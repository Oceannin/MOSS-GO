"""Validated, canvas-independent generation settings."""

import math
import re
import uuid

from .errors import StudioError

SEED_MAX = 2**53 - 1
PROFILES = {
    "economy": {"label": "Memory saver", "target_gb": 12, "max_pixels": 589824, "text_device": "cpu", "verified": False},
    "balanced": {"label": "Balanced", "target_gb": 16, "max_pixels": 1048576, "text_device": "default", "verified": False},
    "quality": {"label": "High precision", "target_gb": 24, "max_pixels": 2097152, "text_device": "default", "verified": False},
}
FORMATS = {"portrait": (768, 1024), "square": (1024, 1024), "landscape": (1024, 768)}
MODES = {"create", "reference", "refine"}
ENGINES = {"moss", "moss-charref", "flux-klein"}


def identifier(value, field="id"):
    if not isinstance(value, str) or not re.fullmatch(r"[a-f0-9]{32}", value):
        raise StudioError("Invalid identifier.", field=field)
    return value


def integer(value, name, low, high):
    if isinstance(value, bool) or not isinstance(value, int) or not low <= value <= high:
        raise StudioError(f"{name} must be a whole number between {low} and {high}.", field=name)
    return value


def text(value, name, limit=12000, *, required=False):
    if not isinstance(value, str) or len(value) > limit or "\x00" in value:
        raise StudioError(f"{name} must be text of at most {limit} characters.", field=name)
    value = value.strip()
    if required and not value:
        raise StudioError("Describe the image you want to make.", field=name)
    return value


def choose_profile(requested, total_vram=None):
    if requested not in {"auto", *PROFILES}:
        raise StudioError("Choose a known memory profile.", field="profile")
    if requested != "auto":
        return requested
    # High precision remains an explicit choice, including on large GPUs.
    known = not isinstance(total_vram, bool) and isinstance(total_vram, (int, float)) and math.isfinite(total_vram)
    return "balanced" if known and total_vram >= 14 * 1024**3 else "economy"


def dimensions(format_name, profile, custom=None):
    if format_name not in FORMATS:
        raise StudioError("Choose portrait, square or landscape.", field="format")
    width, height = FORMATS[format_name]
    if custom is not None:
        if not isinstance(custom, dict) or set(custom) != {"width", "height"}:
            raise StudioError("Custom size requires width and height.", field="size")
        width = integer(custom["width"], "width", 256, 2048)
        height = integer(custom["height"], "height", 256, 2048)
        if width % 16 or height % 16:
            raise StudioError("Width and height must be multiples of 16.", field="size")
    scale = min(1, math.sqrt(PROFILES[profile]["max_pixels"] / (width * height)))
    return max(256, int(width * scale) // 16 * 16), max(256, int(height * scale) // 16 * 16)


def refinement_dimensions(width, height, profile, *, focus=False):
    """Fit the inference canvas to the source, without changing the final output size."""
    budget = min(PROFILES[profile]["max_pixels"], 768**2) if focus else PROFILES[profile]["max_pixels"]
    scale = min(math.sqrt(budget / (width * height)), (1024 if focus else 2048) / max(width, height))
    if not focus:
        scale = min(1., scale)
    fitted_w, fitted_h = max(64, int(width * scale) // 16 * 16), max(64, int(height * scale) // 16 * 16)
    if fitted_w * fitted_h > budget:
        if fitted_w > fitted_h:
            fitted_w = budget // fitted_h // 16 * 16
        else:
            fitted_h = budget // fitted_w // 16 * 16
    return fitted_w, fitted_h


def validate_request(data, *, total_vram=None):
    if not isinstance(data, dict):
        raise StudioError("Expected generation settings.")
    allowed = {"request_id", "mode", "engine", "profile", "quality", "format", "size", "prompt", "negative", "seed", "variants", "input_id", "mask_id", "parent_id", "strength", "feather", "scenes", "character", "loras"}
    if set(data) - allowed:
        raise StudioError("Unknown generation setting.")
    mode = data.get("mode", "reference")
    if mode not in MODES:
        raise StudioError("Choose a known generation mode.", field="mode")
    engine = data.get("engine", "moss" if mode == "create" else "flux-klein")
    if engine not in ENGINES or mode == "reference" and engine == "moss":
        raise StudioError("Choose an engine that supports this mode.", field="engine")
    if mode != "reference" and engine == "moss-charref":
        raise StudioError("CharRef is available in reference mode.", field="engine")
    quality = data.get("quality", "standard")
    if quality not in {"draft", "standard", "detailed"}:
        raise StudioError("Choose a known quality setting.", field="quality")
    profile = choose_profile(data.get("profile", "auto"), total_vram)
    width, height = dimensions(data.get("format", "portrait"), profile, data.get("size"))
    prompt = text(data.get("prompt", ""), "prompt", required=True)
    scenes = data.get("scenes", [])
    if not isinstance(scenes, list) or len(scenes) > 4:
        raise StudioError("A scene pack contains at most four scenes.", field="scenes")
    scenes = [text(scene, "scenes", 3000, required=True) for scene in scenes]
    if mode == "refine" and scenes:
        raise StudioError("Refine one selected image at a time.", field="scenes")
    request_id = data.get("request_id", uuid.uuid4().hex)
    identifier(request_id, "request_id")
    result = {"request_id": request_id, "mode": mode, "engine": engine, "profile": profile,
              "requested_profile": data.get("profile", "auto"), "quality": quality,
              "format": data.get("format", "portrait"), "width": width, "height": height,
              "prompt": prompt, "negative": text(data.get("negative", ""), "negative", 4000),
              "seed": integer(data.get("seed", 42), "seed", 0, SEED_MAX),
              "variants": integer(data.get("variants", 4), "variants", 1, 4), "scenes": scenes,
              "steps": 4 if engine == "flux-klein" else {"draft": 20, "standard": 30, "detailed": 50}[quality],
              "text_device": PROFILES[profile]["text_device"]}
    for key in ("input_id", "mask_id", "parent_id"):
        result[key] = identifier(data[key], key) if data.get(key) is not None else None
    if mode in {"reference", "refine"} and not result["input_id"]:
        raise StudioError("Choose an input image first.", field="input_id")
    if result["mask_id"] and mode != "refine":
        raise StudioError("Masks belong to refine mode.", field="mask_id")
    strength = data.get("strength", .3)
    if isinstance(strength, bool) or not isinstance(strength, (int, float)) or not math.isfinite(strength) or not .01 <= strength <= 1:
        raise StudioError("Refinement strength must be between 0.01 and 1.", field="strength")
    result["strength"] = strength
    result["feather"] = integer(data.get("feather", 8), "feather", 0, 64)
    from .characters import validate_character
    result["character"] = validate_character(data.get("character", {}))
    loras = data.get("loras", [])
    if not isinstance(loras, list) or len(loras) > 8:
        raise StudioError("Choose at most eight LoRAs.", field="loras")
    result["loras"] = []
    for item in loras:
        if not isinstance(item, dict) or set(item) != {"name", "strength"}:
            raise StudioError("Each LoRA needs a name and strength.", field="loras")
        name = text(item["name"], "loras", 512, required=True)
        if ".." in name.replace("\\", "/").split("/") or name.startswith(("/", "\\")) or ":" in name:
            raise StudioError("Choose a LoRA from the model library.", field="loras")
        value = item["strength"]
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or not -2 <= value <= 2:
            raise StudioError("LoRA strength must be between -2 and 2.", field="loras")
        result["loras"].append({"name": name, "strength": value})
    return result
