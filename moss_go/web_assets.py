"""Content-addressed native modules and styles, with immutable snapshots."""

from collections import OrderedDict
import hashlib
from pathlib import Path


CONTENT_TYPES = {".js": "text/javascript", ".css": "text/css", ".svg": "image/svg+xml",
                 ".woff2": "font/woff2", ".png": "image/png", ".jpg": "image/jpeg",
                 ".webp": "image/webp", ".txt": "text/plain", ".json": "application/json"}


class WebAssets:
    def __init__(self, root, retained_versions=4):
        self.root = Path(root)
        self.retained_versions = retained_versions
        self.versions = OrderedDict()

    def snapshot(self):
        files, digest = {}, hashlib.sha256()
        for path in sorted(self.root.rglob("*")):
            relative = path.relative_to(self.root)
            if not path.is_file() or path.suffix.lower() not in CONTENT_TYPES or any(part.startswith(".") for part in relative.parts):
                continue
            content = path.read_bytes()
            name = relative.as_posix()
            files[name] = (content, CONTENT_TYPES[path.suffix.lower()])
            digest.update(name.encode("utf-8") + b"\0" + hashlib.sha256(content).digest())
        revision = digest.hexdigest()[:20]
        if revision not in self.versions:
            self.versions[revision] = files
            while len(self.versions) > self.retained_versions:
                self.versions.popitem(last=False)
        return revision

    def read(self, revision, path):
        # Exact dictionary lookup only: URL paths are never opened on the filesystem.
        return self.versions[revision][path]
