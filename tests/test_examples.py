import hashlib
import io
import tempfile
import unittest
from unittest.mock import patch

from aiohttp.test_utils import TestClient, TestServer
from PIL import Image

from moss_go.examples import EXAMPLES, example_bytes
from moss_go.server import API, STUDIO, create_app


class ExampleTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.app = create_app(data_root=self.folder.name, comfy_url="http://127.0.0.1:1")
        self.client = TestClient(TestServer(self.app))
        await self.client.start_server()

    async def asyncTearDown(self):
        await self.client.close()
        self.folder.cleanup()

    async def test_preview_is_read_only_and_all_originals_have_matching_hashes_and_dimensions(self):
        listing = await (await self.client.get(API + "/examples")).json()
        self.assertEqual([item["id"] for item in listing["items"]], ["mira", "theo", "nia"])
        for item in listing["items"]:
            response = await self.client.get(item["image_url"])
            self.assertEqual(response.status, 200)
            content = await response.read()
            self.assertEqual(hashlib.sha256(content).hexdigest(), EXAMPLES[item["id"]]["sha256"])
            with Image.open(io.BytesIO(content)) as picture:
                self.assertEqual(picture.size, (item["width"], item["height"]))
        with self.app[STUDIO]["store"].connect() as db:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM artifacts").fetchone()[0], 0)

    async def test_loading_an_original_prepares_one_canonical_input_without_jobs(self):
        for example_id in EXAMPLES:
            route = API + f"/examples/{example_id}/use"
            first = await self.client.post(route, json={})
            self.assertEqual(first.status, 201)
            artifact = await first.json()
            repeated = await (await self.client.post(route, json={})).json()
            self.assertEqual(artifact["id"], repeated["id"])
            self.assertEqual(artifact["kind"], "input")
            with Image.open(io.BytesIO(example_bytes(example_id))) as source, Image.open(self.app[STUDIO]["store"].image_path(artifact["id"])) as prepared:
                self.assertEqual(source.convert("RGB").tobytes(), prepared.convert("RGB").tobytes())
        self.assertEqual((await (await self.client.get(API + "/jobs")).json())["items"], [])

    async def test_unknown_examples_wrong_hashes_settings_and_external_origins_are_rejected(self):
        cases = [("/examples/unknown/use", {}, {}, 404), ("/examples/mira/use", {"prompt": "Never launch"}, {}, 400),
                 ("/examples/mira/use", {}, {"Origin": "https://outside.invalid"}, 403)]
        for route, body, headers, status in cases:
            result = await self.client.post(API + route, json=body, headers=headers)
            self.assertEqual(result.status, status)
        image = await self.client.get(API + "/examples/mira/" + "0" * 64 + ".png")
        self.assertEqual(image.status, 404)

    async def test_a_damaged_bundled_image_is_not_imported(self):
        with patch.dict(EXAMPLES["mira"], {"sha256": "0" * 64}):
            result = await self.client.post(API + "/examples/mira/use", json={})
            self.assertEqual(result.status, 500)
            self.assertEqual((await result.json())["error"]["code"], "example_corrupt")
        with self.app[STUDIO]["store"].connect() as db:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM artifacts").fetchone()[0], 0)
