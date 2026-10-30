import tempfile
import unittest

from aiohttp.test_utils import TestClient, TestServer

from moss_go.characters import CHARACTER_FIELDS, CHARACTER_PRESETS, import_character, random_character, render_character, validate_character
from moss_go.errors import StudioError
from moss_go.server import API, create_app


class CharacterPresetTests(unittest.TestCase):
    def test_exported_preset_values_and_pins_survive_import(self):
        original = {"format": "moss-go-character", "version": 1, "character": {"hair": "two long purple braids", "skin_tone": "dark brown skin", "footwear": "teal ankle boots"}, "locks": ["hair", "footwear", "hair"]}
        preview = import_character(original)
        self.assertEqual(preview["character"], original["character"])
        self.assertEqual(preview["locks"], ["hair", "footwear"])
        self.assertFalse(preview["requires_review"])

    def test_legacy_wrappers_report_discarded_metadata_and_invalid_pins(self):
        preview = import_character({"character": {"hair": "short silver hair", "unsupported": True}, "locks": ["hair", "unsupported", {"nested": True}], "enable_flag": True})
        self.assertEqual(preview["character"], {"hair": "short silver hair"})
        self.assertEqual(preview["locks"], ["hair"])
        self.assertEqual(preview["removed_fields"], ["locks.invalid", "locks.unsupported", "metadata.enable_flag", "unsupported"])
        self.assertTrue(preview["requires_review"])

    def test_unknown_portable_versions_are_not_silently_reinterpreted(self):
        for version in (2, True, "1"):
            with self.subTest(version=version), self.assertRaises(StudioError):
                import_character({"format": "moss-go-character", "version": version, "character": {}})

    def test_every_bundled_preset_is_valid_and_pins_only_selected_traits(self):
        self.assertEqual(len(CHARACTER_FIELDS), 12)
        for preset in CHARACTER_PRESETS:
            with self.subTest(preset=preset["id"]):
                self.assertEqual(validate_character(preset["character"]), preset["character"])
                self.assertFalse(import_character({"character": preset["character"], "locks": preset["locks"]})["removed_fields"])
                self.assertTrue(preset["label_ru"])
        for field in CHARACTER_FIELDS.values():
            self.assertEqual(len(field["values"]), len(set(field["values"])))
            self.assertTrue(field["label_ru"])
            self.assertEqual(set(field["values"]), set(field["labels_ru"]))

    def test_randomization_preserves_many_pins_and_can_leave_optional_fields_unset(self):
        fixed = {"hair": "two long purple braids", "eyes": "amber eyes", "skin_tone": "dark brown skin"}
        first = random_character(11, fixed, fields=["outfit", "expression"])
        self.assertEqual(set(first), {*fixed, "outfit", "expression"})
        self.assertEqual({key: first[key] for key in fixed}, fixed)
        self.assertEqual(random_character(11, fixed, fields=[]), fixed)
        for invalid in (["unknown"], "hair", [None]):
            with self.subTest(invalid=invalid), self.assertRaises(StudioError):
                random_character(11, fixed, fields=invalid)

    def test_prompt_order_is_stable_and_does_not_contain_pin_metadata(self):
        self.assertEqual(render_character({"eyes": "green eyes", "role": "a courier", "hair": "short silver hair"}), "a courier, short silver hair, green eyes")


class CharacterApiTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.data = tempfile.TemporaryDirectory()
        # A closed loopback port prevents these CPU tests from reaching a real ComfyUI.
        self.client = TestClient(TestServer(create_app(data_root=self.data.name, comfy_url="http://127.0.0.1:1"), host="127.0.0.1"))
        await self.client.start_server()

    async def asyncTearDown(self):
        await self.client.close()
        self.data.cleanup()

    async def test_preview_and_import_do_not_enqueue_generations(self):
        schema = await (await self.client.get(API + "/characters")).json()
        self.assertEqual(len(schema["presets"]), 3)
        preset = schema["presets"][0]
        result = await self.client.post(API + "/characters/preview", json={"randomize": True, "seed": 44, "character": {"hair": preset["character"]["hair"]}})
        self.assertEqual(result.status, 200)
        self.assertEqual((await result.json())["character"]["hair"], preset["character"]["hair"])
        imported = await self.client.post(API + "/characters/import", json={"character": preset["character"], "locks": preset["locks"]})
        self.assertEqual(imported.status, 200)
        self.assertEqual((await (await self.client.get(API + "/jobs")).json())["items"], [])

    async def test_invalid_preview_input_returns_field_errors(self):
        for body, field in [({"randomize": "true"}, "randomize"), ({"randomize": True, "seed": True}, "seed"), ({"randomize": True, "fields": ["unknown"]}, "fields")]:
            with self.subTest(body=body):
                response = await self.client.post(API + "/characters/preview", json=body)
                self.assertEqual(response.status, 400)
                self.assertEqual((await response.json())["error"]["field"], field)

    async def test_cross_origin_preset_writes_are_rejected(self):
        response = await self.client.post(API + "/characters/import", json={"character": {}}, headers={"Origin": "https://outside.invalid"})
        self.assertEqual(response.status, 403)
