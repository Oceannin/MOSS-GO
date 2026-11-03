"""Observe the next real UI job without submitting or altering any GPU work.

QA dependency: psutil; nvidia-ml-py is optional (otherwise uses nvidia-smi).
Memory peaks are sampled, device/system-wide where indicated, not Torch peaks.
"""

import argparse
from datetime import datetime, timezone
import io
import json
from pathlib import Path
import time
import subprocess
from urllib.request import urlopen

from PIL import Image, ImageChops, ImageFilter
import psutil


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--studio", default="http://127.0.0.1:8191/moss-go/api/v1")
    parser.add_argument("--pid", type=int, required=True, help="ComfyUI process, not the studio process")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)

    def get(path, binary=False):
        with urlopen(args.studio + path, timeout=30) as response:
            return response.read() if binary else json.load(response)

    try:
        import pynvml
        pynvml.nvmlInit()
        gpu = pynvml.nvmlDeviceGetHandleByIndex(0)
        gpu_used = lambda: pynvml.nvmlDeviceGetMemoryInfo(gpu).used
    except Exception:
        def gpu_used():
            raw = subprocess.check_output(["nvidia-smi", "--query-gpu=memory.used", "--format=csv,noheader,nounits"],
                                          text=True, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            return int(raw.strip().splitlines()[0]) * 1024**2
    process = psutil.Process(args.pid)

    def sample():
        return {"gpu_device_used_bytes": gpu_used(),
                "comfy_rss_bytes": process.memory_info().rss,
                "system_used_bytes": psutil.virtual_memory().used,
                "system_available_bytes": psutil.virtual_memory().available}

    previous = {j["id"] for j in get("/jobs")["items"]}
    baseline = sample()
    peaks = dict(baseline)
    minimum_available = baseline["system_available_bytes"]
    start = time.monotonic()
    samples = 0
    job_id = None
    print("Watching for the next actual UI submission; no generation is submitted by this observer.", flush=True)
    while True:
        current = sample()
        samples += 1
        for key, value in current.items():
            peaks[key] = max(peaks[key], value)
        minimum_available = min(minimum_available, current["system_available_bytes"])
        if job_id is None:
            jobs = [j for j in get("/jobs")["items"] if j["id"] not in previous]
            if jobs:
                job_id = jobs[-1]["id"]
                print("Observed:", job_id, flush=True)
        if job_id:
            job = get("/jobs/" + job_id)
            if job["status"] in {"done", "error", "cancelled", "interrupted"}:
                break
        time.sleep(.5)
    record = {"recorded_utc": datetime.now(timezone.utc).isoformat(),
              "scope": "Sampled device-wide VRAM, ComfyUI process RSS and system RAM, including other applications.",
              "sample_interval_seconds": .5, "samples": samples,
              "baseline": baseline, "sampled_peak": peaks, "after": sample(),
              "minimum_system_available_bytes": minimum_available,
              "observed_seconds": round(time.monotonic() - start, 2), "job": job}
    if job.get("output_id"):
        raw = get("/images/" + job["output_id"], True)
        (args.output / "result.png").write_bytes(raw)
        settings = job["settings"]
        if settings.get("mask_id"):
            source_raw = get("/images/" + settings["input_id"], True)
            mask_raw = get("/images/" + settings["mask_id"], True)
            (args.output / "source.png").write_bytes(source_raw)
            (args.output / "mask.png").write_bytes(mask_raw)
            source = Image.open(io.BytesIO(source_raw)).convert("RGB")
            result = Image.open(io.BytesIO(raw)).convert("RGB")
            mask = Image.open(io.BytesIO(mask_raw)).convert("L")
            if source.size != result.size or source.size != mask.size:
                record["pixel_check"] = {"passed": False, "reason": "dimension mismatch"}
            else:
                effective = mask.filter(ImageFilter.GaussianBlur(settings["feather"]))
                diff = ImageChops.difference(source, result)
                bands = diff.split()
                changed = ImageChops.lighter(ImageChops.lighter(bands[0], bands[1]), bands[2]).point(lambda v: 255 if v else 0)
                outside = effective.point(lambda v: 0 if v else 255)
                violations = ImageChops.multiply(changed, outside).histogram()[255]
                record["pixel_check"] = {"passed": violations == 0, "dimensions": list(source.size),
                                         "changed_pixels": changed.histogram()[255],
                                         "changed_outside_effective_mask": violations,
                                         "effective_mask_bounds": effective.getbbox(),
                                         "changed_bounds": changed.getbbox()}
    (args.output / "measurement.json").write_text(json.dumps(record, indent=2), encoding="utf-8")
    print("Finished:", job["status"], "actual job seconds:", job.get("elapsed"),
          "sampled VRAM GiB:", round(peaks["gpu_device_used_bytes"] / 1024**3, 2),
          "pixel check:", record.get("pixel_check"), flush=True)
    if job["status"] != "done" or record.get("pixel_check", {}).get("passed") is False:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
