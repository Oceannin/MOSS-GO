"""Native ComfyUI transport. No browser canvas imports or global queue hooks."""

import asyncio
import json
import time
import uuid
from urllib.parse import urlparse

import aiohttp

from .errors import StudioError


def combo_options(node, field):
    spec = node.get("input", {}).get("required", {}).get(field, [])
    if spec and isinstance(spec[0], list):
        return spec[0]
    if len(spec) > 1 and spec[0] == "COMBO" and isinstance(spec[1], dict):
        return spec[1].get("options", [])
    return []


class ComfyClient:
    def __init__(self, base_url):
        parsed = urlparse(base_url)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment:
            raise ValueError("Use an http(s) ComfyUI URL without credentials or query parameters.")
        self.base = base_url.rstrip("/")
        self.session = None
        self._schemas = None
        self._schemas_at = 0
        self.client_id = uuid.uuid4().hex
        self.progress = {}
        self.observer = None

    async def start(self):
        self.session = aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=30))
        self.observer = asyncio.create_task(self.observe(), name="comfy-progress")

    async def close(self):
        if self.observer:
            self.observer.cancel()
            try:
                await self.observer
            except asyncio.CancelledError:
                pass
        if self.session:
            await self.session.close()

    async def observe(self):
        while True:
            try:
                current = None
                async with self.session.ws_connect(self.base + "/ws", params={"clientId": self.client_id}, heartbeat=20) as socket:
                    async for message in socket:
                        if message.type != aiohttp.WSMsgType.TEXT:
                            continue
                        event = json.loads(message.data)
                        data = event.get("data", {})
                        prompt = data.get("prompt_id") or current
                        if event.get("type") == "execution_start":
                            current = prompt
                        if prompt and event.get("type") in {"executing", "progress", "execution_start"}:
                            previous = self.progress.get(prompt, {})
                            if event.get("type") == "executing":
                                previous = {}
                            self.progress[prompt] = {**previous, **{k: data[k] for k in ("node", "value", "max") if k in data}}
            except (aiohttp.ClientError, asyncio.TimeoutError, ValueError):
                pass
            await asyncio.sleep(2)

    async def json(self, path, data=None, *, timeout=None):
        try:
            method = "POST" if data is not None else "GET"
            async with self.session.request(method, self.base + path, json=data, timeout=aiohttp.ClientTimeout(total=timeout or 30)) as response:
                value = await response.json(content_type=None)
                if response.status >= 400:
                    # Preserve validation details for the caller, without a server traceback.
                    message = value.get("error", {}) if isinstance(value, dict) else {}
                    message = message.get("message", "ComfyUI could not accept this request.") if isinstance(message, dict) else str(message)
                    raise StudioError(message, code="comfy_rejected", status=502)
                return value
        except (aiohttp.ClientError, asyncio.TimeoutError, ValueError) as exc:
            self._schemas = None
            if path == "/prompt" and data is not None:
                raise StudioError("The launch response was lost. Checking the existing queue before retrying.", code="submission_uncertain", status=503) from exc
            raise StudioError("ComfyUI is not responding. Start it, then reconnect.", code="comfy_unavailable", status=503) from exc

    async def schemas(self, *, refresh=False):
        if self._schemas is None or refresh or time.monotonic() - self._schemas_at > 60:
            self._schemas = await self.json("/object_info")
            self._schemas_at = time.monotonic()
        return self._schemas

    async def upload(self, content, filename):
        body = aiohttp.FormData()
        body.add_field("image", content, filename=filename, content_type="image/png")
        body.add_field("type", "input")
        body.add_field("subfolder", "moss-go")
        body.add_field("overwrite", "true")
        try:
            async with self.session.post(self.base + "/upload/image", data=body) as response:
                value = await response.json()
                if response.status >= 400:
                    raise StudioError("The input image could not be sent to ComfyUI.", code="upload_failed", status=502)
                return "/".join(filter(None, [value.get("subfolder", ""), value["name"]]))
        except (aiohttp.ClientError, asyncio.TimeoutError, ValueError, KeyError) as exc:
            raise StudioError("The image transfer was interrupted. Reconnecting to ComfyUI.", code="comfy_unavailable", status=503) from exc

    async def image(self, descriptor):
        params = {key: descriptor[key] for key in ("filename", "subfolder", "type") if key in descriptor}
        try:
            async with self.session.get(self.base + "/view", params=params) as response:
                if response.status >= 500:
                    raise StudioError("The finished image is temporarily unavailable. Reconnecting to ComfyUI.", code="comfy_unavailable", status=503)
                if response.status != 200:
                    raise StudioError("The generated image could not be downloaded.", code="output_missing", status=502)
                return await response.read()
        except (aiohttp.ClientError, asyncio.TimeoutError) as exc:
            raise StudioError("The image download was interrupted. Reconnecting to ComfyUI.", code="comfy_unavailable", status=503) from exc

    async def inventory(self, *, refresh=False):
        stats, schemas = await asyncio.gather(self.json("/system_stats", timeout=5), self.schemas(refresh=refresh))
        def options(node, field):
            return combo_options(schemas.get(node, {}), field)
        models = {
            "diffusion_models": list(dict.fromkeys(options("UNETLoader", "unet_name") + options("MOSSImageUNETLoader", "unet_name"))),
            "text_encoders": list(dict.fromkeys(options("CLIPLoader", "clip_name") + options("MOSSImageCLIPLoader", "clip_name"))),
            "vae": options("VAELoader", "vae_name"),
            "loras": options("LoraLoaderModelOnly", "lora_name"),
        }
        return {"connected": True, "system": stats.get("system", {}), "devices": stats.get("devices", []), "models": models, "nodes": set(schemas)}
