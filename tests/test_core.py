import io
import json
from pathlib import Path
import tempfile
import unittest

from PIL import Image

from moss_go.characters import import_character, random_character, validate_character
from moss_go.comfy import combo_options
from moss_go.errors import StudioError
from moss_go.settings import SEED_MAX, validate_request
from moss_go.store import Store
from moss_go.workflows import build_workflow, resolve_models


def settings(**changes):
    return validate_request({"mode": "create", "prompt": "An original clockmaker in a workshop.", **changes})


def png(color="red", size=(64, 64), mode="RGB"):
    out = io.BytesIO()
    Image.new(mode, size, color).save(out, format="PNG")
    return out.getvalue()


class SettingsTests(unittest.TestCase):
    def test_reference_requires_an_input(self):
        with self.assertRaises(StudioError):
            validate_request({"prompt": "Same character, new scene."})

    def test_unknown_and_private_fields_are_rejected(self):
        for field in ("adult", "genitals", "prompt_graph", "file_path"):
            with self.subTest(field=field), self.assertRaises(StudioError):
                settings(**{field: True})

    def test_seed_does_not_accept_boolean_or_unsafe_integer(self):
        for seed in (True, -1, SEED_MAX + 1, float("nan"), 1.5):
            with self.subTest(seed=seed), self.assertRaises(StudioError):
                settings(seed=seed)

    def test_memory_profile_changes_effective_size(self):
        self.assertLess(settings(profile="economy")["width"] * settings(profile="economy")["height"], settings(profile="balanced")["width"] * settings(profile="balanced")["height"])

    def test_nonfinite_strength_and_lora_strength_rejected(self):
        with self.assertRaises(StudioError):
            settings(strength=float("inf"))
        with self.assertRaises(StudioError):
            settings(loras=[{"name": "test.safetensors", "strength": float("nan")}])

    def test_path_traversal_in_lora_rejected(self):
        with self.assertRaises(StudioError):
            settings(loras=[{"name": "../secret.safetensors", "strength": 1}])


class CharacterTests(unittest.TestCase):
    def test_catalog_is_an_allowlist(self):
        with self.assertRaises(StudioError):
            validate_character({"adult": True})

    def test_import_produces_an_explicit_clean_preview(self):
        result = import_character({"hair": "short silver hair", "adult": True, "genitals": {"value": "legacy"}})
        self.assertEqual(result["character"], {"hair": "short silver hair"})
        self.assertEqual(result["removed_fields"], ["adult", "genitals"])
        self.assertTrue(result["requires_review"])

    def test_randomization_is_reproducible_and_respects_locks(self):
        self.assertEqual(random_character(42), random_character(42))
        self.assertEqual(random_character(42, {"hair": "short silver hair"})["hair"], "short silver hair")


class WorkflowTests(unittest.TestCase):
    models = {"model": "moss.safetensors", "clip": "clip.safetensors", "vae": "vae.safetensors"}

    def test_create_has_no_reference_mask_upscale_or_detailer_dependencies(self):
        graph = build_workflow(settings(), self.models)
        kinds = {node["class_type"] for node in graph.values()}
        self.assertFalse({"LoadImage", "FaceDetailer", "MossGoReferencePatch", "SetLatentNoiseMask", "ImageUpscaleWithModel"} & kinds)
        self.assertEqual(graph["save"]["class_type"], "SaveImage")

    def test_masked_refine_reuses_one_mask_for_noise_and_compositing(self):
        graph = build_workflow(settings(mode="refine", engine="moss", input_id="a" * 32, mask_id="b" * 32), self.models, input_image="input.png", mask_image="mask.png")
        self.assertEqual(graph["noise_mask"]["inputs"]["mask"], graph["composite"]["inputs"]["mask"])
        self.assertEqual(graph["composite"]["inputs"]["destination"], ["base_size", 0])

    def test_all_graph_links_resolve(self):
        for options in ({}, {"mode": "refine", "input_id": "a" * 32, "mask_id": "b" * 32}, {"engine": "flux-klein"}):
            graph = build_workflow(settings(**options), self.models, input_image="input.png", mask_image="mask.png")
            for node in graph.values():
                for value in node["inputs"].values():
                    if isinstance(value, list):
                        self.assertIn(value[0], graph)

    def test_both_native_combo_schema_formats_are_supported(self):
        legacy = {"input": {"required": {"name": [["a", "b"]]}}}
        modern = {"input": {"required": {"name": ["COMBO", {"options": ["a", "b"]}]}}}
        self.assertEqual(combo_options(legacy, "name"), combo_options(modern, "name"))

    def test_high_precision_never_silently_falls_back_to_quantized_weights(self):
        inv = {"models": {"diffusion_models": ["moss_image_sft_int8_convrot.safetensors"], "text_encoders": ["qwen3.5_9b_w4a8_gptq.safetensors"], "vae": ["flux2-vae_small.safetensors"]}}
        self.assertFalse(resolve_models("moss", inv, "balanced")[1])
        self.assertIn("model", [item["role"] for item in resolve_models("moss", inv, "quality")[1]])


class StoreTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.store = Store(self.temp.name)

    def tearDown(self):
        self.temp.cleanup()

    def test_images_are_deduplicated_and_persisted(self):
        image = self.store.add_image(png())
        self.assertEqual(image["id"], self.store.add_image(png())["id"])
        self.assertEqual(Store(self.temp.name).artifact(image["id"])["sha256"], image["sha256"])

    def test_mask_extrema_support_empty_mask_shortcut(self):
        image = self.store.add_image(png(0, mode="L"), "mask")
        self.assertEqual((image["minimum"], image["maximum"]), (0, 0))

    def test_request_lookup_recovers_a_batch_older_than_the_visible_history_window(self):
        request = settings(request_id="d" * 32, variants=1)
        original = self.store.create_batch(request)
        for index in range(7):
            self.store.create_batch(settings(request_id=f"{index:032x}", variants=4, scenes=["One", "Two", "Three", "Four"]))
        self.assertNotIn(original["jobs"][0]["id"], {job["id"] for job in self.store.jobs()})
        self.assertEqual(Store(self.temp.name).batch_for_request(request["request_id"]), original)
        self.assertIsNone(self.store.batch_for_request("e" * 32))

    def test_terminal_jobs_cannot_be_revived_by_delayed_observations(self):
        job = self.store.create_batch(settings(variants=1))["jobs"][0]
        result = self.store.update_job(job["id"], status="error", error="Original failure")
        self.assertEqual(self.store.update_job(job["id"], status="running", error=None), result)

    def test_same_request_never_creates_duplicate_jobs(self):
        request = settings(request_id="c" * 32)
        first = self.store.create_batch(request)
        second = self.store.create_batch(request)
        self.assertEqual(first, second)
        self.assertEqual(len(self.store.jobs()), 4)

    def test_changed_request_with_same_id_conflicts(self):
        self.store.create_batch(settings(request_id="c" * 32))
        with self.assertRaises(StudioError) as error:
            self.store.create_batch(settings(request_id="c" * 32, seed=43))
        self.assertEqual(error.exception.status, 409)

    def test_batch_seeds_wrap_and_scenes_remain_distinct(self):
        batch = self.store.create_batch(settings(seed=SEED_MAX, variants=2, scenes=["First scene", "Second scene"]))
        self.assertEqual([job["settings"]["seed"] for job in batch["jobs"]], [SEED_MAX, 0, 1, 2])
        self.assertIn("Second scene", batch["jobs"][2]["settings"]["prompt"])

    def test_catalog_does_not_accept_path_identifiers(self):
        with self.assertRaises(StudioError):
            self.store.image_path("../private")

    def test_execution_snapshot_is_immutable(self):
        job = self.store.create_batch(settings(variants=1))["jobs"][0]
        self.store.save_execution(job["id"], graph={"sample": "original"}, models={"model": "first"}, settings=job["settings"])
        self.store.save_execution(job["id"], graph={"sample": "replacement"}, models={"model": "second"}, settings=job["settings"])
        self.assertEqual(self.store.execution(job["id"])["models"]["model"], "first")


if __name__ == "__main__":
    unittest.main()
