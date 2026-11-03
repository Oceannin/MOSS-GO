"""Execute the distilled official FLUX 3 template's core API path.

Download the official templates separately after accepting their model license.
This probe does not import MOSS GO or count mock execution as GPU validation.
"""

import argparse
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import subprocess
import time
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import Request, urlopen
import uuid

import psutil


def request(base, path, payload=None):
    raw = json.dumps(payload).encode() if payload is not None else None
    req = Request(base + path, data=raw, headers={"Content-Type": "application/json"})
    try:
        with urlopen(req, timeout=30) as response:
            return json.load(response)
    except HTTPError as exc:
        raise RuntimeError(f"ComfyUI HTTP {exc.code}: {exc.read().decode()}") from exc


def official_graph(template, prompt, *, reference=None, width=1024, height=1024, seed=42, captioned=False):
    """Resolve the official no-boxes, upsampler-enabled branch into API nodes.

    The visual template's primitive/switch/UI nodes are resolved here. Model
    loaders, actual TextGenerate, sampling shifts and image conditioning retain
    the official semantics. INT8 replaces the template's W4A8 upsampler choice.
    """
    groups = template["definitions"]["subgraphs"]
    pup = next(g for g in groups if g["name"] == "Prompt Upsampler")
    system = next(n for n in pup["nodes"] if n["id"] == 114)["widgets_values"][0]
    graph = {}

    def add(key, kind, **inputs):
        graph[key] = {"class_type": kind, "inputs": inputs}
        return [key, 0]

    source = add("source", "LoadImage", image=reference) if reference else None
    params = {"prompt": prompt, "system_prompt": system,
              "max_length": 3584, "sampling_mode": "on",
              "sampling_mode.temperature": 1., "sampling_mode.top_k": 1,
              "sampling_mode.top_p": .95, "sampling_mode.min_p": 0.,
              "sampling_mode.repetition_penalty": 1., "sampling_mode.seed": seed,
              "sampling_mode.presence_penalty": 0. if reference else 1.5,
              "thinking": False, "use_default_template": True, "mtp": "off"}
    if source:
        params["image"] = source
    if captioned:
        expanded = prompt
    else:
        params["clip"] = add("upsampler_model", "CLIPLoader",
                             clip_name="qwen3.5_9b_flux3_prompt_upsampler_int8_convrot.safetensors",
                             type="flux3", device="default")
        expanded = add("upsample", "TextGenerate", **params)
    add("expanded_prompt", "PreviewAny", source=expanded)
    model = add("model", "UNETLoader",
                unet_name="flux3-image-klein-int8-convrot.safetensors", weight_dtype="default")
    clip = add("clip", "CLIPLoader", clip_name="qwen3vl_4b_int8_convrot.safetensors",
               type="flux3", device="default")
    vae = add("vae", "VAELoader", vae_name="flux2-vae.safetensors")
    positive = add("positive", "CLIPTextEncode", clip=clip, text=expanded)
    negative = add("negative", "CLIPTextEncode", clip=clip, text="")
    if source:
        positive = add("reference", "ReferenceMultiLatent", positive=positive,
                       negative=negative, vae=vae, resolution="resize",
                       **{"resolution.megapixels": 1., "images.image0": source})
        negative = ["reference", 1]
    latent = add("latent", "EmptyFlux2LatentImage", width=width, height=height, batch_size=1)
    model = add("sampling", "ModelSamplingFlux", model=model,
                max_shift=math.log(16), base_shift=math.log(16), width=width, height=height)
    sampled = add("sample", "KSampler", model=model, positive=positive, negative=negative,
                  latent_image=latent, seed=seed, steps=16, cfg=1.,
                  sampler_name="euler", scheduler="simple", denoise=1.)
    image = add("decode", "VAEDecode", samples=sampled, vae=vae)
    add("save", "SaveImage", images=image, filename_prefix="MOSS-GO-FLUX3/official-smoke")
    return graph


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--template", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--comfy", default="http://127.0.0.1:8188")
    parser.add_argument("--pid", type=int, required=True, help="Isolated ComfyUI process ID")
    parser.add_argument("--prompt", required=True)
    parser.add_argument("--reference", help="Image already uploaded to ComfyUI input")
    parser.add_argument("--width", type=int, default=1024)
    parser.add_argument("--height", type=int, default=1024)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--build-only", action="store_true")
    parser.add_argument("--captioned", action="store_true",
                        help="Explicit official bypass for a supplied full caption; no upsampler is claimed")
    args = parser.parse_args()
    graph = official_graph(json.loads(args.template.read_text(encoding="utf-8")), args.prompt,
                           reference=args.reference, width=args.width, height=args.height,
                           seed=args.seed, captioned=args.captioned)
    args.output.mkdir(parents=True, exist_ok=True)
    (args.output / "workflow.api.json").write_text(json.dumps(graph, indent=2), encoding="utf-8")
    if args.build_only:
        return
    process = psutil.Process(args.pid)
    try:
        import pynvml
        pynvml.nvmlInit()
        gpu = pynvml.nvmlDeviceGetHandleByIndex(0)
        gpu_memory = lambda: pynvml.nvmlDeviceGetMemoryInfo(gpu).used
    except Exception:
        def gpu_memory():
            value = subprocess.check_output(
                ["nvidia-smi", "--query-gpu=memory.used", "--format=csv,noheader,nounits"],
                text=True, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            return int(value.strip().splitlines()[0]) * 1024**2
    baseline = {"gpu_device_used_bytes": gpu_memory(), "process_rss_bytes": process.memory_info().rss,
                "system_used_bytes": psutil.virtual_memory().used}
    peak = dict(baseline)
    started = time.monotonic()
    record = {"started_utc": datetime.now(timezone.utc).isoformat(), "prompt": args.prompt,
              "template": args.template.name, "template_sha256": hashlib.sha256(args.template.read_bytes()).hexdigest(),
              "width": args.width, "height": args.height, "steps": 16, "seed": args.seed,
              "prompt_upsampler": "explicit full-caption bypass" if args.captioned else "official Qwen3.5 9B INT8",
              "sampling": "Euler/simple, CFG 1, Flux shift ln(16)", "baseline": baseline,
              "memory_scope": "sampled device-wide VRAM, ComfyUI RSS, system-wide RAM; includes other applications"}
    result = request(args.comfy, "/prompt", {"prompt": graph, "client_id": uuid.uuid4().hex})
    record["prompt_id"] = result["prompt_id"]
    (args.output / "submission.json").write_text(json.dumps(record, indent=2), encoding="utf-8")
    print("Submitted actual GPU probe:", record["prompt_id"], flush=True)
    while True:
        current = {"gpu_device_used_bytes": gpu_memory(), "process_rss_bytes": process.memory_info().rss,
                   "system_used_bytes": psutil.virtual_memory().used}
        peak = {key: max(peak[key], value) for key, value in current.items()}
        history = request(args.comfy, "/history/" + record["prompt_id"])
        entry = history.get(record["prompt_id"])
        if entry:
            (args.output / "history.json").write_text(json.dumps(entry, indent=2), encoding="utf-8")
            record.update(elapsed_seconds=round(time.monotonic() - started, 2), sampled_peak=peak,
                          status=entry.get("status", {}), outputs=entry.get("outputs", {}))
            for index, image in enumerate(entry.get("outputs", {}).get("save", {}).get("images", [])):
                with urlopen(args.comfy + "/view?" + urlencode(image), timeout=30) as response:
                    raw = response.read()
                (args.output / f"result-{index}.png").write_bytes(raw)
            (args.output / "result.json").write_text(json.dumps(record, indent=2), encoding="utf-8")
            print("GPU probe finished:", record["status"], "elapsed:", record["elapsed_seconds"],
                  "sampled peaks:", peak, flush=True)
            if not list(args.output.glob("result-*.png")) or record["status"].get("status_str") != "success":
                raise SystemExit(1)
            return
        time.sleep(.5)


if __name__ == "__main__":
    main()
