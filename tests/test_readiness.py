import tempfile
import unittest
from unittest.mock import AsyncMock, patch

from aiohttp.test_utils import TestClient, TestServer

from moss_go.readiness import ENGINE_MODES, engine_readiness, hardware_summary, required_nodes
from moss_go.server import API, create_app
from moss_go.settings import choose_profile
from moss_go.workflows import MODEL_ROLES


def inventory():
    models = {}
    for roles in MODEL_ROLES.values():
        for category, aliases in roles.values():
            models.setdefault(category, []).extend(aliases[:1])
    return {"models": models, "nodes": set().union(*(required_nodes(engine, mode) for engine, modes in ENGINE_MODES.items() for mode in modes)),
            "devices": [{"name": "Test CUDA", "type": "cuda", "vram_total": 16 * 1024**3, "vram_free": 1024**3}],
            "system": {"ram_total": 32 * 1024**3, "ram_free": 12 * 1024**3, "comfyui_version": "fixture"}}


class ReadinessTests(unittest.TestCase):
    def test_missing_sampler_blocks_the_affected_mode_even_when_loaders_exist(self):
        inv = inventory()
        inv["nodes"].remove("SamplerCustomAdvanced")
        result = engine_readiness(inv)
        self.assertFalse(result["flux-klein"]["modes"]["create"]["ready"])
        self.assertIn("SamplerCustomAdvanced", result["flux-klein"]["modes"]["reference"]["missing_nodes"])
        self.assertTrue(result["moss"]["modes"]["create"]["ready"])

    def test_refinement_requirements_do_not_disable_create_or_reference(self):
        inv = inventory()
        inv["nodes"] -= {"MossGoFeatherMask", "ImageCrop", "CropMask"}
        result = engine_readiness(inv)["flux-klein"]
        self.assertTrue(result["modes"]["create"]["ready"])
        self.assertTrue(result["modes"]["reference"]["ready"])
        self.assertFalse(result["modes"]["refine"]["ready"])
        self.assertEqual(result["modes"]["refine"]["missing_nodes"], ["CropMask", "ImageCrop", "MossGoFeatherMask"])

    def test_unsupported_modes_and_uninstalled_precision_are_not_ready(self):
        result = engine_readiness(inventory())
        self.assertFalse(result["moss"]["modes"]["reference"]["supported"])
        self.assertFalse(result["moss-charref"]["modes"]["create"]["ready"])
        self.assertTrue(result["flux-klein"]["profiles"]["balanced"]["modes"]["refine"]["ready"])
        self.assertFalse(result["flux-klein"]["profiles"]["quality"]["modes"]["refine"]["ready"])
        self.assertIn("flux-2-klein-4b.safetensors", [item["filename"] for item in result["flux-klein"]["profiles"]["quality"]["missing"]])

    def test_optional_loras_are_not_a_dependency_of_the_core_graph(self):
        self.assertNotIn("LoraLoaderModelOnly", required_nodes("moss", "create"))
        self.assertIn("VAEEncodeTiled", required_nodes("moss", "refine"))
        self.assertIn("ImageScale", required_nodes("flux-klein", "refine"))

    def test_capacity_not_currently_free_vram_selects_auto_profile(self):
        inv = inventory()
        result = hardware_summary(inv["devices"], inv["system"])
        self.assertEqual(result["recommended_profile"], "balanced")
        self.assertEqual(result["vram_free"], 1024**3)
        self.assertEqual(choose_profile("auto", 12 * 1024**3), "economy")
        self.assertEqual(choose_profile("auto", 48 * 1024**3), "balanced")
        self.assertEqual(choose_profile("quality", 12 * 1024**3), "quality")

    def test_unknown_and_non_cuda_capacity_use_a_conservative_profile(self):
        for total in (None, True, -1, float("nan"), "16 GB"):
            self.assertEqual(choose_profile("auto", total), "economy")
        for devices in ([], [{"type": "cpu", "name": "CPU", "vram_total": 64 * 1024**3}], [{"type": "mps", "name": "Apple"}]):
            summary = hardware_summary(devices, {"ram_free": float("nan")})
            self.assertIsNone(summary["vram_total"])
            self.assertEqual(summary["recommended_profile"], "economy")
            self.assertIsNone(summary["ram_free"])


class ReadinessApiTests(unittest.IsolatedAsyncioTestCase):
    async def test_missing_models_or_sampling_nodes_cannot_create_a_batch(self):
        for profile, removed_node, code in (("quality", None, "models_missing"), ("balanced", "SamplerCustomAdvanced", "nodes_missing")):
            with self.subTest(profile=profile, missing=removed_node), tempfile.TemporaryDirectory() as folder:
                inv = inventory()
                if removed_node:
                    inv["nodes"].remove(removed_node)
                with patch("moss_go.comfy.ComfyClient.inventory", new=AsyncMock(return_value=inv)), \
                     patch("moss_go.comfy.ComfyClient.json", new=AsyncMock(return_value={"devices": inv["devices"]})) as transport:
                    client = TestClient(TestServer(create_app(data_root=folder, comfy_url="http://127.0.0.1:1")))
                    await client.start_server()
                    try:
                        result = await client.post(API + "/jobs", json={"mode": "create", "engine": "flux-klein", "profile": profile, "prompt": "A cup.", "variants": 1})
                        self.assertEqual(result.status, 409)
                        self.assertEqual((await result.json())["error"]["code"], code)
                        self.assertEqual((await (await client.get(API + "/jobs")).json())["items"], [])
                        transport.assert_awaited_once_with("/system_stats", timeout=5)  # Never POST /prompt.
                    finally:
                        await client.close()

    async def test_system_exposes_mode_specific_readiness_without_creating_jobs(self):
        with tempfile.TemporaryDirectory() as folder:
            inv = inventory()
            inv["nodes"].remove("MossGoFeatherMask")
            with patch("moss_go.comfy.ComfyClient.inventory", new=AsyncMock(return_value=inv)):
                client = TestClient(TestServer(create_app(data_root=folder, comfy_url="http://127.0.0.1:1")))
                await client.start_server()
                try:
                    result = await (await client.get(API + "/system?refresh=1")).json()
                    self.assertTrue(result["connected"])
                    self.assertEqual(result["default_language"], "en")
                    self.assertFalse(result["refine_ready"])
                    self.assertTrue(result["engines"]["flux-klein"]["modes"]["create"]["ready"])
                    self.assertEqual(result["hardware"]["recommended_profile"], "balanced")
                    self.assertEqual((await (await client.get(API + "/jobs")).json())["items"], [])
                finally:
                    await client.close()
