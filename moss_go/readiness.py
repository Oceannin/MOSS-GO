"""Readiness follows real graph construction, separately for each supported mode."""

import math

from .settings import PROFILES, choose_profile, validate_request
from .workflows import build_workflow, resolve_models
from .flux3 import compatibility_issues


ENGINE_MODES = {"moss": ("create", "refine"), "moss-charref": ("reference",),
                "flux-klein": ("create", "reference", "refine"),
                "flux3-klein": ("create", "reference", "refine")}


def required_nodes(engine, mode, *, prompt_upsampler=True):
    settings = validate_request({"engine": engine, "mode": mode, "profile": "balanced",
                                 "prompt": "Readiness probe; never submitted.", "variants": 1,
                                 "input_id": "a" * 32 if mode != "create" else None,
                                 "mask_id": "b" * 32 if mode == "refine" else None,
                                 "prompt_upsampler": prompt_upsampler})
    # Include the full source restoration and focused-mask paths that may be
    # needed after the user uploads an image. Optional LoRAs remain optional.
    if mode == "refine":
        settings.update(source_width=1536, source_height=2048)
        if engine in {"flux-klein", "flux3-klein"}:
            settings["edit_region"] = {"x": 200, "y": 200, "width": 320, "height": 320}
    graph = build_workflow(settings, {"model": "probe.safetensors", "clip": "probe.safetensors",
                                     "vae": "probe.safetensors", "reference_lora": "probe.safetensors",
                                     "upsampler": "probe.safetensors"},
                           input_image="probe.png" if mode != "create" else None,
                           mask_image="probe-mask.png" if mode == "refine" else None)
    return {node["class_type"] for node in graph.values()}


def engine_readiness(inventory):
    engines = {}
    for engine, supported in ENGINE_MODES.items():
        issues = compatibility_issues(inventory) if engine == "flux3-klein" else []
        def checked_profile(profile, upsampler=True):
            models, missing = resolve_models(engine, inventory, profile, prompt_upsampler=upsampler)
            modes = {}
            for mode in ("create", "reference", "refine"):
                absent = sorted(required_nodes(engine, mode, prompt_upsampler=upsampler) - inventory["nodes"]) if mode in supported else []
                modes[mode] = {"supported": mode in supported, "missing_nodes": absent,
                               "missing_capabilities": issues,
                               "ready": mode in supported and not missing and not absent and not issues}
            return {"models": models, "missing": missing, "modes": modes,
                    "missing_capabilities": issues, "ready": any(item["ready"] for item in modes.values())}
        profiles = {}
        for profile in PROFILES:
            profiles[profile] = checked_profile(profile)
            if engine == "flux3-klein":
                profiles[profile]["caption_only"] = checked_profile(profile, False)
        balanced = profiles["balanced"]
        engines[engine] = {**balanced, "profiles": profiles, "quality_verified": False,
                           "missing_nodes": sorted({node for mode in balanced["modes"].values() for node in mode["missing_nodes"]})}
    return engines


def memory_bytes(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0:
        return None
    return int(value)


def hardware_summary(devices, system):
    device = next((item for item in devices if item.get("type") == "cuda"), devices[0] if devices else {})
    accelerator = device.get("type", "unknown")
    capacity = memory_bytes(device.get("vram_total")) if accelerator == "cuda" else None
    return {"accelerator": accelerator, "name": device.get("name"), "vram_total": capacity,
            "vram_free": memory_bytes(device.get("vram_free")) if accelerator == "cuda" else None,
            "ram_total": memory_bytes(system.get("ram_total")), "ram_free": memory_bytes(system.get("ram_free")),
            "recommended_profile": choose_profile("auto", capacity),
            "recommendation_basis": "gpu_capacity" if capacity else "unknown_capacity",
            "hardware_validation": "NVIDIA RTX 4070 Ti SUPER 16 GB / 32 GB RAM only"}
