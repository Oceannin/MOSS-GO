"""Portable image bundles. Import is a reviewed preparation, never execution."""

import hashlib
import io
import json
import math
import re
import zipfile

from PIL import Image, ImageDraw, ImageFont

from . import __version__
from .characters import import_character
from .errors import StudioError
from .settings import validate_request

MAX_BUNDLE_BYTES = 100 * 1024 * 1024
MAX_BUNDLE_FILES = 80
LAUNCH_FIELDS = {"mode", "engine", "profile", "quality", "format", "prompt", "negative", "seed", "variants", "strength", "feather", "scenes", "character", "loras", "input_id", "mask_id", "prompt_upsampler", "flux3_steps"}


def recipe_for_job(store, job_id):
    job = store.job(job_id)
    # A take already contains its scene description and its effective seed.
    # Replaying it must not append every scene again or expand to more variants.
    settings = {**job["settings"], "scenes": [], "variants": 1}
    return {"recipe_version": 1, "application": "MOSS GO", "application_version": __version__,
            "source_job_id": job["id"], "settings": settings, "execution": store.execution(job_id),
            "inputs": {key: store.artifact(settings[key]) for key in ("input_id", "mask_id") if settings.get(key)},
            "output": store.artifact(job["output_id"]) if job.get("output_id") else None}


def preview_recipe(store, recipe):
    if not isinstance(recipe, dict) or recipe.get("recipe_version") != 1:
        raise StudioError("This recipe version is not supported.")
    source = recipe.get("settings")
    if not isinstance(source, dict):
        raise StudioError("The recipe has no settings.")
    settings = {key: value for key, value in source.items() if key in LAUNCH_FIELDS}
    character = import_character(source.get("character", {}))
    settings["character"] = character["character"]
    if settings.get("mode") != "refine" and "width" in source and "height" in source:
        settings["size"] = {"width": source["width"], "height": source["height"]}
    checked = validate_request(settings)
    missing = []
    for key in ("input_id", "mask_id"):
        if checked.get(key):
            try:
                store.image_path(checked[key])
            except StudioError:
                missing.append(key)
    internal = {"request_id", "requested_profile", "width", "height", "source_width", "source_height", "edit_region", "steps", "text_device", "parent_id"}
    removed = sorted(set(source) - LAUNCH_FIELDS - internal)
    return {"settings": settings, "missing_inputs": missing, "removed_fields": removed,
            "removed_character_fields": character["removed_fields"], "requires_review": True,
            "source_job_id": recipe.get("source_job_id")}


def contact_sheet(store, jobs):
    columns = min(4, len(jobs))
    tile_w, tile_h, caption, gap = 300, 380, 44, 16
    rows = math.ceil(len(jobs) / columns)
    sheet = Image.new("RGB", (columns * (tile_w + gap) + gap, rows * (tile_h + caption + gap) + gap), "#211927")
    draw, font = ImageDraw.Draw(sheet), ImageFont.load_default(size=16)
    for index, job in enumerate(jobs):
        x, y = gap + index % columns * (tile_w + gap), gap + index // columns * (tile_h + caption + gap)
        with Image.open(store.image_path(job["output_id"])) as source:
            picture = source.convert("RGB")
            picture.thumbnail((tile_w, tile_h), Image.Resampling.LANCZOS)
            sheet.paste(picture, (x + (tile_w - picture.width) // 2, y + (tile_h - picture.height) // 2))
        draw.text((x, y + tile_h + 8), f"Scene {job['scene'] + 1} / Take {job['variant'] + 1} / Seed {job['settings']['seed']}", fill="#f0efed", font=font)
    out = io.BytesIO()
    sheet.save(out, format="JPEG", quality=92)
    return out.getvalue()


def export_bundle(store, job_ids):
    if not isinstance(job_ids, list) or not 1 <= len(job_ids) <= 16 or len(set(job_ids)) != len(job_ids):
        raise StudioError("Export between one and sixteen distinct saved takes.")
    jobs = [store.job(job_id) for job_id in job_ids]
    if any(job["status"] != "done" or not job["output_id"] for job in jobs):
        raise StudioError("Wait for the selected images to finish before exporting.", status=409)
    recipes = [recipe_for_job(store, job["id"]) for job in jobs]
    files = {}
    for recipe in recipes:
        for artifact in [*recipe["inputs"].values(), recipe["output"]]:
            files[f"images/{artifact['id']}.png"] = store.image_path(artifact["id"]).read_bytes()
        execution = recipe.get("execution")
        if execution:
            files[f"workflows/{recipe['source_job_id']}.api.json"] = json.dumps(execution["graph"], indent=2, ensure_ascii=False).encode("utf-8")
    files["manifest.json"] = json.dumps({"bundle_format": "moss-go", "bundle_version": 1, "recipes": recipes}, indent=2, ensure_ascii=False).encode("utf-8")
    files["contact-sheet.jpg"] = contact_sheet(store, jobs)
    if sum(len(raw) for raw in files.values()) > MAX_BUNDLE_BYTES:
        raise StudioError("This pack is larger than 100 MB. Export fewer takes at once.")
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, content in files.items():
            archive.writestr(name, content)
    return out.getvalue()


def import_bundle(store, raw):
    if not raw or len(raw) > MAX_BUNDLE_BYTES:
        raise StudioError("Choose a MOSS GO pack smaller than 100 MB.")
    try:
        with zipfile.ZipFile(io.BytesIO(raw)) as archive:
            entries = archive.infolist()
            names = [entry.filename for entry in entries]
            if len(entries) > MAX_BUNDLE_FILES or len(set(names)) != len(names):
                raise StudioError("The pack has duplicate or too many files.")
            if sum(entry.file_size for entry in entries) > MAX_BUNDLE_BYTES:
                raise StudioError("The expanded pack exceeds the 100 MB limit.")
            if any(not re.fullmatch(r"manifest\.json|contact-sheet\.jpg|images/[a-f0-9]{32}\.png|workflows/[a-f0-9]{32}\.api\.json", name) for name in names):
                raise StudioError("The pack contains an unexpected file or path.")
            manifest_info = archive.getinfo("manifest.json")
            if manifest_info.file_size > 2_000_000:
                raise StudioError("The recipe manifest is too large.")
            manifest = json.loads(archive.read("manifest.json"))
            if not isinstance(manifest, dict) or manifest.get("bundle_format") != "moss-go" or manifest.get("bundle_version") != 1:
                raise StudioError("This is not a supported MOSS GO pack.")
            recipes = manifest.get("recipes")
            if not isinstance(recipes, list) or not 1 <= len(recipes) <= 16:
                raise StudioError("The pack must contain one to sixteen recipes.")
            artifacts = {}
            for recipe in recipes:
                preview_recipe(store, recipe)
                inputs = recipe.get("inputs", {})
                if not isinstance(inputs, dict) or set(inputs) - {"input_id", "mask_id"}:
                    raise StudioError("The recipe contains invalid image references.")
                for slot, item in inputs.items():
                    if not isinstance(item, dict) or item.get("id") != recipe["settings"].get(slot):
                        raise StudioError("The recipe input does not match its settings.")
                descriptors = [*inputs.values()]
                if recipe.get("output") is not None:
                    descriptors.append(recipe["output"])
                for item in descriptors:
                    if not isinstance(item, dict) or not re.fullmatch(r"[a-f0-9]{32}", str(item.get("id", ""))) or item.get("kind") not in {"input", "mask", "result"}:
                        raise StudioError("The pack contains invalid image metadata.")
                    filename = f"images/{item['id']}.png"
                    if archive.getinfo(filename).file_size > 25 * 1024 * 1024:
                        raise StudioError("An image in the pack is larger than 25 MB.")
                    content = archive.read(filename)
                    if hashlib.sha256(content).hexdigest() != item.get("sha256"):
                        raise StudioError("An image in the pack failed its integrity check.")
                    artifacts[item["id"]] = (content, item["kind"])
    except (zipfile.BadZipFile, KeyError, ValueError, TypeError, UnicodeDecodeError) as exc:
        if isinstance(exc, StudioError):
            raise
        raise StudioError("The MOSS GO pack could not be read.") from exc
    # Files are decoded through the same guarded image importer; no paths are extracted.
    remap = {old: store.add_image(content, kind)["id"] for old, (content, kind) in artifacts.items()}
    previews = []
    for recipe in recipes:
        preview = preview_recipe(store, recipe)
        for key in ("input_id", "mask_id"):
            if preview["settings"].get(key):
                old = preview["settings"][key]
                if old not in remap:
                    raise StudioError("The pack is missing an input image.")
                preview["settings"][key] = remap[old]
        preview["missing_inputs"] = []
        preview["imported_output_id"] = remap.get((recipe.get("output") or {}).get("id"))
        previews.append(preview)
    return {"items": previews, "requires_review": True}
