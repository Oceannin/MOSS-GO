import io
import json
import tempfile
import unittest
import zipfile

from PIL import Image

from moss_go.errors import StudioError
from moss_go.recipes import export_bundle, import_bundle, preview_recipe, recipe_for_job
from moss_go.settings import validate_request
from moss_go.store import Store


def image(color):
    out = io.BytesIO()
    Image.new("RGB", (64, 96), color).save(out, "PNG")
    return out.getvalue()


class RecipeTests(unittest.TestCase):
    def setUp(self):
        self.source_root = tempfile.TemporaryDirectory()
        self.target_root = tempfile.TemporaryDirectory()
        self.source, self.target = Store(self.source_root.name), Store(self.target_root.name)
        source = self.source.add_image(image("red"))
        result = self.source.add_image(image("blue"), "result")
        settings = validate_request({"mode": "reference", "input_id": source["id"], "engine": "flux-klein", "prompt": "A new scene.", "variants": 1})
        job = self.source.create_batch(settings)["jobs"][0]
        self.job = self.source.update_job(job["id"], status="done", output_id=result["id"])

    def tearDown(self):
        self.source_root.cleanup()
        self.target_root.cleanup()

    def test_pack_roundtrip_restores_sources_without_creating_generation_jobs(self):
        raw = export_bundle(self.source, [self.job["id"]])
        preview = import_bundle(self.target, raw)
        self.assertTrue(preview["requires_review"])
        self.assertFalse(self.target.jobs())
        self.assertFalse(preview["items"][0]["missing_inputs"])
        with Image.open(self.target.image_path(preview["items"][0]["settings"]["input_id"])) as picture:
            self.assertEqual(picture.getpixel((0, 0)), (255, 0, 0))

    def test_export_includes_contact_sheet_and_recipe(self):
        with zipfile.ZipFile(io.BytesIO(export_bundle(self.source, [self.job["id"]]))) as archive:
            self.assertIn("contact-sheet.jpg", archive.namelist())
            self.assertEqual(json.loads(archive.read("manifest.json"))["recipes"][0]["recipe_version"], 1)

    def test_json_preview_identifies_inputs_not_present_on_this_installation(self):
        preview = preview_recipe(self.target, recipe_for_job(self.source, self.job["id"]))
        self.assertEqual(preview["missing_inputs"], ["input_id"])

    def test_import_rejects_traversal_and_does_not_extract_files(self):
        out = io.BytesIO()
        with zipfile.ZipFile(out, "w") as archive:
            archive.writestr("../unexpected.txt", "unsafe")
            archive.writestr("manifest.json", "{}")
        with self.assertRaises(StudioError):
            import_bundle(self.target, out.getvalue())
        self.assertFalse(self.target.jobs())

    def test_corrupt_image_hash_is_rejected(self):
        raw = export_bundle(self.source, [self.job["id"]])
        out = io.BytesIO()
        with zipfile.ZipFile(io.BytesIO(raw)) as source, zipfile.ZipFile(out, "w") as target:
            for name in source.namelist():
                content = source.read(name)
                if name.startswith("images/"):
                    content = image("green")
                target.writestr(name, content)
        with self.assertRaises(StudioError):
            import_bundle(self.target, out.getvalue())

    def test_recipe_does_not_reuse_a_foreign_parent_or_request_id(self):
        recipe = recipe_for_job(self.source, self.job["id"])
        recipe["settings"]["parent_id"] = "a" * 32
        prepared = preview_recipe(self.source, recipe)["settings"]
        self.assertNotIn("parent_id", prepared)
        self.assertNotIn("request_id", prepared)

    def test_refinement_recipe_does_not_treat_its_small_inference_canvas_as_an_output_size(self):
        recipe = recipe_for_job(self.source, self.job["id"])
        recipe["settings"].update(mode="refine", width=64, height=96, source_width=64, source_height=96)
        prepared = preview_recipe(self.source, recipe)["settings"]
        self.assertNotIn("size", prepared)
        self.assertEqual(prepared["input_id"], self.job["settings"]["input_id"])
        self.assertEqual(prepared["mode"], "refine")

    def test_a_scene_pack_take_replays_only_its_own_scene_and_seed(self):
        settings = validate_request({"mode": "create", "prompt": "Same character.",
                                     "scenes": ["At the station.", "In the workshop."],
                                     "variants": 2, "seed": 100})
        original = self.source.create_batch(settings)["jobs"][-1]
        prepared = preview_recipe(self.source, recipe_for_job(self.source, original["id"]))["settings"]
        replay = self.source.create_batch(validate_request(prepared))["jobs"]
        self.assertEqual(len(replay), 1)
        self.assertEqual(replay[0]["settings"]["prompt"], "Same character.\nIn the workshop.")
        self.assertEqual(replay[0]["settings"]["seed"], 103)
        self.assertEqual(self.source.job(original["id"])["settings"]["scenes"], settings["scenes"])


if __name__ == "__main__":
    unittest.main()
