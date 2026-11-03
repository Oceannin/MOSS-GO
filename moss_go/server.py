"""The standalone studio web application."""

import asyncio
import io
import json
import logging
from pathlib import Path
import zipfile

from aiohttp import web

from . import __version__
from .assistant import PromptAssistant
from .characters import CHARACTER_FIELDS, CHARACTER_PRESETS, import_character, random_character, render_character
from .comfy import ComfyClient
from .errors import StudioError
from .examples import example, example_bytes, public_examples
from .runner import Runner
from .recipes import MAX_BUNDLE_BYTES, export_bundle, import_bundle, preview_recipe, recipe_for_job
from .readiness import engine_readiness, hardware_summary
from .settings import PROFILES, validate_request
from .store import MAX_IMAGE_BYTES, Store
from .web_assets import WebAssets

HERE = Path(__file__).resolve().parent
API = "/moss-go/api/v1"
log = logging.getLogger(__name__)
STUDIO = web.AppKey("studio", dict)
CSP = "default-src 'self'; img-src 'self' blob: data:; style-src 'self' 'unsafe-inline'; script-src 'self'; connect-src 'self'; font-src 'self'; object-src 'none'; base-uri 'self'; frame-ancestors 'none'"


@web.middleware
async def boundaries(request, handler):
    origin = request.headers.get("Origin")
    if request.method not in {"GET", "HEAD", "OPTIONS"} and origin and origin != f"{request.scheme}://{request.host}":
        return web.json_response(StudioError("Requests must come from this studio.", code="origin_rejected", status=403).as_dict(), status=403)
    try:
        response = await handler(request)
    except StudioError as exc:
        response = web.json_response(exc.as_dict(), status=exc.status)
    except (json.JSONDecodeError, UnicodeDecodeError):
        response = web.json_response(StudioError("The request could not be read.").as_dict(), status=400)
    except web.HTTPException:
        raise
    except Exception:
        log.exception("Request failed: %s %s", request.method, request.path)
        response = web.json_response(StudioError("The request could not be completed. Your saved work is unchanged.", code="internal_error", status=500).as_dict(), status=500)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "same-origin"
    response.headers.setdefault("Content-Security-Policy", CSP)
    if request.path.startswith(API):
        response.headers["Cache-Control"] = "no-store"
    elif request.path.startswith("/moss-go/assets/"):
        response.headers.setdefault("Cache-Control", "no-cache")
    return response


async def body(request):
    if request.content_length is not None and request.content_length > 128_000:
        raise StudioError("This request is too large.", status=413)
    data = await request.json()
    if not isinstance(data, dict):
        raise StudioError("Expected an object.")
    return data


def create_app(*, data_root, comfy_url="http://127.0.0.1:8188", ollama_url="http://127.0.0.1:11434"):
    app = web.Application(middlewares=[boundaries], client_max_size=MAX_BUNDLE_BYTES + 1024 * 1024)
    store, comfy = Store(data_root), ComfyClient(comfy_url)
    runner = Runner(store, comfy)
    assistant = PromptAssistant(ollama_url)
    app[STUDIO] = {"store": store, "comfy": comfy, "runner": runner}
    routes = web.RouteTableDef()
    assets = WebAssets(HERE / "web")

    def public_job(job):
        return {**job, "progress": comfy.progress.get(job.get("prompt_id"), {}), "output_url": f"{API}/images/{job['output_id']}" if job.get("output_id") else None}

    @routes.get("/")
    async def root(request):
        raise web.HTTPFound("/moss-go/")

    @routes.get("/moss-go/")
    async def index(request):
        revision = assets.snapshot()
        html = (HERE / "web" / "index.html").read_text("utf-8").replace("/moss-go/assets/", f"/moss-go/assets/{revision}/")
        response = web.Response(text=html, content_type="text/html")
        response.headers["Content-Security-Policy"] = CSP
        response.headers["Cache-Control"] = "no-cache"
        return response

    @routes.get("/moss-go/assets/{revision:[a-f0-9]{20}}/{path:.*}")
    async def versioned_asset(request):
        try:
            content, content_type = assets.read(request.match_info["revision"], request.match_info["path"])
        except KeyError:
            raise web.HTTPNotFound()
        return web.Response(body=content, content_type=content_type,
                            headers={"Cache-Control": "public,max-age=31536000,immutable"})

    @routes.get(API + "/system")
    async def system(request):
        try:
            inventory = await comfy.inventory(refresh=request.query.get("refresh") == "1")
            engines = engine_readiness(inventory)
            sys = inventory["system"]
            result = {"connected": True, "devices": inventory["devices"], "ram_total": sys.get("ram_total"), "ram_free": sys.get("ram_free"), "comfy_version": sys.get("comfyui_version"), "engines": engines,
                      "hardware": hardware_summary(inventory["devices"], sys),
                      "refine_ready": any(engine["modes"]["refine"]["ready"] for engine in engines.values())}
        except StudioError as exc:
            result = {"connected": False, "error": str(exc), "devices": [], "engines": {}}
        return web.json_response({"version": __version__, "default_language": "en", "profiles": PROFILES, **result})

    @routes.get(API + "/jobs")
    async def jobs(request):
        return web.json_response({"items": [public_job(job) for job in store.jobs()]})

    @routes.post(API + "/jobs")
    async def submit(request):
        if assistant.lock.locked():
            raise StudioError("Wait for the prompt assistant to finish before starting an image.", code="assistant_busy", status=409)
        data = await body(request)
        stats = await comfy.json("/system_stats", timeout=5)
        gpu = next((device for device in stats.get("devices", []) if device.get("type") == "cuda"), {})
        settings = validate_request(data, total_vram=gpu.get("vram_total"))
        result = await runner.submit(settings)
        return web.json_response({"id": result["id"], "jobs": [public_job(job) for job in result["jobs"]]}, status=202)

    @routes.get(API + "/jobs/{job_id}")
    async def job(request):
        job_id = request.match_info["job_id"]
        return web.json_response({**public_job(store.job(job_id)), "execution": store.execution(job_id)})

    @routes.post(API + "/jobs/{job_id}/cancel")
    async def cancel(request):
        return web.json_response(public_job(await runner.cancel(request.match_info["job_id"])))

    @routes.post(API + "/images")
    async def upload(request):
        multipart = await request.multipart()
        part = await multipart.next()
        if part is None or part.name not in {"image", "mask"}:
            raise StudioError("Choose an image to upload.")
        raw = bytearray()
        while chunk := await part.read_chunk():
            raw.extend(chunk)
            if len(raw) > MAX_IMAGE_BYTES:
                raise StudioError("Choose an image smaller than 25 MB.", status=413)
        artifact = await asyncio.to_thread(store.add_image, bytes(raw), "mask" if part.name == "mask" else "input")
        return web.json_response({**artifact, "url": f"{API}/images/{artifact['id']}"}, status=201)

    @routes.get(API + "/images/{image_id}")
    async def image(request):
        return web.FileResponse(store.image_path(request.match_info["image_id"]), headers={"Cache-Control": "private,max-age=31536000,immutable"})

    @routes.get(API + "/images/{image_id}/metadata")
    async def image_metadata(request):
        return web.json_response(store.artifact(request.match_info["image_id"]))

    @routes.get(API + "/characters")
    async def characters(request):
        return web.json_response({"version": 1, "fields": CHARACTER_FIELDS, "presets": CHARACTER_PRESETS})

    @routes.get(API + "/examples")
    async def examples(request):
        return web.json_response({"items": public_examples(API)})

    @routes.get(API + "/examples/{example_id}/{digest:[a-f0-9]{64}}.png")
    async def example_image(request):
        item = example(request.match_info["example_id"])
        if request.match_info["digest"] != item["sha256"]:
            raise web.HTTPNotFound()
        content = await asyncio.to_thread(example_bytes, item["id"])
        return web.Response(body=content, content_type="image/png",
                            headers={"Cache-Control": "private,max-age=31536000,immutable"})

    @routes.post(API + "/examples/{example_id}/use")
    async def use_example(request):
        if await body(request):
            raise StudioError("The example does not accept generation settings.")
        content = await asyncio.to_thread(example_bytes, request.match_info["example_id"])
        artifact = await asyncio.to_thread(store.add_image, content, "input")
        return web.json_response({**artifact, "url": f"{API}/images/{artifact['id']}"}, status=201)

    @routes.post(API + "/characters/preview")
    async def character_preview(request):
        data = await body(request)
        if set(data) - {"character", "randomize", "seed", "fields"}:
            raise StudioError("Unknown character preview setting.")
        if "randomize" in data and not isinstance(data["randomize"], bool):
            raise StudioError("Choose whether to randomize the character.", field="randomize")
        character = data.get("character", {})
        if data.get("randomize"):
            seed = data.get("seed", 42)
            if isinstance(seed, bool) or not isinstance(seed, int) or not 0 <= seed <= 2**53 - 1:
                raise StudioError("Choose a valid seed.", field="seed")
            character = random_character(seed, character, fields=data.get("fields"))
        return web.json_response({"character": character, "text": render_character(character)})

    @routes.post(API + "/characters/import")
    async def character_import(request):
        return web.json_response(import_character(await body(request)))

    @routes.get(API + "/assistant")
    async def assistant_status(request):
        return web.json_response(await assistant.status())

    @routes.post(API + "/prompts/enhance")
    async def enhance(request):
        data = await body(request)
        if set(data) - {"prompt", "character"}:
            raise StudioError("Unknown assistant setting.")
        try:
            queue = await comfy.json("/queue")
        except StudioError as exc:
            if exc.code != "comfy_unavailable":
                raise
            queue = {}
        if store.jobs(active=True) or queue.get("queue_running") or queue.get("queue_pending"):
            raise StudioError("Finish image generation before using the local assistant.", code="generation_busy", status=409)
        return web.json_response(await assistant.enhance(data.get("prompt", ""), data.get("character", {})))

    @routes.get(API + "/jobs/{job_id}/recipe")
    async def recipe(request):
        job = store.job(request.match_info["job_id"])
        content = recipe_for_job(store, job["id"])
        return web.json_response(content, headers={"Content-Disposition": 'attachment; filename="moss-go-recipe.json"'})

    @routes.get(API + "/jobs/{job_id}/bundle")
    async def job_bundle(request):
        content = await asyncio.to_thread(export_bundle, store, [request.match_info["job_id"]])
        return web.Response(body=content, content_type="application/zip", headers={"Content-Disposition": 'attachment; filename="moss-go-take.zip"'})

    @routes.get(API + "/batches/{batch_id}/bundle")
    async def batch_bundle(request):
        batch = store.batch(request.match_info["batch_id"])
        content = await asyncio.to_thread(export_bundle, store, [job["id"] for job in batch["jobs"]])
        return web.Response(body=content, content_type="application/zip", headers={"Content-Disposition": 'attachment; filename="moss-go-scene-pack.zip"'})

    @routes.post(API + "/recipes/import")
    async def recipe_import(request):
        multipart = await request.multipart()
        part = await multipart.next()
        if part is None or part.name != "bundle":
            raise StudioError("Choose a MOSS GO ZIP pack.")
        raw = bytearray()
        while chunk := await part.read_chunk():
            raw.extend(chunk)
            if len(raw) > MAX_BUNDLE_BYTES:
                raise StudioError("Choose a pack smaller than 100 MB.", status=413)
        return web.json_response(await asyncio.to_thread(import_bundle, store, bytes(raw)))

    @routes.post(API + "/recipes/preview")
    async def recipe_preview(request):
        return web.json_response(preview_recipe(store, await body(request)))

    @routes.get(API + "/requests/{request_id}")
    async def request_status(request):
        batch = store.batch_for_request(request.match_info["request_id"])
        if batch:
            batch = {**batch, "jobs": [public_job(job) for job in batch["jobs"]]}
        return web.json_response({"batch": batch})

    @routes.get(API + "/health")
    async def health(request):
        return web.json_response({"ok": True, "version": __version__})

    app.add_routes(routes)
    app.router.add_static("/moss-go/assets/", HERE / "web", show_index=False)

    async def lifetime(application):
        await comfy.start()
        runner.start()
        yield
        await runner.close()
        await comfy.close()

    app.cleanup_ctx.append(lifetime)
    return app
