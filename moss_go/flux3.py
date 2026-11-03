"""Dedicated FLUX 3 distilled graphs, derived from the official INT8 templates."""

import json
import math
from pathlib import Path

from .refinement import edit_mask, finish_refinement

PROMPTS = json.loads((Path(__file__).parent / "assets/flux3_prompts.json").read_text("utf-8"))
ENGINE = "flux3-klein"


def compatibility_issues(inventory):
    # CLIPLoader exists in older ComfyUI releases without a FLUX 3 loader.
    return [] if "flux3" in inventory.get("clip_types", []) else ["CLIPLoader type flux3 (ComfyUI 0.41.2 recommended)"]


def build_flux3_workflow(settings, models, *, input_image=None, mask_image=None, prefix="MOSS-GO/result"):
    graph = {}

    def add(key, kind, **inputs):
        graph[key] = {"class_type": kind, "inputs": inputs}
        return [key, 0]

    mode, width, height = settings["mode"], settings["width"], settings["height"]
    source = add("source", "LoadImage", image=input_image) if input_image else None
    region = settings.get("edit_region") if mode == "refine" else None
    edit_source = add("focus_image", "ImageCrop", image=source, **region) if region else source
    prompt = settings["prompt"]
    if settings.get("prompt_upsampler", True):
        upsampler = add("upsampler_model", "CLIPLoader", clip_name=models["upsampler"],
                        type="flux3", device=settings["text_device"])
        params = {"clip": upsampler, "prompt": prompt,
                  "system_prompt": PROMPTS["create" if mode == "create" else "edit"],
                  "max_length": 3584, "sampling_mode": "on",
                  "sampling_mode.temperature": 1., "sampling_mode.top_k": 1,
                  "sampling_mode.top_p": .95, "sampling_mode.min_p": 0.,
                  "sampling_mode.repetition_penalty": 1., "sampling_mode.seed": settings["seed"],
                  "sampling_mode.presence_penalty": 1.5 if mode == "create" else 0.,
                  "thinking": False, "use_default_template": True, "mtp": "off"}
        if edit_source:
            params["image"] = edit_source
        prompt = add("upsample", "TextGenerate", **params)
    # The exact generated caption is returned in ComfyUI history and persisted.
    prompt = add("expanded_prompt", "PreviewAny", source=prompt)
    model = add("model", "UNETLoader", unet_name=models["model"], weight_dtype="default")
    for index, lora in enumerate(settings.get("loras", [])):
        if lora["strength"]:
            model = add(f"lora_{index}", "LoraLoaderModelOnly", model=model,
                        lora_name=lora["name"], strength_model=lora["strength"])
    clip = add("clip", "CLIPLoader", clip_name=models["clip"], type="flux3", device=settings["text_device"])
    vae = add("vae", "VAELoader", vae_name=models["vae"])
    positive = add("positive", "CLIPTextEncode", clip=clip, text=prompt)
    negative = add("negative", "CLIPTextEncode", clip=clip, text="")
    if edit_source:
        positive = add("reference", "ReferenceMultiLatent", positive=positive, negative=negative,
                       vae=vae, resolution="resize", **{"resolution.megapixels": min(1., width * height / 1024**2),
                                                        "images.image0": edit_source})
        negative = ["reference", 1]
    latent = add("latent", "EmptyFlux2LatentImage", width=width, height=height, batch_size=1)
    model = add("sampling", "ModelSamplingFlux", model=model,
                max_shift=math.log(16), base_shift=math.log(16), width=width, height=height)
    sampled = add("sample", "KSampler", model=model, positive=positive, negative=negative,
                  latent_image=latent, seed=settings["seed"], steps=settings["steps"], cfg=1.,
                  sampler_name="euler", scheduler="simple", denoise=1.)
    result = add("decode", "VAEDecodeTiled", samples=sampled, vae=vae, tile_size=512,
                 overlap=64, temporal_size=64, temporal_overlap=8)
    if mode == "refine":
        base = source if "source_width" in settings else add("base_size", "ImageScale", image=edit_source,
                    upscale_method="lanczos", width=width, height=height, crop="disabled")
        mask = edit_mask(add, settings, mask_image) if mask_image else None
        result = finish_refinement(add, settings, source, base, result, mask)
    add("save", "SaveImage", images=result, filename_prefix=prefix)
    return graph
