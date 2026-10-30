"""Durable jobs and content-addressed images, separate from personal ComfyUI history."""

import hashlib
from contextlib import contextmanager
import io
import json
import os
from pathlib import Path
import sqlite3
import time
import uuid
import warnings

from PIL import Image, ImageOps, UnidentifiedImageError

from .errors import StudioError
from .settings import SEED_MAX, identifier

MAX_IMAGE_BYTES = 25 * 1024 * 1024
MAX_IMAGE_PIXELS = 32_000_000
TERMINAL = {"done", "error", "cancelled", "interrupted"}


class Store:
    def __init__(self, root):
        self.root = Path(root).resolve()
        self.images = self.root / "images"
        self.images.mkdir(parents=True, exist_ok=True)
        self.database = self.root / "catalog.sqlite3"
        with self.connect() as db:
            db.executescript("""
                PRAGMA journal_mode=WAL;
                CREATE TABLE IF NOT EXISTS metadata(key TEXT PRIMARY KEY, value TEXT NOT NULL);
                INSERT OR IGNORE INTO metadata VALUES('schema_version','2');
                CREATE TABLE IF NOT EXISTS artifacts(
                    id TEXT PRIMARY KEY, kind TEXT NOT NULL, sha256 TEXT NOT NULL,
                    width INTEGER NOT NULL, height INTEGER NOT NULL,
                    minimum INTEGER NOT NULL, maximum INTEGER NOT NULL, created REAL NOT NULL);
                CREATE TABLE IF NOT EXISTS batches(
                    id TEXT PRIMARY KEY, request_id TEXT UNIQUE NOT NULL,
                    settings TEXT NOT NULL, created REAL NOT NULL);
                CREATE TABLE IF NOT EXISTS jobs(
                    id TEXT PRIMARY KEY, batch_id TEXT NOT NULL REFERENCES batches(id),
                    settings TEXT NOT NULL, scene INTEGER NOT NULL, variant INTEGER NOT NULL,
                    status TEXT NOT NULL, prompt_id TEXT, output_id TEXT REFERENCES artifacts(id),
                    error TEXT, elapsed REAL, created REAL NOT NULL, updated REAL NOT NULL,
                    error_code TEXT);
                CREATE INDEX IF NOT EXISTS jobs_created ON jobs(created DESC);
                CREATE INDEX IF NOT EXISTS jobs_status ON jobs(status);
                CREATE TABLE IF NOT EXISTS executions(
                    job_id TEXT PRIMARY KEY REFERENCES jobs(id),
                    graph TEXT NOT NULL, models TEXT NOT NULL,
                    effective_settings TEXT NOT NULL, created REAL NOT NULL);
            """)
            version = db.execute("SELECT value FROM metadata WHERE key='schema_version'").fetchone()[0]
            if version == "1":
                columns = {row["name"] for row in db.execute("PRAGMA table_info(jobs)")}
                if "error_code" not in columns:
                    db.execute("ALTER TABLE jobs ADD COLUMN error_code TEXT")
                db.execute("UPDATE metadata SET value='2' WHERE key='schema_version'")
            elif version != "2":
                raise RuntimeError("This catalog version requires a newer MOSS GO installation.")

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.database, timeout=15)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys=ON")
        try:
            with db:
                yield db
        finally:
            db.close()

    def add_image(self, raw, kind="input"):
        if kind not in {"input", "mask", "result"}:
            raise ValueError("Unknown artifact kind")
        if not raw or len(raw) > MAX_IMAGE_BYTES:
            raise StudioError("Choose an image smaller than 25 MB.", field="image")
        try:
            with warnings.catch_warnings():
                warnings.simplefilter("error", Image.DecompressionBombWarning)
                with Image.open(io.BytesIO(raw)) as source:
                    if source.format not in {"PNG", "JPEG", "WEBP"}:
                        raise StudioError("Choose a PNG, JPEG or WebP image.", field="image")
                    if source.width * source.height > MAX_IMAGE_PIXELS:
                        raise StudioError("Choose an image with at most 32 million pixels.", field="image")
                    if getattr(source, "n_frames", 1) != 1:
                        raise StudioError("Choose a single still image.", field="image")
                    picture = ImageOps.exif_transpose(source).convert("L" if kind == "mask" else "RGB")
                    out = io.BytesIO()
                    picture.save(out, format="PNG")
        except (UnidentifiedImageError, OSError, Image.DecompressionBombError, Image.DecompressionBombWarning) as exc:
            raise StudioError("The image could not be read safely.", field="image") from exc
        content = out.getvalue()
        digest = hashlib.sha256(content).hexdigest()
        image_id = hashlib.sha256((kind + digest).encode()).hexdigest()[:32]
        path = self.images / (image_id + ".png")
        if not path.exists():
            temporary = self.images / (uuid.uuid4().hex + ".tmp")
            try:
                temporary.write_bytes(content)
                os.replace(temporary, path)
            finally:
                temporary.unlink(missing_ok=True)
        low, high = picture.getextrema() if kind == "mask" else (0, 255)
        with self.connect() as db:
            db.execute("INSERT OR IGNORE INTO artifacts VALUES(?,?,?,?,?,?,?,?)", (image_id, kind, digest, picture.width, picture.height, low, high, time.time()))
        return self.artifact(image_id)

    def artifact(self, image_id):
        identifier(image_id)
        with self.connect() as db:
            row = db.execute("SELECT * FROM artifacts WHERE id=?", (image_id,)).fetchone()
        if row is None:
            raise StudioError("This image is no longer available.", code="image_missing", status=404)
        return dict(row)

    def image_path(self, image_id):
        self.artifact(image_id)
        path = self.images / (image_id + ".png")
        if not path.is_file():
            raise StudioError("The image file is missing.", code="image_missing", status=404)
        return path

    def create_batch(self, settings):
        serialized = json.dumps(settings, sort_keys=True, ensure_ascii=False)
        now, batch_id = time.time(), uuid.uuid4().hex
        prompts = settings["scenes"] or [""]
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            existing = db.execute("SELECT * FROM batches WHERE request_id=?", (settings["request_id"],)).fetchone()
            if existing:
                if existing["settings"] != serialized:
                    raise StudioError("This request identifier was already used with different settings.", code="request_conflict", status=409)
                batch_id = existing["id"]
            else:
                db.execute("INSERT INTO batches VALUES(?,?,?,?)", (batch_id, settings["request_id"], serialized, now))
                for scene, description in enumerate(prompts):
                    for variant in range(settings["variants"]):
                        item = dict(settings)
                        item["seed"] = (settings["seed"] + scene * settings["variants"] + variant) % (SEED_MAX + 1)
                        item["prompt"] = "\n".join(filter(None, [settings["prompt"], description]))
                        db.execute("INSERT INTO jobs(id,batch_id,settings,scene,variant,status,created,updated) VALUES(?,?,?,?,?,'pending',?,?)", (uuid.uuid4().hex, batch_id, json.dumps(item, ensure_ascii=False), scene, variant, now, now))
        return self.batch(batch_id)

    @staticmethod
    def _job(row):
        result = dict(row)
        result["settings"] = json.loads(result["settings"])
        return result

    def job(self, job_id):
        identifier(job_id)
        with self.connect() as db:
            row = db.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone()
        if row is None:
            raise StudioError("This job could not be found.", code="job_missing", status=404)
        return self._job(row)

    def jobs(self, *, active=False, limit=100):
        with self.connect() as db:
            if active:
                rows = db.execute("SELECT * FROM jobs WHERE status NOT IN ('done','error','cancelled','interrupted') ORDER BY created,scene,variant").fetchall()
            else:
                rows = db.execute("SELECT * FROM jobs ORDER BY created DESC,rowid DESC LIMIT ?", (limit,)).fetchall()
        return [self._job(row) for row in rows]

    def batch(self, batch_id):
        identifier(batch_id)
        with self.connect() as db:
            rows = db.execute("SELECT * FROM jobs WHERE batch_id=? ORDER BY scene,variant", (batch_id,)).fetchall()
        return {"id": batch_id, "jobs": [self._job(row) for row in rows]}

    def batch_for_request(self, request_id):
        identifier(request_id, "request_id")
        with self.connect() as db:
            row = db.execute("SELECT id FROM batches WHERE request_id=?", (request_id,)).fetchone()
        return self.batch(row["id"]) if row else None

    def save_execution(self, job_id, *, graph, models, settings):
        self.job(job_id)
        with self.connect() as db:
            db.execute("INSERT OR IGNORE INTO executions VALUES(?,?,?,?,?)", (job_id, json.dumps(graph), json.dumps(models), json.dumps(settings, ensure_ascii=False), time.time()))

    def execution(self, job_id):
        self.job(job_id)
        with self.connect() as db:
            row = db.execute("SELECT * FROM executions WHERE job_id=?", (job_id,)).fetchone()
        return {"graph": json.loads(row["graph"]), "models": json.loads(row["models"]), "settings": json.loads(row["effective_settings"]), "recorded_at": row["created"]} if row else None

    def update_job(self, job_id, **changes):
        identifier(job_id)
        if not changes or set(changes) - {"status", "prompt_id", "output_id", "error", "error_code", "elapsed"}:
            raise ValueError("Unsupported job update")
        if "status" in changes and changes["status"] not in {*TERMINAL, "pending", "submitting", "queued", "running"}:
            raise ValueError("Unknown job status")
        changes["updated"] = time.time()
        with self.connect() as db:
            # A delayed queue/history response must never revive or overwrite a
            # terminal result, especially a cancellation accepted concurrently.
            db.execute("UPDATE jobs SET " + ",".join(f"{key}=?" for key in changes) + " WHERE id=? AND status NOT IN ('done','error','cancelled','interrupted')", (*changes.values(), job_id))
        return self.job(job_id)

    @staticmethod
    def _hold_pending_batch(db, batch_id, *, system_memory=False):
        db.execute("UPDATE jobs SET status='interrupted',error_code=?,error=?,updated=? WHERE batch_id=? AND status='pending' AND prompt_id IS NULL",
                   ("batch_system_memory_hold" if system_memory else "batch_memory_hold",
                    "This take was held after its batch ran out of memory. Load its settings to retry when ready.", time.time(), batch_id))

    def hold_pending_batch(self, batch_id, *, system_memory=False):
        """End only this batch's unsubmitted takes after a memory failure."""
        identifier(batch_id, "batch_id")
        with self.connect() as db:
            self._hold_pending_batch(db, batch_id, system_memory=system_memory)

    def fail_job(self, job_id, *, error, code):
        """The failure and memory hold commit together, or neither commits."""
        identifier(job_id)
        with self.connect() as db:
            changed = db.execute("UPDATE jobs SET status='error',error=?,error_code=?,updated=? WHERE id=? AND status NOT IN ('done','error','cancelled','interrupted')",
                                 (error, code, time.time(), job_id)).rowcount
            if changed and code in {"out_of_memory", "system_memory_exhausted"}:
                batch_id = db.execute("SELECT batch_id FROM jobs WHERE id=?", (job_id,)).fetchone()[0]
                self._hold_pending_batch(db, batch_id, system_memory=code == "system_memory_exhausted")
        return self.job(job_id)
