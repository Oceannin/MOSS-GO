from pathlib import Path
import re
import tempfile
import unittest

from aiohttp.test_utils import TestClient, TestServer

from moss_go.server import create_app
from moss_go.web_assets import WebAssets


class AssetSnapshotTests(unittest.TestCase):
    def test_updates_get_new_urls_and_do_not_mutate_an_open_pages_snapshot(self):
        with tempfile.TemporaryDirectory() as root:
            source = Path(root) / "app.js"
            source.write_text("export const version = 1;", encoding="utf-8")
            assets = WebAssets(root)
            old = assets.snapshot()
            self.assertEqual(assets.snapshot(), old)
            source.write_text("export const version = 2;", encoding="utf-8")
            new = assets.snapshot()
            self.assertNotEqual(new, old)
            self.assertIn(b"version = 1", assets.read(old, "app.js")[0])
            self.assertIn(b"version = 2", assets.read(new, "app.js")[0])
            with self.assertRaises(KeyError):
                assets.read(new, "../app.js")

    def test_hidden_and_non_web_files_are_not_exposed_and_old_snapshots_are_bounded(self):
        with tempfile.TemporaryDirectory() as root:
            folder = Path(root)
            (folder / ".secret.json").write_text("{}")
            (folder / "private.py").write_text("secret = 1")
            source = folder / "app.js"
            source.write_text("1")
            assets = WebAssets(root, retained_versions=2)
            first = assets.snapshot()
            for version in ("2", "3"):
                source.write_text(version)
                current = assets.snapshot()
            with self.assertRaises(KeyError):
                assets.read(first, "app.js")
            for path in (".secret.json", "private.py"):
                with self.assertRaises(KeyError):
                    assets.read(current, path)


class AssetHttpTests(unittest.IsolatedAsyncioTestCase):
    async def test_legacy_html_cannot_bypass_the_main_pages_frame_policy(self):
        for path in ("/moss-go/", "/moss-go/assets/index.html"):
            response = await self.client.get(path)
            self.assertEqual(response.status, 200)
            self.assertIn("frame-ancestors 'none'", response.headers["Content-Security-Policy"])
            self.assertEqual(response.headers["X-Content-Type-Options"], "nosniff")

    async def asyncSetUp(self):
        self.data = tempfile.TemporaryDirectory()
        self.client = TestClient(TestServer(create_app(data_root=self.data.name, comfy_url="http://127.0.0.1:1"), host="127.0.0.1"))
        await self.client.start_server()

    async def asyncTearDown(self):
        await self.client.close()
        self.data.cleanup()

    async def test_root_and_transitive_module_paths_use_one_immutable_revision(self):
        root = await self.client.get("/moss-go/")
        self.assertEqual(root.headers["Cache-Control"], "no-cache")
        html = await root.text()
        revisions = re.findall(r"/moss-go/assets/([a-f0-9]{20})/", html)
        self.assertTrue(revisions)
        self.assertEqual(len(set(revisions)), 1)
        prefix = f"/moss-go/assets/{revisions[0]}/"
        for path in ("app.js", "character-editor.js", "studio.css", "fonts/InterVariable.woff2"):
            response = await self.client.get(prefix + path)
            self.assertEqual(response.status, 200)
            self.assertIn("immutable", response.headers["Cache-Control"])
        missing = await self.client.get(prefix + "missing.js")
        self.assertEqual(missing.status, 404)
        plain = await self.client.get("/moss-go/assets/app.js")
        self.assertEqual(plain.headers["Cache-Control"], "no-cache")
