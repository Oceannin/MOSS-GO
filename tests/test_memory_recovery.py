import asyncio
import io
import sqlite3
import tempfile
import unittest

from PIL import Image

from moss_go.recipes import preview_recipe, recipe_for_job
from moss_go.runner import Runner, memory_failure, system_memory_failure
from moss_go.settings import validate_request
from moss_go.store import Store


def picture():
    out = io.BytesIO()
    Image.new("RGB", (64, 64), "blue").save(out, "PNG")
    return out.getvalue()


class MemorySimulation:
    client_id = "memory-test"

    def __init__(self, failed_id, *, system_memory=False):
        self.failed_id = failed_id
        self.prompts = {}
        self.finished = asyncio.Event()
        self.system_memory = system_memory

    async def inventory(self):
        return {"models": {"diffusion_models": ["moss_image_sft_int8_convrot.safetensors"],
                           "text_encoders": ["qwen3.5_9b_w4a8_gptq.safetensors"], "vae": ["flux2-vae_small.safetensors"]}}

    async def json(self, path, data=None):
        if path == "/prompt":
            prompt_id = f"native-{len(self.prompts)}"
            self.prompts[prompt_id] = data["extra_data"]["extra_pnginfo"]["moss_go"]["job_id"]
            return {"prompt_id": prompt_id}
        if path.startswith("/history/"):
            prompt_id = path.split("/")[-1]
            if self.prompts[prompt_id] == self.failed_id:
                return {prompt_id: {"status": {"messages": [["execution_error", {"exception_type": "MemoryError" if self.system_memory else "torch.OutOfMemoryError", "exception_message": "CPUAllocator cannot allocate memory" if self.system_memory else "CUDA out of memory; private-path fixture"}]]}}}
            return {prompt_id: {"status": {"completed": True}, "outputs": {"save": {"images": [{"filename": "fixture.png"}]}}}}
        raise AssertionError(path)

    async def image(self, descriptor):
        self.finished.set()
        return picture()


class MemoryRecoveryTests(unittest.IsolatedAsyncioTestCase):
    async def test_ram_failure_does_not_recommend_moving_more_weights_to_cpu(self):
        with tempfile.TemporaryDirectory() as root:
            store = Store(root)
            jobs = store.create_batch(validate_request({"mode": "create", "prompt": "A cup.", "profile": "balanced", "variants": 2}))["jobs"]
            other = store.create_batch(validate_request({"mode": "create", "prompt": "Another task.", "variants": 1}))["jobs"][0]
            native = MemorySimulation(jobs[0]["id"], system_memory=True)
            runner = Runner(store, native)
            runner.start()
            try:
                await asyncio.wait_for(native.finished.wait(), timeout=2)
            finally:
                await runner.close()
            failed = store.job(jobs[0]["id"])
            held = store.job(jobs[1]["id"])
            self.assertEqual(failed["error_code"], "system_memory_exhausted")
            self.assertEqual(held["error_code"], "batch_system_memory_hold")
            self.assertEqual(failed["settings"]["profile"], "balanced")
            self.assertEqual(store.job(other["id"])["status"], "done")
            self.assertIn("may not help", failed["error"])
    async def test_memory_failure_holds_only_its_unsubmitted_siblings_and_preserves_work(self):
        with tempfile.TemporaryDirectory() as root:
            store = Store(root)
            source = store.add_image(picture())
            original = validate_request({"mode": "create", "prompt": "A blue ceramic cup.", "variants": 4,
                                         "profile": "balanced", "seed": 55})
            batch = store.create_batch(original)
            completed, failed, *held = batch["jobs"]
            store.update_job(completed["id"], status="done", output_id=source["id"])
            other = store.create_batch(validate_request({"mode": "create", "prompt": "An unrelated job.", "variants": 1}))["jobs"][0]
            native = MemorySimulation(failed["id"])
            runner = Runner(store, native)
            runner.start()
            try:
                await asyncio.wait_for(native.finished.wait(), timeout=2)
            finally:
                await runner.close()
            rejected = store.job(failed["id"])
            self.assertEqual((rejected["status"], rejected["error_code"]), ("error", "out_of_memory"))
            self.assertNotIn("private-path", rejected["error"])
            for job in held:
                result = store.job(job["id"])
                self.assertEqual((result["status"], result["error_code"], result["prompt_id"]), ("interrupted", "batch_memory_hold", None))
                self.assertEqual(result["settings"], job["settings"])
            self.assertEqual(store.job(other["id"])["status"], "done")
            self.assertEqual(store.job(completed["id"])["output_id"], source["id"])
            self.assertEqual(len(native.prompts), 2)  # One failure, one unrelated take; no automatic OOM retries.
            self.assertEqual(store.job(failed["id"])["settings"], failed["settings"])
            self.assertIsNotNone(store.execution(failed["id"]))
            recipe = recipe_for_job(store, failed["id"])
            recipe["settings"]["profile"] = "economy"
            preview = preview_recipe(store, recipe)
            recovered = validate_request(preview["settings"])
            self.assertEqual((recovered["profile"], recovered["seed"], recovered["prompt"], recovered["variants"], recovered["scenes"]),
                             ("economy", failed["settings"]["seed"], failed["settings"]["prompt"], 1, []))
            self.assertLess(recovered["width"] * recovered["height"], failed["settings"]["width"] * failed["settings"]["height"])
            self.assertEqual(len(store.jobs()), 5)  # A preview is never a new launch.

    async def test_batch_hold_never_changes_completed_cancelled_or_submitted_takes(self):
        with tempfile.TemporaryDirectory() as root:
            store = Store(root)
            jobs = store.create_batch(validate_request({"mode": "create", "prompt": "A cup.", "variants": 4}))["jobs"]
            store.update_job(jobs[0]["id"], status="done")
            store.update_job(jobs[1]["id"], status="cancelled")
            store.update_job(jobs[2]["id"], status="queued", prompt_id="already-submitted")
            store.hold_pending_batch(jobs[0]["batch_id"])
            self.assertEqual([store.job(job["id"])["status"] for job in jobs], ["done", "cancelled", "queued", "interrupted"])


class MemoryClassificationTests(unittest.TestCase):
    def test_failure_and_sibling_hold_are_one_transaction(self):
        with tempfile.TemporaryDirectory() as root:
            store = Store(root)
            jobs = store.create_batch(validate_request({"mode": "create", "prompt": "A cup.", "variants": 2}))["jobs"]
            store.update_job(jobs[0]["id"], status="queued", prompt_id="native-failed")
            with store.connect() as db:
                db.execute("CREATE TRIGGER reject_hold BEFORE UPDATE ON jobs WHEN new.error_code='batch_memory_hold' BEGIN SELECT RAISE(ABORT,'synthetic hold failure'); END")
            with self.assertRaises(sqlite3.IntegrityError):
                store.fail_job(jobs[0]["id"], error="Out of memory", code="out_of_memory")
            self.assertEqual([store.job(job["id"])["status"] for job in jobs], ["queued", "pending"])
            self.assertIsNone(store.job(jobs[0]["id"])["error_code"])
            with store.connect() as db:
                db.execute("DROP TRIGGER reject_hold")
            store.fail_job(jobs[0]["id"], error="Out of memory", code="out_of_memory")
            self.assertEqual([store.job(job["id"])["status"] for job in jobs], ["error", "interrupted"])
            # A delayed error for a cancelled take cannot hold its siblings.
            other = store.create_batch(validate_request({"mode": "create", "prompt": "Other batch.", "variants": 2}))["jobs"]
            store.update_job(other[0]["id"], status="cancelled")
            store.fail_job(other[0]["id"], error="Late failure", code="out_of_memory")
            self.assertEqual(store.job(other[1]["id"])["status"], "pending")

    def test_shape_and_allocator_api_errors_are_not_mislabeled_as_oom(self):
        for message in ("memory shape mismatch", "allocator API is not supported", "Invalid allocation parameter"):
            self.assertFalse(memory_failure({"exception_type": "ValueError", "exception_message": message}))
        for error in ({"exception_type": "torch.OutOfMemoryError"}, {"exception_type": "MemoryError"},
                      {"exception_message": "CUDA out of memory"}, {"exception_message": "std::bad_alloc"}):
            self.assertTrue(memory_failure(error))
        self.assertTrue(system_memory_failure({"exception_type": "MemoryError"}))
        self.assertTrue(system_memory_failure({"exception_message": "DefaultCPUAllocator: not enough memory"}))
        self.assertTrue(memory_failure({"exception_message": "The paging file is too small"}))
        self.assertFalse(system_memory_failure({"exception_type": "torch.OutOfMemoryError", "exception_message": "CUDA out of memory"}))

    def test_schema_one_upgrade_preserves_jobs_artifacts_and_execution_snapshots(self):
        with tempfile.TemporaryDirectory() as root:
            store = Store(root)
            source = store.add_image(picture())
            job = store.create_batch(validate_request({"mode": "create", "prompt": "An archived cup.", "variants": 1}))["jobs"][0]
            store.save_execution(job["id"], graph={"original": True}, models={"model": "original"}, settings=job["settings"])
            store.update_job(job["id"], status="done", output_id=source["id"])
            # Recreate the exact prior jobs layout: all other columns unchanged.
            with store.connect() as db:
                db.execute("ALTER TABLE jobs DROP COLUMN error_code")
                db.execute("UPDATE metadata SET value='1' WHERE key='schema_version'")
            upgraded = Store(root)
            result = upgraded.job(job["id"])
            self.assertEqual((result["status"], result["output_id"], result["settings"]), ("done", source["id"], job["settings"]))
            self.assertIsNone(result["error_code"])
            self.assertEqual(upgraded.execution(job["id"])["graph"], {"original": True})
            self.assertEqual(upgraded.image_path(source["id"]).read_bytes(), picture())
            self.assertEqual(Store(root).job(job["id"]), result)  # Upgrade is idempotent.
