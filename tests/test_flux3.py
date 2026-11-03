"""Control/metadata regression tests; these are not evidence of GPU execution."""

import io
import hashlib
import json
import math
import tempfile
import unittest
import zipfile
import urllib.request
from unittest.mock import patch

from PIL import Image

from moss_go.errors import StudioError
from moss_go.model_setup import download_file
from moss_go.readiness import engine_readiness, required_nodes
from moss_go.recipes import export_bundle, preview_recipe, recipe_for_job
from moss_go.runner import Runner
from moss_go.settings import validate_request
from moss_go.store import Store
from moss_go.workflows import MODEL_ROLES, build_workflow, resolve_models


def settings(mode="create", **changes):
    return validate_request({"mode": mode, "prompt": "An original courier in a railway station.",
                             "input_id": "a" * 32 if mode != "create" else None,
                             "mask_id": "b" * 32 if mode == "refine" else None,
                             "variants": 1, **changes})


def inventory():
    models = {}
    for category, aliases in MODEL_ROLES["flux3-klein"].values():
        models.setdefault(category, []).append(aliases[0])
    return {"models": models, "clip_types": ["flux2", "flux3"],
            "nodes": set().union(*(required_nodes("flux3-klein", mode) for mode in ("create", "reference", "refine"))),
            "system": {"comfyui_version": "0.41.2"}}


class Flux3Tests(unittest.TestCase):
    def test_default_engine_and_distilled_parameters_apply_to_all_three_modes(self):
        for mode in ("create", "reference", "refine"):
            checked = settings(mode)
            self.assertEqual(checked["engine"], "flux3-klein")
            self.assertEqual(checked["steps"], 16)
            self.assertTrue(checked["prompt_upsampler"])
        for value in (True, 3, 17, 4.5):
            with self.subTest(value=value), self.assertRaises(StudioError):
                settings(flux3_steps=value)
        with self.assertRaises(StudioError):
            settings(prompt_upsampler="false")

    def test_native_flux3_path_uses_vision_conditioning_and_actual_prompt_generation(self):
        models, _ = resolve_models("flux3-klein", inventory())
        graph = build_workflow(settings("reference"), models, input_image="mira.png")
        self.assertEqual(graph["clip"]["inputs"]["type"], "flux3")
        self.assertEqual(graph["upsample"]["class_type"], "TextGenerate")
        self.assertEqual(graph["upsample"]["inputs"]["image"], ["source", 0])
        self.assertEqual(graph["positive"]["inputs"]["text"], ["expanded_prompt", 0])
        self.assertEqual(graph["expanded_prompt"]["inputs"]["source"], ["upsample", 0])
        self.assertEqual(graph["reference"]["class_type"], "ReferenceMultiLatent")
        self.assertEqual(graph["reference"]["inputs"]["images.image0"], ["source", 0])
        self.assertEqual(graph["sample"]["inputs"]["cfg"], 1.)
        self.assertAlmostEqual(graph["sampling"]["inputs"]["max_shift"], math.log(16))
        self.assertNotIn("Flux2Scheduler", {n["class_type"] for n in graph.values()})

    def test_readiness_detects_old_loader_even_when_every_node_name_exists(self):
        inv = inventory()
        inv["clip_types"] = ["flux2"]
        status = engine_readiness(inv)["flux3-klein"]
        self.assertFalse(status["modes"]["create"]["ready"])
        self.assertIn("flux3", status["missing_capabilities"][0])

    def test_explicit_full_caption_bypass_removes_only_upsampler_dependencies(self):
        inv = inventory()
        inv["models"]["text_encoders"] = ["qwen3vl_4b_int8_convrot.safetensors"]
        inv["nodes"].remove("TextGenerate")
        status = engine_readiness(inv)["flux3-klein"]["profiles"]["balanced"]
        self.assertFalse(status["modes"]["reference"]["ready"])
        self.assertTrue(status["caption_only"]["modes"]["reference"]["ready"])
        models, missing = resolve_models("flux3-klein", inv, prompt_upsampler=False)
        self.assertEqual(missing, [])
        graph = build_workflow(settings(prompt_upsampler=False), models)
        self.assertNotIn("upsample", graph)
        self.assertEqual(graph["expanded_prompt"]["inputs"]["source"], settings()["prompt"])

    def test_legacy_vae_is_never_substituted_for_the_pinned_flux3_vae(self):
        inv = inventory()
        inv["models"]["vae"] = ["flux2-vae.safetensors"]
        _, missing = resolve_models("flux3-klein", inv)
        self.assertEqual([x["filename"] for x in missing], ["flux3-vae.safetensors"])
        _, missing = resolve_models("flux3-klein", inventory(), "quality")
        self.assertIn("flux3-image-klein-bf16.safetensors", [x["filename"] for x in missing])

    def test_focus_transform_feathers_before_crop_and_composites_into_original(self):
        effective = {**settings("refine"), "source_width": 1536, "source_height": 2048,
                     "edit_region": {"x": 240, "y": 300, "width": 320, "height": 400},
                     "width": 512, "height": 640}
        models, _ = resolve_models("flux3-klein", inventory())
        graph = build_workflow(effective, models, input_image="source.png", mask_image="mask.png")
        self.assertEqual(graph["upsample"]["inputs"]["image"], ["focus_image", 0])
        self.assertEqual(graph["feather"]["inputs"]["width"], 1536)
        self.assertEqual(graph["focus_mask"]["inputs"]["mask"], ["feather", 0])
        self.assertEqual(graph["restore_size"]["inputs"]["width"], 320)
        self.assertEqual(graph["restore_size"]["inputs"]["height"], 400)
        self.assertEqual(graph["composite"]["inputs"]["destination"], ["source", 0])
        self.assertEqual((graph["composite"]["inputs"]["x"], graph["composite"]["inputs"]["y"]), (240, 300))

    def test_export_keeps_observed_prompt_and_immutable_actual_graph(self):
        with tempfile.TemporaryDirectory() as folder:
            store = Store(folder)
            job = store.create_batch(settings())["jobs"][0]
            models, _ = resolve_models("flux3-klein", inventory())
            graph = build_workflow(job["settings"], models)
            store.save_execution(job["id"], graph=graph, models=models, settings=job["settings"])
            store.save_execution_result(job["id"], {"expanded_prompt": "Observed full caption."})
            store.save_execution_result(job["id"], {"expanded_prompt": "Must not overwrite."})
            raw = io.BytesIO()
            Image.new("RGB", (64, 64), "blue").save(raw, "PNG")
            output = store.add_image(raw.getvalue(), "result")
            store.update_job(job["id"], status="done", output_id=output["id"])
            recipe = recipe_for_job(store, job["id"])
            self.assertEqual(recipe["execution"]["runtime"]["expanded_prompt"], "Observed full caption.")
            preview = preview_recipe(store, recipe)
            self.assertTrue(preview["settings"]["prompt_upsampler"])
            self.assertEqual(preview["settings"]["flux3_steps"], 16)
            with zipfile.ZipFile(io.BytesIO(export_bundle(store, [job["id"]]))) as bundle:
                self.assertEqual(json.loads(bundle.read(f"workflows/{job['id']}.api.json")), graph)

    def test_gated_download_fails_before_transfer_without_authentication(self):
        with tempfile.TemporaryDirectory() as folder, patch("moss_go.model_setup.hub_token", return_value=None):
            item = {"category": "vae", "filename": "test.safetensors", "repository": "owner/model",
                    "revision": "a" * 40, "path": "test.safetensors", "size": 4,
                    "sha256": "b" * 64, "requires_hf_access": True}
            with patch("urllib.request.urlopen") as transfer, self.assertRaisesRegex(ValueError, "Accept the model terms"):
                download_file(folder, item, opener=transfer)
            transfer.assert_not_called()

    def test_hub_credential_is_not_forwarded_to_a_download_redirect(self):
        class Response(io.BytesIO):
            status = 200
            headers = {"Content-Length": "4"}
        seen = []
        def transfer(request, **kwargs):
            seen.append(request)
            return Response(b"data")
        with tempfile.TemporaryDirectory() as folder, patch("moss_go.model_setup.hub_token", return_value="fixture-secret"):
            item = {"category": "vae", "filename": "test.safetensors", "repository": "owner/model",
                    "revision": "a" * 40, "path": "test.safetensors", "size": 4,
                    "sha256": hashlib.sha256(b"data").hexdigest(), "requires_hf_access": True}
            download_file(folder, item, opener=transfer, report=lambda _: None)
        self.assertEqual(seen[0].get_header("Authorization"), "Bearer fixture-secret")
        redirected = urllib.request.HTTPRedirectHandler().redirect_request(
            seen[0], None, 302, "", {}, "https://download.example/model")
        self.assertIsNone(redirected.get_header("Authorization"))
        self.assertNotIn("fixture-secret", redirected.full_url)


class Flux3ErrorTests(unittest.IsolatedAsyncioTestCase):
    async def test_incompatible_runtime_cannot_submit_or_fall_back(self):
        with tempfile.TemporaryDirectory() as folder:
            store = Store(folder)
            job = store.create_batch(settings())["jobs"][0]
            class OldRuntime:
                posts = 0
                async def inventory(self):
                    return {**inventory(), "clip_types": ["flux2"]}
                async def json(self, *args):
                    self.posts += 1
                    raise AssertionError("No native job should be submitted")
            native = OldRuntime()
            with self.assertRaises(StudioError) as failure:
                await Runner(store, native).execute(job)
            self.assertEqual(failure.exception.code, "runtime_incompatible")
            self.assertEqual(native.posts, 0)
            self.assertEqual(store.job(job["id"])["settings"]["engine"], "flux3-klein")
