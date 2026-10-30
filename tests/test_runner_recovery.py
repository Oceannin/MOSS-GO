import io
import tempfile
import unittest
from unittest.mock import AsyncMock, patch

from PIL import Image

from moss_go.errors import StudioError
from moss_go.runner import Runner
from moss_go.settings import validate_request
from moss_go.store import Store
from moss_go.characters import CHARACTER_PRESETS, compose_prompt


PROMPT = "7b8f91cb-825e-42e4-9d7e-a31067e2f559"


class NativeSimulation:
    client_id = "test-client"

    def __init__(self, job_id):
        self.job_id = job_id
        self.posts = 0
        self.observations = 0
        self.downloads = 0
        self.visibility_delay = 0
        self.download_failures = 0
        self.history_failures = 0
        self.never_accepted = False
        self.on_download = None
        self.acceptance_reply = None

    async def inventory(self):
        return {"models": {"diffusion_models": ["moss_image_sft_int8_convrot.safetensors"],
                           "text_encoders": ["qwen3.5_9b_w4a8_gptq.safetensors"],
                           "vae": ["flux2-vae_small.safetensors"]}}

    def item(self):
        return [0, PROMPT, {}, {"extra_pnginfo": {"moss_go": {"job_id": self.job_id}}}]

    async def json(self, path, data=None):
        if path == "/prompt":
            self.posts += 1
            if self.acceptance_reply is not None:
                return self.acceptance_reply
            raise StudioError("Lost response", code="submission_uncertain")
        if path == "/queue":
            self.observations += 1
            visible = not self.never_accepted and self.observations > self.visibility_delay
            return {"queue_running": [self.item()] if visible else [], "queue_pending": []}
        if path == "/history?max_items=200":
            return {}
        if path == "/history/" + PROMPT:
            if self.history_failures:
                self.history_failures -= 1
                raise StudioError("Offline", code="comfy_unavailable")
            return {PROMPT: {"status": {"completed": True}, "outputs": {"save": {"images": [{"filename": "result.png", "type": "output"}]}}}}
        raise AssertionError(path)

    async def image(self, descriptor):
        self.downloads += 1
        if self.download_failures:
            self.download_failures -= 1
            raise StudioError("Lost transfer", code="comfy_unavailable")
        if self.on_download:
            self.on_download()
        output = io.BytesIO()
        Image.new("RGB", (64, 64), "blue").save(output, "PNG")
        return output.getvalue()


class RecoveryTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.store = Store(self.folder.name)
        self.job = self.store.create_batch(validate_request({"mode": "create", "prompt": "A blue ceramic cup.", "variants": 1}))["jobs"][0]
        self.native = NativeSimulation(self.job["id"])
        self.sleep = patch("moss_go.runner.asyncio.sleep", new_callable=AsyncMock)
        self.sleep.start()

    async def asyncTearDown(self):
        self.sleep.stop()
        self.folder.cleanup()

    async def test_lost_acceptance_and_process_restart_recover_one_existing_prompt(self):
        with self.assertRaises(StudioError) as caught:
            await Runner(self.store, self.native).execute(self.job)
        self.assertEqual(caught.exception.code, "submission_uncertain")
        self.assertEqual(self.store.job(self.job["id"])["status"], "submitting")
        # The accepted prompt is initially absent from both queue and history.
        self.native.visibility_delay = 2
        reopened = Store(self.folder.name)
        await Runner(reopened, self.native).execute(reopened.job(self.job["id"]))
        result = reopened.job(self.job["id"])
        self.assertEqual((self.native.posts, self.native.observations), (1, 3))
        self.assertEqual((result["status"], result["prompt_id"]), ("done", PROMPT))
        self.assertTrue(reopened.image_path(result["output_id"]).exists())
        self.assertIsNotNone(reopened.execution(result["id"]))

    async def test_offline_observations_and_lost_download_keep_the_same_prompt(self):
        queued = self.store.update_job(self.job["id"], status="queued", prompt_id=PROMPT)
        self.native.history_failures = 2
        self.native.download_failures = 1
        await Runner(self.store, self.native).execute(queued)
        self.assertEqual(self.store.job(self.job["id"])["status"], "done")
        self.assertEqual((self.native.posts, self.native.downloads), (0, 2))

    async def test_an_incomplete_acknowledgement_is_reconciled_instead_of_discarded(self):
        self.native.acceptance_reply = {}
        with self.assertRaises(StudioError) as caught:
            await Runner(self.store, self.native).execute(self.job)
        self.assertEqual(caught.exception.code, "submission_uncertain")
        await Runner(self.store, self.native).execute(self.store.job(self.job["id"]))
        self.assertEqual(self.store.job(self.job["id"])["status"], "done")
        self.assertEqual(self.native.posts, 1)

    async def test_successful_negative_observations_end_as_interrupted_without_resubmitting(self):
        uncertain = self.store.update_job(self.job["id"], status="submitting")
        self.native.never_accepted = True
        await Runner(self.store, self.native).execute(uncertain)
        result = self.store.job(self.job["id"])
        self.assertEqual(result["status"], "interrupted")
        self.assertIsNone(result["prompt_id"])
        self.assertEqual((self.native.posts, self.native.observations), (0, 4))

    async def test_a_delayed_completion_cannot_overwrite_an_accepted_cancellation(self):
        queued = self.store.update_job(self.job["id"], status="queued", prompt_id=PROMPT)
        self.native.on_download = lambda: self.store.update_job(self.job["id"], status="cancelled")
        await Runner(self.store, self.native).execute(queued)
        result = self.store.job(self.job["id"])
        self.assertEqual(result["status"], "cancelled")
        self.assertIsNone(result["output_id"])

    async def test_a_stale_pending_handle_cannot_launch_a_cancelled_job(self):
        self.store.update_job(self.job["id"], status="cancelled")
        await Runner(self.store, self.native).execute(self.job)
        self.assertEqual(self.native.posts, 0)

    async def test_compiled_workflow_keeps_canonical_character_traits_without_duplicate_injection(self):
        character = next(item["character"] for item in CHARACTER_PRESETS if item["id"] == "nia")
        description = "A pilot holding one closed notebook at a tram stop."
        job = self.store.create_batch(validate_request({"mode": "create", "prompt": description, "character": character, "variants": 1}))["jobs"][0]
        native = NativeSimulation(job["id"])
        with self.assertRaises(StudioError):
            await Runner(self.store, native).execute(job)
        execution = self.store.execution(job["id"])
        effective = execution["graph"]["positive"]["inputs"]["text"]
        self.assertEqual(effective, compose_prompt(description, character))
        for trait in character.values():
            self.assertEqual(effective.casefold().count(trait.casefold()), 1, trait)
        self.assertEqual(self.store.job(job["id"])["settings"]["character"], character)
