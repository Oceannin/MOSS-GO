"""Pinned model downloads. Gated packs require the author's own accepted access."""

import argparse
from contextlib import contextmanager
import hashlib
import http.client
import json
import os
from pathlib import Path, PurePosixPath
import re
import sys
import urllib.request
import urllib.error


MANIFEST = Path(__file__).with_name("assets") / "model_manifest.json"
CHUNK = 1024 * 1024


def load_manifest():
    data = json.loads(MANIFEST.read_text(encoding="utf-8"))
    if data.get("schema_version") != 1:
        raise ValueError("Unsupported model manifest version.")
    for pack in data["packs"].values():
        for item in pack["files"]:
            if item["category"] not in {"diffusion_models", "text_encoders", "vae", "loras"}:
                raise ValueError("Invalid model category.")
            if not re.fullmatch(r"[a-zA-Z0-9_.-]+\.safetensors", item["filename"]):
                raise ValueError("Invalid model filename.")
            if not re.fullmatch(r"[a-zA-Z0-9_.-]+/[a-zA-Z0-9_.-]+", item["repository"]):
                raise ValueError("Invalid model repository.")
            if not re.fullmatch(r"[a-f0-9]{40}", item["revision"]):
                raise ValueError("Model source must be pinned to a commit.")
            if not re.fullmatch(r"[a-f0-9]{64}", item["sha256"]):
                raise ValueError("Invalid model checksum.")
            parts = PurePosixPath(item["path"]).parts
            if not parts or any(not re.fullmatch(r"[a-zA-Z0-9_.-]+", p) or p in {".", ".."} for p in parts):
                raise ValueError("Invalid model source path.")
            if type(item["size"]) is not int or item["size"] <= 0:
                raise ValueError("Invalid model size.")
    return data


def target_path(models_root, item):
    root = Path(models_root).resolve()
    path = root / item["category"] / item["filename"]
    if not path.resolve().is_relative_to(root):
        raise ValueError("Model path resolves outside the selected models directory.")
    return path


def file_digest(path):
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(CHUNK), b""):
            digest.update(chunk)
    return digest.hexdigest()


def inspect_file(path, item, *, verify=True):
    if not path.exists():
        return "missing"
    if not path.is_file() or path.stat().st_size != item["size"]:
        return "conflict"
    if not verify:
        return "present-unverified"
    return "verified" if file_digest(path) == item["sha256"] else "conflict"


@contextmanager
def download_lock(path):
    lock = path.with_name("." + path.name + ".moss-go.lock")
    try:
        handle = lock.open("x", encoding="ascii")
    except FileExistsError as exc:
        raise ValueError(f"Download locked: {lock}. If no setup process is running, remove this lock and retry.") from exc
    try:
        with handle:
            handle.write(str(os.getpid()))
        yield
    finally:
        lock.unlink()


def download_file(models_root, item, *, opener=urllib.request.urlopen, report=print):
    """Resume only validated byte ranges; install only after complete SHA-256."""
    path = target_path(models_root, item)
    path.parent.mkdir(parents=True, exist_ok=True)
    with download_lock(path):
        state = inspect_file(path, item)
        if state == "verified":
            report(f"Verified existing {path.name}")
            return "verified"
        if state != "missing":
            raise ValueError(f"Existing file differs from the manifest: {path}. It was left untouched; move it aside before installing this pack.")
        part = path.with_name("." + path.name + ".moss-go.part")
        if part.is_symlink() or not part.resolve().is_relative_to(Path(models_root).resolve()):
            raise ValueError("Partial download resolves outside the models directory.")
        offset = part.stat().st_size if part.exists() else 0
        if offset > item["size"]:
            raise ValueError(f"Oversized partial download: {part}. Move it aside and retry.")
        if offset < item["size"]:
            url = f"https://huggingface.co/{item['repository']}/resolve/{item['revision']}/{item['path']}"
            headers = {"User-Agent": "MOSS-GO-model-setup/1", "Accept-Encoding": "identity"}
            if offset:
                headers["Range"] = f"bytes={offset}-"
            request = urllib.request.Request(url, headers=headers)
            if item.get("requires_hf_access"):
                token = hub_token()
                if not token:
                    raise ValueError(f"Accept the model terms at https://huggingface.co/{item['repository']} and authenticate with hf auth login or HF_TOKEN. No access terms are accepted automatically.")
                # urllib does not copy unredirected headers onto signed CDN
                # redirects. Never forward the user's hub token to a CDN.
                request.add_unredirected_header("Authorization", "Bearer " + token)
            try:
                response = opener(request, timeout=30)
            except urllib.error.HTTPError as exc:
                if item.get("requires_hf_access") and exc.code in {401, 403}:
                    raise ValueError(f"Hugging Face access denied. Review and accept the model conditions at https://huggingface.co/{item['repository']} using the account associated with your local credential.") from None
                raise
            with response:
                status = response.status
                if response.headers.get("Content-Encoding", "identity") != "identity":
                    raise ValueError("Unexpected encoded model response.")
                if status == 200:
                    offset = 0  # Server ignored Range: replace the partial, never append.
                elif status == 206:
                    expected = f"bytes {offset}-{item['size'] - 1}/{item['size']}"
                    if response.headers.get("Content-Range") != expected:
                        raise ValueError("Unexpected model byte range; partial file left untouched.")
                else:
                    raise ValueError(f"Unexpected model HTTP status: {status}")
                length = response.headers.get("Content-Length")
                if length is not None and int(length) != item["size"] - offset:
                    raise ValueError("Model response size differs from the pinned manifest.")
                report(f"Downloading {path.name}: {offset}/{item['size']} bytes")
                last_report = offset
                with part.open("ab" if offset else "wb") as output:
                    while True:
                        chunk = response.read(min(CHUNK, item["size"] - offset + 1))
                        if not chunk:
                            break
                        if offset + len(chunk) > item["size"]:
                            raise ValueError("Model response exceeds the pinned file size.")
                        output.write(chunk)
                        offset += len(chunk)
                        if offset - last_report >= 64 * CHUNK:
                            report(f"{path.name}: {offset}/{item['size']} bytes")
                            last_report = offset
                    output.flush()
                    os.fsync(output.fileno())
        if inspect_file(part, item) != "verified":
            raise ValueError(f"Incomplete or incorrect download: {part}. No model was installed. Retry an incomplete download; move aside a full-size checksum mismatch.")
        # Windows rename refuses an existing destination, including on volumes
        # without hardlinks. POSIX rename would overwrite, so use link there.
        if os.name == "nt":
            os.rename(part, path)
        else:
            os.link(part, path)
            part.unlink()
        report(f"Installed and verified {path.name}")
        return "installed"


def hub_token():
    """Read the existing local HF credential; never log or persist it."""
    token = os.environ.get("HF_TOKEN") or os.environ.get("HUGGING_FACE_HUB_TOKEN")
    if token:
        return token.strip()
    cache = Path(os.environ.get("HF_HOME", Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache")) / "huggingface"))
    path = Path(os.environ.get("HF_TOKEN_PATH", cache / "token"))
    try:
        return path.read_text(encoding="utf-8").strip() or None
    except (OSError, UnicodeError):
        return None


def main(argv=None):
    manifest = load_manifest()
    parser = argparse.ArgumentParser(description="Plan, verify or download pinned MOSS GO model packs. Existing models are never overwritten.")
    parser.add_argument("action", choices=("plan", "check", "download"))
    parser.add_argument("--models-dir", required=True, type=Path, help="ComfyUI models directory")
    parser.add_argument("--pack", choices=tuple(manifest["packs"]), action="append", required=True)
    args = parser.parse_args(argv)
    failed = False
    for name in dict.fromkeys(args.pack):
        pack = manifest["packs"][name]
        print(f"{name}: {pack['verified_on']}", flush=True)
        for item in pack["files"]:
            try:
                path = target_path(args.models_dir, item)
                if args.action == "download":
                    download_file(args.models_dir, item, report=lambda line: print(line, flush=True))
                else:
                    state = inspect_file(path, item, verify=args.action == "check")
                    print(f"  {state}: {item['category']}/{item['filename']} ({item['size']:,} bytes)", flush=True)
                    if args.action == "check" and state != "verified":
                        failed = True
            except (ValueError, OSError, http.client.IncompleteRead) as exc:
                print(f"  Error: {exc}", file=sys.stderr, flush=True)
                failed = True
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
