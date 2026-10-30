"""Exercise installed package resources and HTTP routes, outside the source tree."""

import asyncio
import hashlib
import importlib.util
import json
from pathlib import Path
import posixpath
import re
import sys
import tempfile

from aiohttp.test_utils import TestClient, TestServer
import moss_go
from moss_go.server import API, create_app
from moss_go.web_assets import CONTENT_TYPES


async def main():
    installed = Path(moss_go.__file__).resolve().parent
    assert installed.is_relative_to(Path(sys.prefix).resolve()), f"Not an installed package: {installed}"
    assert importlib.util.find_spec("torch") is None, "This smoke test requires a CPU-only environment without Torch"
    assert importlib.util.find_spec("comfy") is None, "ComfyUI must not be supplied by the source checkout"
    assert (installed / "web/fonts/InterVariable.woff2").read_bytes().startswith(b"wOF2")
    assert "OFL" in (installed / "web/fonts/OFL.txt").read_text("utf-8")
    assert "MIT" in (installed / "nodes/THIRD_PARTY_OSTRIS_LICENSE.txt").read_text("utf-8")
    for filename in ("assistant_model.json", "model_manifest.json", "character_catalog.json"):
        json.loads((installed / "assets" / filename).read_text("utf-8"))
    with tempfile.TemporaryDirectory(prefix="moss-go-smoke-") as folder:
        client = TestClient(TestServer(create_app(data_root=folder, comfy_url="http://127.0.0.1:1", ollama_url="http://127.0.0.1:1")))
        await client.start_server()
        try:
            response = await client.get("/moss-go/")
            assert response.status == 200
            html = await response.text()
            assert '<html lang="en"' in html
            revision = re.search(r"/moss-go/assets/([a-f0-9]{20})/", html).group(1)
            checked = 0
            for path in (installed / "web").rglob("*"):
                if not path.is_file() or path.name.startswith(".") or path.suffix not in CONTENT_TYPES:
                    continue
                relative = path.relative_to(installed / "web").as_posix()
                asset = await client.get(f"/moss-go/assets/{revision}/{relative}")
                assert asset.status == 200, relative
                assert await asset.read() == path.read_bytes(), relative
                if path.suffix == ".js":
                    for specifier in re.findall(r'(?:from\s+|import\s*)[\"\'](\.[^\"\']+\.js)[\"\']', path.read_text("utf-8")):
                        imported = posixpath.normpath(posixpath.join(posixpath.dirname(relative), specifier))
                        imported_asset = await client.get(f"/moss-go/assets/{revision}/{imported}")
                        assert imported_asset.status == 200, f"{relative} imports missing {imported}"
                checked += 1
            system = await (await client.get(API + "/system")).json()
            assert system["connected"] is False and system["default_language"] == "en"
            examples = (await (await client.get(API + "/examples")).json())["items"]
            assert len(examples) == 3
            for item in examples:
                picture = await client.get(item["image_url"])
                assert picture.status == 200
                digest = item["image_url"].rsplit("/", 1)[-1].removesuffix(".png")
                assert hashlib.sha256(await picture.read()).hexdigest() == digest
            route = API + "/examples/" + examples[0]["id"] + "/use"
            first = await client.post(route, json={})
            assert first.status == 201
            image = await first.json()
            second = await (await client.post(route, json={})).json()
            assert image["id"] == second["id"] and image["kind"] == "input"
            assert (await (await client.get(API + "/jobs")).json())["items"] == []
            print(json.dumps({"installed_version": moss_go.__version__, "assets_checked": checked,
                              "examples_checked": len(examples), "comfy_connected": False,
                              "model_jobs_created": 0, "package_path": str(installed)}))
        finally:
            await client.close()


if __name__ == "__main__":
    asyncio.run(main())
