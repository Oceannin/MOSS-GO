import io
import tempfile
import unittest

from PIL import Image, ImageDraw

from moss_go.runner import Runner
from moss_go.refinement import selection_region
from moss_go.settings import PROFILES, refinement_dimensions, validate_request
from moss_go.store import Store
from moss_go.workflows import build_workflow


FLUX_MODELS = {"model": "flux-2-klein-4b-fp8.safetensors", "clip": "qwen_3_4b.safetensors", "vae": "flux2-vae.safetensors"}


def settings(**extra):
    return validate_request({"mode": "refine", "engine": "flux-klein", "input_id": "a" * 32,
                             "mask_id": "b" * 32, "prompt": "Replace the badge with a blue crescent moon.", "variants": 1, **extra})


class RefinementWorkflowTests(unittest.TestCase):
    def test_flux_edits_condition_on_the_input_and_composite_only_the_selected_region(self):
        graph = build_workflow(settings(), FLUX_MODELS, input_image="input.png", mask_image="mask.png")
        self.assertEqual(graph["reference_positive"]["class_type"], "ReferenceLatent")
        self.assertEqual(graph["latent"]["class_type"], "EmptyFlux2LatentImage")
        self.assertNotIn("noise_mask", graph)
        self.assertEqual(graph["composite"]["inputs"]["mask"], ["feather", 0])

    def test_original_pixels_are_the_composite_destination_even_when_inference_is_smaller(self):
        effective = {**settings(), "source_width": 1536, "source_height": 2048}
        for engine in ("flux-klein", "moss"):
            with self.subTest(engine=engine):
                graph = build_workflow({**effective, "engine": engine}, FLUX_MODELS, input_image="input.png", mask_image="mask.png")
                self.assertEqual(graph["composite"]["inputs"]["destination"], ["source", 0])
                self.assertEqual(graph["restore_size"]["inputs"]["width"], 1536)
                self.assertEqual(graph["restore_size"]["inputs"]["height"], 2048)
                self.assertEqual(graph["feather"]["inputs"]["width"], 1536)
                if engine == "moss":
                    self.assertEqual(graph["noise_mask"]["inputs"]["mask"], graph["composite"]["inputs"]["mask"])

    def test_canvas_respects_the_profile_budget_and_preserves_regular_aspect_ratios(self):
        for profile, options in PROFILES.items():
            for width, height in [(768, 1024), (4000, 2000), (64, 64), (16000, 100)]:
                with self.subTest(profile=profile, size=(width, height)):
                    w, h = refinement_dimensions(width, height, profile)
                    self.assertLessEqual(w * h, options["max_pixels"])
                    self.assertTrue(w % 16 == h % 16 == 0)
                    self.assertTrue(64 <= w <= 2048 and 64 <= h <= 2048)
            w, h = refinement_dimensions(4000, 2000, profile)
            self.assertAlmostEqual(w / h, 2, delta=.05)

    def test_full_frame_api_edit_without_a_mask_also_restores_the_original_size(self):
        effective = {**settings(mask_id=None), "source_width": 1536, "source_height": 2048}
        graph = build_workflow(effective, FLUX_MODELS, input_image="input.png")
        self.assertNotIn("composite", graph)
        self.assertEqual(graph["save"]["inputs"]["images"], ["restore_size", 0])
        self.assertEqual(graph["restore_size"]["inputs"]["height"], 2048)

    def test_focused_edit_returns_to_its_original_coordinates_and_feathers_before_cropping(self):
        region = {"x": 235, "y": 200, "width": 240, "height": 240}
        effective = {**settings(), "width": 768, "height": 768, "source_width": 768, "source_height": 1024, "edit_region": region}
        graph = build_workflow(effective, FLUX_MODELS, input_image="input.png", mask_image="mask.png")
        self.assertEqual(graph["reference_size"]["inputs"]["image"], ["focus_image", 0])
        self.assertEqual(graph["focus_mask"]["inputs"]["mask"], ["feather", 0])
        self.assertEqual(graph["composite"]["inputs"]["destination"], ["source", 0])
        self.assertEqual(graph["composite"]["inputs"]["x"], 235)
        self.assertEqual(graph["composite"]["inputs"]["y"], 200)
        self.assertEqual(graph["restore_size"]["inputs"]["width"], 240)

    def test_focus_has_context_stays_inside_edges_and_keeps_the_memory_budget(self):
        self.assertIsNone(selection_region(768, 1024, None, 8))
        self.assertIsNone(selection_region(768, 1024, (0, 0, 768, 1024), 8))
        for bounds in ((330, 295, 380, 345), (0, 0, 20, 20), (750, 1000, 768, 1024)):
            region = selection_region(768, 1024, bounds, 8)
            self.assertLessEqual(region["x"], bounds[0])
            self.assertLessEqual(region["y"], bounds[1])
            self.assertGreaterEqual(region["x"] + region["width"], bounds[2])
            self.assertGreaterEqual(region["y"] + region["height"], bounds[3])
            self.assertLessEqual(region["x"] + region["width"], 768)
            self.assertLessEqual(region["y"] + region["height"], 1024)
            for profile, options in PROFILES.items():
                w, h = refinement_dimensions(region["width"], region["height"], profile, focus=True)
                self.assertLessEqual(w * h, options["max_pixels"])
                self.assertEqual((w, h), (768, 768))


class ReadyFlux:
    async def inventory(self):
        return {"models": {"diffusion_models": [FLUX_MODELS["model"]], "text_encoders": [FLUX_MODELS["clip"]], "vae": [FLUX_MODELS["vae"]], "loras": []},
                "nodes": {"UNETLoader", "CLIPLoader", "VAELoader", "LoadImage", "CLIPTextEncode", "ConditioningZeroOut", "ImageScaleToTotalPixels", "VAEEncode", "ReferenceLatent", "EmptyFlux2LatentImage", "LoadImageMask", "MossGoFeatherMask", "RandomNoise", "KSamplerSelect", "CFGGuider", "Flux2Scheduler", "SamplerCustomAdvanced", "VAEDecodeTiled", "ImageCompositeMasked", "SaveImage", "ImageScale", "ImageCrop", "CropMask"}}


class RefinementPreparationTests(unittest.IsolatedAsyncioTestCase):
    async def test_tiny_selection_uses_its_context_without_mutating_the_source_or_request(self):
        with tempfile.TemporaryDirectory() as root:
            store = Store(root)
            def add(picture, kind):
                output = io.BytesIO()
                picture.save(output, "PNG")
                return store.add_image(output.getvalue(), kind)["id"]
            image = add(Image.new("RGB", (768, 1024), "red"), "input")
            mask = Image.new("L", (768, 1024))
            ImageDraw.Draw(mask).rectangle((330, 295, 379, 344), fill=255)
            mask_id = add(mask, "mask")
            original = settings(input_id=image, mask_id=mask_id)
            runner = Runner(store, ReadyFlux())
            batch = await runner.submit(original)
            self.assertEqual(batch["id"], (await runner.submit(original))["id"])
            effective = batch["jobs"][0]["settings"]
            self.assertEqual(effective["edit_region"], {"x": 235, "y": 200, "width": 240, "height": 240})
            self.assertEqual((effective["width"], effective["height"]), (768, 768))
            self.assertEqual((effective["source_width"], effective["source_height"]), (768, 1024))
            self.assertNotIn("edit_region", original)

    async def test_submit_derives_original_size_from_artifacts_and_remains_idempotent(self):
        with tempfile.TemporaryDirectory() as root:
            store = Store(root)
            def add(mode, kind, color):
                output = io.BytesIO()
                Image.new(mode, (600, 400), color).save(output, "PNG")
                return store.add_image(output.getvalue(), kind)["id"]
            image, mask = add("RGB", "input", "red"), add("L", "mask", 255)
            original = settings(input_id=image, mask_id=mask, format="portrait")
            runner = Runner(store, ReadyFlux())
            first = await runner.submit(original)
            second = await runner.submit(original)
            self.assertEqual(first["id"], second["id"])
            effective = first["jobs"][0]["settings"]
            self.assertEqual((effective["source_width"], effective["source_height"]), (600, 400))
            self.assertEqual((effective["width"], effective["height"]), (592, 400))
            self.assertEqual(effective["format"], "landscape")
            self.assertNotIn("source_width", original)
