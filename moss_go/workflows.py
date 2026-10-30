"""Small explicit API graphs; disabled features do not create dependencies."""

from .errors import StudioError

MODEL_ROLES = {
    "moss": {
        "model": ("diffusion_models", ["moss_image_sft_int8_convrot.safetensors"]),
        "clip": ("text_encoders", ["qwen3.5_9b_moss_image_sft_w4a8_gptq.safetensors", "qwen3.5_9b_w4a8_gptq.safetensors"]),
        "vae": ("vae", ["moss_image_vae_bf16.safetensors", "flux2-vae_small.safetensors"]),
    },
    "moss-charref": {
        "model": ("diffusion_models", ["moss_image_base_int8_convrot.safetensors"]),
        "clip": ("text_encoders", ["qwen3.5_9b_moss_image_sft_w4a8_gptq.safetensors", "qwen3.5_9b_w4a8_gptq.safetensors"]),
        "vae": ("vae", ["moss_image_vae_bf16.safetensors", "flux2-vae_small.safetensors"]),
        "reference_lora": ("loras", ["moss_image_charref_poc.safetensors"]),
    },
    "flux-klein": {
        "model": ("diffusion_models", ["flux-2-klein-4b-fp8.safetensors", "flux-2-klein-4b.safetensors"]),
        "clip": ("text_encoders", ["qwen_3_4b.safetensors"]),
        "vae": ("vae", ["flux2-vae.safetensors"]),
    },
}


QUALITY_OVERRIDES = {
    "moss": {
        "model": ("diffusion_models", ["moss_image_sft_bf16.safetensors"]),
        "clip": ("text_encoders", ["qwen3.5_9b_int8_convrot.safetensors"]),
        "vae": ("vae", ["flux2-vae.safetensors"]),
    },
    "moss-charref": {
        "model": ("diffusion_models", ["moss_image_base_bf16.safetensors"]),
        "clip": ("text_encoders", ["qwen3.5_9b_int8_convrot.safetensors"]),
        "vae": ("vae", ["flux2-vae.safetensors"]),
    },
    "flux-klein": {
        "model": ("diffusion_models", ["flux-2-klein-4b.safetensors"]),
    },
}


def resolve_models(engine, inventory, profile="balanced"):
    result, missing = {}, []
    roles = {**MODEL_ROLES[engine], **(QUALITY_OVERRIDES[engine] if profile == "quality" else {})}
    for role, (category, aliases) in roles.items():
        available = inventory.get("models", {}).get(category, [])
        match = next((name for alias in aliases for name in available if name.replace("\\", "/").split("/")[-1] == alias), None)
        if match:
            result[role] = match
        else:
            missing.append({"role": role, "category": category, "filename": aliases[0]})
    return result, missing


def build_workflow(settings, models, *, input_image=None, mask_image=None, prefix="MOSS-GO/result"):
    graph = {}
    def add(key, kind, **inputs):
        graph[key] = {"class_type": kind, "inputs": inputs}
        return [key, 0]
    engine, mode = settings["engine"], settings["mode"]
    width, height, seed = settings["width"], settings["height"], settings["seed"]
    if mode != "create" and not input_image:
        raise StudioError("This mode requires an input image.", field="input_id")
    if engine == "moss-charref":
        model = add("model", "MossGoReferenceModelLoader", base_name=models["model"], edit_lora=models["reference_lora"], strength=1.)
    else:
        model = add("model", "MOSSImageUNETLoader" if engine == "moss" else "UNETLoader", unet_name=models["model"], weight_dtype="default")
    for index, lora in enumerate(settings.get("loras", [])):
        if lora["strength"]:
            model = add(f"lora_{index}", "LoraLoaderModelOnly", model=model, lora_name=lora["name"], strength_model=lora["strength"])
    if engine.startswith("moss"):
        clip = add("clip", "MOSSImageCLIPLoader", clip_name=models["clip"], device=settings["text_device"])
    else:
        clip = add("clip", "CLIPLoader", clip_name=models["clip"], type="flux2", device=settings["text_device"])
    vae = add("vae", "VAELoader", vae_name=models["vae"])
    source = add("source", "LoadImage", image=input_image) if input_image else None
    region = settings.get("edit_region") if mode == "refine" else None
    edit_source = add("focus_image", "ImageCrop", image=source, **region) if region else source
    if engine == "moss-charref":
        model = add("sampling", "ModelSamplingSD3", model=model, shift=1.)
        model = add("slg", "SkipLayerGuidanceDiTSimple", model=model, double_layers="", single_layers="22", start_percent=0., end_percent=1.)
        model = add("reference_patch", "MossGoReferencePatch", model=model, kv_cache=True)
        positive = add("reference_conditioning", "MossGoReferenceConditioning", clip=clip, vae=vae, image=source, positive=settings["prompt"], negative=settings["negative"], reference_megapixels=min(1., width * height / 1_000_000))
        negative = ["reference_conditioning", 1]
    else:
        positive = add("positive", "CLIPTextEncode", clip=clip, text=settings["prompt"])
        negative = add("negative", "CLIPTextEncode", clip=clip, text=settings["negative"]) if engine == "moss" else add("negative", "ConditioningZeroOut", conditioning=positive)
        if engine == "moss":
            model = add("sampling", "ModelSamplingSD3", model=model, shift=5.)
            model = add("slg", "SkipLayerGuidanceDiTSimple", model=model, double_layers="", single_layers="22", start_percent=0., end_percent=1.)
        elif mode in {"reference", "refine"}:
            scaled = add("reference_size", "ImageScaleToTotalPixels", image=edit_source, upscale_method="lanczos", megapixels=min(1., width * height / 1_000_000), resolution_steps=16)
            encoded = add("reference_encode", "VAEEncode", pixels=scaled, vae=vae)
            positive = add("reference_positive", "ReferenceLatent", conditioning=positive, latent=encoded)
            negative = add("reference_negative", "ReferenceLatent", conditioning=negative, latent=encoded)
    if mode == "refine":
        base = add("base_size", "ImageScale", image=edit_source, upscale_method="lanczos", width=width, height=height, crop="disabled")
        latent = add("encode", "VAEEncodeTiled", pixels=base, vae=vae, tile_size=512, overlap=64, temporal_size=64, temporal_overlap=8) if engine == "moss" else add("latent", "EmptyFlux2LatentImage", width=width, height=height, batch_size=1)
        if mask_image:
            mask = add("mask", "LoadImageMask", image=mask_image, channel="red")
            mask = add("feather", "MossGoFeatherMask", mask=mask, width=settings.get("source_width", width), height=settings.get("source_height", height), radius=settings["feather"])
            if region:
                mask = add("focus_mask", "CropMask", mask=mask, **region)
            if engine == "moss":
                latent = add("noise_mask", "SetLatentNoiseMask", samples=latent, mask=mask)
    else:
        latent = add("latent", "EmptyFlux2LatentImage", width=width, height=height, batch_size=1)
    if engine == "flux-klein":
        noise = add("noise", "RandomNoise", noise_seed=seed)
        sampler = add("sampler", "KSamplerSelect", sampler_name="euler")
        guider = add("guider", "CFGGuider", model=model, positive=positive, negative=negative, cfg=1.)
        sigmas = add("sigmas", "Flux2Scheduler", steps=4, width=width, height=height)
        sampled = add("sample", "SamplerCustomAdvanced", noise=noise, guider=guider, sampler=sampler, sigmas=sigmas, latent_image=latent)
    else:
        sampled = add("sample", "KSampler", model=model, seed=seed, steps=settings["steps"], cfg=3., sampler_name="euler", scheduler="simple" if engine == "moss-charref" else "sgm_uniform", positive=positive, negative=negative, latent_image=latent, denoise=settings["strength"] if mode == "refine" else 1.)
    result = add("decode", "VAEDecodeTiled", samples=sampled, vae=vae, tile_size=512, overlap=64, temporal_size=64, temporal_overlap=8)
    if mode == "refine":
        original_size = (region["width"], region["height"]) if region else (settings.get("source_width", width), settings.get("source_height", height))
        if original_size != (width, height):
            result = add("restore_size", "ImageScale", image=result, upscale_method="lanczos", width=original_size[0], height=original_size[1], crop="disabled")
        if mask_image:
            result = add("composite", "ImageCompositeMasked", destination=source if "source_width" in settings else base, source=result, x=region["x"] if region else 0, y=region["y"] if region else 0, resize_source=False, mask=mask)
    add("save", "SaveImage", images=result, filename_prefix=prefix)
    return graph
