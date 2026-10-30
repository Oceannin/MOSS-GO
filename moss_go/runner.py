"""A durable serial worker. Closing the page does not stop generation."""

import asyncio
import logging
import time

from .characters import compose_prompt
from .errors import StudioError
from .store import TERMINAL
from .settings import refinement_dimensions
from .refinement import region_from_mask
from .workflows import build_workflow, resolve_models

log = logging.getLogger(__name__)


def memory_failure(error):
    kind = str(error.get("exception_type", "")).rsplit(".", 1)[-1]
    message = str(error.get("exception_message", "")).lower()
    return kind in {"OutOfMemoryError", "MemoryError"} or any(
        phrase in message for phrase in ("out of memory", "not enough memory", "cannot allocate memory",
                                         "failed to allocate", "memory allocation failed", "std::bad_alloc", "paging file is too small"))


def system_memory_failure(error):
    kind = str(error.get("exception_type", "")).rsplit(".", 1)[-1]
    message = str(error.get("exception_message", "")).lower()
    return kind == "MemoryError" or any(name in message for name in ("defaultcpuallocator", "cpuallocator", "std::bad_alloc", "paging file is too small"))


class Runner:
    def __init__(self, store, comfy):
        self.store, self.comfy = store, comfy
        self.wake = asyncio.Event()
        self.task = None
        self.current = None

    def start(self):
        self.task = asyncio.create_task(self.run(), name="moss-go-worker")
        self.wake.set()

    async def close(self):
        if self.task:
            self.task.cancel()
            try:
                await self.task
            except asyncio.CancelledError:
                pass

    async def submit(self, settings):
        settings = dict(settings)
        for key in ("input_id", "mask_id"):
            if settings.get(key):
                self.store.image_path(settings[key])
        if settings.get("parent_id"):
            self.store.job(settings["parent_id"])
        if settings.get("mask_id") and self.store.artifact(settings["mask_id"])["kind"] != "mask":
            raise StudioError("Choose a painted mask.", field="mask_id")
        if settings.get("mask_id"):
            source, mask = self.store.artifact(settings["input_id"]), self.store.artifact(settings["mask_id"])
            if (source["width"], source["height"]) != (mask["width"], mask["height"]):
                raise StudioError("The mask and source must have the same dimensions.", field="mask_id")
        if settings["mode"] == "refine":
            source = self.store.artifact(settings["input_id"])
            settings["source_width"], settings["source_height"] = source["width"], source["height"]
            settings["width"], settings["height"] = refinement_dimensions(source["width"], source["height"], settings["profile"])
            settings["format"] = "portrait" if source["height"] > source["width"] else "landscape" if source["width"] > source["height"] else "square"
            if settings["engine"] == "flux-klein" and settings.get("mask_id"):
                region = await asyncio.to_thread(region_from_mask, self.store.image_path(settings["mask_id"]), source["width"], source["height"], settings["feather"])
                if region:
                    settings["edit_region"] = region
                    settings["width"], settings["height"] = refinement_dimensions(region["width"], region["height"], settings["profile"], focus=True)
        inv = await self.comfy.inventory()
        models, missing = resolve_models(settings["engine"], inv, settings["profile"])
        if missing:
            raise StudioError("Install missing models: " + ", ".join(item["filename"] for item in missing), code="models_missing", status=409)
        for lora in settings["loras"]:
            if lora["name"] not in inv["models"]["loras"]:
                raise StudioError("A selected LoRA is no longer installed.", field="loras")
        draft = build_workflow(settings, models, input_image="validation.png" if settings.get("input_id") else None, mask_image="validation-mask.png" if settings.get("mask_id") else None)
        absent = sorted({node["class_type"] for node in draft.values()} - inv["nodes"])
        if absent:
            raise StudioError("Install required nodes: " + ", ".join(absent), code="nodes_missing", status=409)
        batch = self.store.create_batch(settings)
        self.wake.set()
        return batch

    async def cancel(self, job_id):
        job = self.store.job(job_id)
        if job["status"] in TERMINAL:
            return job
        if job["status"] == "pending":
            return self.store.update_job(job_id, status="cancelled")
        # A targeted bridge checks both prompt id and provenance; never use global /interrupt.
        if not job["prompt_id"]:
            raise StudioError("The job is being accepted. Try cancelling again in a moment.", code="job_submitting", status=409)
        response = await self.comfy.json("/moss-go/bridge/cancel", {"prompt_id": job["prompt_id"], "job_id": job_id})
        if response.get("cancelled"):
            return self.store.update_job(job_id, status="cancelled")
        return self.store.job(job_id)

    async def run(self):
        while True:
            await self.wake.wait()
            self.wake.clear()
            for job in self.store.jobs(active=True):
                if self.store.job(job["id"])["status"] in TERMINAL:
                    continue
                self.current = job["id"]
                try:
                    await self.execute(job)
                except asyncio.CancelledError:
                    raise
                except StudioError as exc:
                    if exc.code in {"comfy_unavailable", "submission_uncertain"}:
                        self.wake.set()
                        await asyncio.sleep(2)
                        break
                    self.store.fail_job(job["id"], error=str(exc), code=exc.code)
                except Exception:
                    log.exception("Job %s failed", job["id"])
                    self.store.update_job(job["id"], status="error", error="Generation stopped unexpectedly. Your input and settings are saved.")
                finally:
                    self.current = None

    async def reconcile_submission(self, job):
        # A lost POST response can precede the queue's visibility. Require several
        # successful negative observations, without ever posting a second prompt.
        for attempt in range(4):
            current = self.store.job(job["id"])
            if current["status"] in TERMINAL:
                return current
            queue = await self.comfy.json("/queue")
            history = await self.comfy.json("/history?max_items=200")
            items = queue.get("queue_running", []) + queue.get("queue_pending", [])
            items += [entry["prompt"] for entry in history.values() if "prompt" in entry]
            match = next((item for item in items if item[3].get("extra_pnginfo", {}).get("moss_go", {}).get("job_id") == job["id"]), None)
            if match:
                return self.store.update_job(job["id"], status="queued", prompt_id=match[1])
            if attempt < 3:
                await asyncio.sleep(2)
        return self.store.update_job(job["id"], status="interrupted", error="The previous launch could not be reconciled. Review the queue before retrying.")

    async def execute(self, job):
        job = self.store.job(job["id"])
        if job["status"] in TERMINAL:
            return
        settings = job["settings"]
        if job["status"] == "pending":
            if settings.get("mask_id") and self.store.artifact(settings["mask_id"])["maximum"] == 0:
                self.store.update_job(job["id"], status="done", output_id=settings["input_id"], elapsed=0.)
                return
            inv = await self.comfy.inventory()
            models, missing = resolve_models(settings["engine"], inv, settings["profile"])
            if missing:
                raise StudioError("A required model is no longer installed.", code="models_missing")
            paths = {}
            for field in ("input_id", "mask_id"):
                if settings.get(field):
                    paths[field] = await self.comfy.upload(self.store.image_path(settings[field]).read_bytes(), settings[field] + ".png")
            effective = dict(settings)
            effective["prompt"] = compose_prompt(settings["prompt"], settings["character"])
            graph = build_workflow(effective, models, input_image=paths.get("input_id"), mask_image=paths.get("mask_id"), prefix="MOSS-GO/" + job["id"])
            if self.store.job(job["id"])["status"] == "cancelled":
                return
            self.store.save_execution(job["id"], graph=graph, models=models, settings=effective)
            if self.store.update_job(job["id"], status="submitting")["status"] != "submitting":
                return
            result = await self.comfy.json("/prompt", {"prompt": graph, "client_id": self.comfy.client_id, "extra_data": {"extra_pnginfo": {"moss_go": {"job_id": job["id"], "recipe_version": 1, "settings": effective}}}})
            prompt_id = result.get("prompt_id") if isinstance(result, dict) else None
            if not prompt_id:
                raise StudioError("The launch response was incomplete. Checking the existing queue before retrying.", code="submission_uncertain", status=503)
            job = self.store.update_job(job["id"], status="queued", prompt_id=prompt_id)
        elif job["status"] == "submitting" and not job["prompt_id"]:
            job = await self.reconcile_submission(job)
            if job["status"] in TERMINAL:
                return
        started, missing_count = time.monotonic(), 0
        while True:
            if self.store.job(job["id"])["status"] in TERMINAL:
                return
            try:
                history = await self.comfy.json("/history/" + job["prompt_id"])
                entry = history.get(job["prompt_id"])
                if entry:
                    events = entry.get("status", {}).get("messages", [])
                    error = next((detail for name, detail in events if name == "execution_error"), None)
                    interrupted = any(name == "execution_interrupted" for name, _ in events)
                    if interrupted:
                        self.store.update_job(job["id"], status="interrupted", error="Generation was interrupted in ComfyUI.")
                        return
                    if error:
                        if memory_failure(error):
                            if system_memory_failure(error):
                                raise StudioError("System RAM ran out. Your work is saved and remaining takes were held. Free system memory before retrying; Memory saver moves the encoder to RAM and may not help.", code="system_memory_exhausted")
                            raise StudioError("There was not enough memory. Your input and settings are saved. Remaining takes in this batch were held; load a take in Memory saver before retrying.", code="out_of_memory")
                        raise StudioError("ComfyUI could not finish this image. Your input and settings are saved.", code="generation_failed")
                    images = entry.get("outputs", {}).get("save", {}).get("images", [])
                    if images:
                        artifact = self.store.add_image(await self.comfy.image(images[0]), "result")
                        self.store.update_job(job["id"], status="done", output_id=artifact["id"], elapsed=round(time.monotonic() - started, 2))
                        return
                    if entry.get("status", {}).get("completed"):
                        raise StudioError("The job finished without an output image.", code="output_missing")
                queue = await self.comfy.json("/queue")
                running = queue.get("queue_running", [])
                pending = queue.get("queue_pending", [])
                if any(item[1] == job["prompt_id"] for item in running):
                    missing_count = 0
                    self.store.update_job(job["id"], status="running")
                elif any(item[1] == job["prompt_id"] for item in pending):
                    missing_count = 0
                else:
                    missing_count += 1
                    if missing_count >= 4:
                        self.store.update_job(job["id"], status="interrupted", error="The job is no longer in ComfyUI. Its settings are saved; retry when ready.")
                        return
            except StudioError as exc:
                if exc.code != "comfy_unavailable":
                    raise
                # An observation timeout is not proof of termination. Keep the same prompt id.
            await asyncio.sleep(2)
