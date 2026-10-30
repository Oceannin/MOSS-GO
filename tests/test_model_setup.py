import hashlib
import io
from pathlib import Path
import tempfile
import unittest

from moss_go.model_setup import download_file, inspect_file, load_manifest, target_path
from moss_go.workflows import MODEL_ROLES


class Response(io.BytesIO):
    def __init__(self, data, status=200, **headers):
        super().__init__(data)
        self.status = status
        self.headers = headers


class ModelSetupTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.data = b"pinned model fixture bytes"
        self.item = {
            "category": "vae", "filename": "fixture.safetensors",
            "repository": "owner/model", "revision": "a" * 40,
            "path": "split_files/vae/fixture.safetensors",
            "sha256": hashlib.sha256(self.data).hexdigest(), "size": len(self.data),
        }
        self.path = target_path(self.root, self.item)

    def download(self, response):
        requests = []
        def opener(request, **kwargs):
            requests.append(request)
            return response
        result = download_file(self.root, self.item, opener=opener, report=lambda _: None)
        return result, requests

    def partial(self, data):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        part = self.path.with_name("." + self.path.name + ".moss-go.part")
        part.write_bytes(data)
        return part

    def test_installs_verified_bytes_at_runtime_resolvable_paths(self):
        manifest = load_manifest()
        for pack in manifest["packs"].values():
            for item in pack["files"]:
                category, aliases = MODEL_ROLES[pack["engine"]][item["role"]]
                self.assertEqual(category, item["category"])
                self.assertIn(item["filename"], aliases)
        result, requests = self.download(Response(self.data))
        self.assertEqual(result, "installed")
        self.assertEqual(self.path.read_bytes(), self.data)
        self.assertIn("/resolve/" + self.item["revision"] + "/", requests[0].full_url)
        self.assertEqual(inspect_file(self.path, self.item), "verified")

    def test_same_size_corrupt_response_never_becomes_a_model(self):
        with self.assertRaisesRegex(ValueError, "incorrect download"):
            self.download(Response(b"x" * len(self.data)))
        self.assertFalse(self.path.exists())

    def test_existing_conflicting_file_is_never_overwritten_or_downloaded(self):
        self.path.parent.mkdir(parents=True)
        self.path.write_bytes(b"x" * len(self.data))
        with self.assertRaisesRegex(ValueError, "left untouched"):
            self.download(Response(self.data))
        self.assertEqual(self.path.read_bytes(), b"x" * len(self.data))

    def test_existing_verified_file_does_not_open_network(self):
        self.path.parent.mkdir(parents=True)
        self.path.write_bytes(self.data)
        def forbidden(*args, **kwargs):
            self.fail("Verified weights must not be downloaded again")
        self.assertEqual(download_file(self.root, self.item, opener=forbidden, report=lambda _: None), "verified")

    def test_partial_download_resumes_only_with_correct_range(self):
        part = self.partial(self.data[:7])
        size = len(self.data)
        _, requests = self.download(Response(self.data[7:], 206, **{"Content-Range": f"bytes 7-{size-1}/{size}", "Content-Length": str(size-7)}))
        self.assertEqual(requests[0].get_header("Range"), "bytes=7-")
        self.assertEqual(self.path.read_bytes(), self.data)
        self.assertFalse(part.exists())

    def test_range_ignored_by_server_restarts_instead_of_appending(self):
        self.partial(self.data[:7])
        self.download(Response(self.data, 200, **{"Content-Length": str(len(self.data))}))
        self.assertEqual(self.path.read_bytes(), self.data)

    def test_incorrect_range_keeps_original_partial(self):
        part = self.partial(self.data[:7])
        with self.assertRaisesRegex(ValueError, "byte range"):
            self.download(Response(self.data[7:], 206, **{"Content-Range": "bytes 8-24/25"}))
        self.assertEqual(part.read_bytes(), self.data[:7])
        self.assertFalse(self.path.exists())

    def test_incomplete_response_can_be_resumed_on_next_invocation(self):
        with self.assertRaisesRegex(ValueError, "Incomplete"):
            self.download(Response(self.data[:7]))
        self.assertFalse(self.path.exists())
        size = len(self.data)
        self.download(Response(self.data[7:], 206, **{"Content-Range": f"bytes 7-{size-1}/{size}"}))
        self.assertEqual(self.path.read_bytes(), self.data)

    def test_excess_response_cannot_write_more_than_pinned_size(self):
        with self.assertRaisesRegex(ValueError, "exceeds"):
            self.download(Response(self.data + b"extra"))
        self.assertFalse(self.path.exists())

    def test_locked_model_is_not_touched(self):
        self.path.parent.mkdir(parents=True)
        lock = self.path.with_name("." + self.path.name + ".moss-go.lock")
        lock.write_text("another process")
        with self.assertRaisesRegex(ValueError, "locked"):
            self.download(Response(self.data))
        self.assertEqual(lock.read_text(), "another process")
        self.assertFalse(self.path.exists())

    def test_category_symlink_cannot_escape_selected_directory(self):
        outside = self.root / "outside"
        outside.mkdir()
        models = self.root / "models"
        models.mkdir()
        try:
            (models / "vae").symlink_to(outside, target_is_directory=True)
        except OSError as exc:
            self.skipTest(f"Symlink creation unavailable: {exc}")
        with self.assertRaisesRegex(ValueError, "outside"):
            target_path(models, self.item)
