"""Run real studio jobs and keep a resumable evidence ledger. No synthetic results."""

import argparse
import hashlib
import json
from pathlib import Path
import sys
import time
import urllib.error
import urllib.request
import uuid

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("stage", choices=["references", "smoke", "compare", "status"])
    parser.add_argument("--server", default="http://127.0.0.1:8191")
    parser.add_argument("--report", type=Path, default=ROOT / ".local/benchmark/report.json")
    parser.add_argument("--wait", action="store_true")
    parser.add_argument("--retry-failed", action="store_true", help="Retry only jobs authoritatively marked error, keeping prior attempts")
    parser.add_argument("--retry-reason", default="")
    parser.add_argument("--case", help="Run one exact comparison key before expanding a repaired benchmark")
    parser.add_argument("--summary", action="store_true")
    parser.add_argument("--cases", type=Path, default=ROOT / "moss_go/assets/benchmark_cases.json")
    parser.add_argument("--engine", action="append", choices=["moss-charref", "flux-klein"], help="Bound a follow-up round to explicit engines")
    parser.add_argument("--references-from", type=Path, help="Reuse inspected reference fixtures in a separate new report")
    args = parser.parse_args()
    CASES = json.loads(args.cases.read_text(encoding="utf-8"))
    if args.retry_failed and not args.retry_reason.strip():
        parser.error("--retry-failed requires a recorded --retry-reason")
    endpoint = args.server.rstrip("/") + "/moss-go/api/v1"
    report = json.loads(args.report.read_text(encoding="utf-8")) if args.report.exists() else {"version": 1, "real_model_runs": True, "references": {}, "runs": []}
    if args.references_from and not report["references"]:
        baseline = json.loads(args.references_from.read_text(encoding="utf-8"))
        report["references"] = baseline["references"]
        report["reference_ledger"] = str(args.references_from)
    if args.stage != "status":
        digest = hashlib.sha256(args.cases.read_bytes()).hexdigest()
        if report.get("config_sha256") not in {None, digest}:
            raise RuntimeError("This report belongs to a different benchmark configuration. Choose a new report.")
        report["config_sha256"] = digest
        report["config"] = CASES
    args.report.parent.mkdir(parents=True, exist_ok=True)

    def save():
        temporary = args.report.with_suffix(".tmp")
        temporary.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
        temporary.replace(args.report)

    def api(path, data=None):
        request = urllib.request.Request(endpoint + path, data=json.dumps(data).encode() if data is not None else None, headers={"Content-Type": "application/json"} if data is not None else {})
        try:
            with urllib.request.urlopen(request, timeout=60) as response:
                return json.load(response)
        except urllib.error.HTTPError as exc:
            raise RuntimeError(exc.read().decode("utf-8", errors="replace")) from exc

    def launch(key, settings, **metadata):
        if args.case and key != args.case:
            return
        existing = next((run for run in report["runs"] if run["key"] == key), None)
        if existing:
            current = api("/jobs/" + existing["job_id"])
            if not args.retry_failed or current["status"] != "error":
                print("Existing", key, existing["job_id"], flush=True)
                return
            retries = report.setdefault("retry_intents", {})
            intent = retries.get(key)
            if not intent or intent["previous_job_id"] != existing["job_id"]:
                intent = {"previous_job_id": existing["job_id"], "token": uuid.uuid4().hex, "reason": args.retry_reason}
                retries[key] = intent
            save()
            batch = api("/jobs", {"request_id": intent["token"], "variants": 1, **settings})
            existing.setdefault("attempts", []).append({"job_id": current["id"], "result": {k: current.get(k) for k in ("status", "error", "prompt_id", "output_id", "elapsed")}, "retry_reason": intent["reason"]})
            existing["job_id"] = batch["jobs"][0]["id"]
            existing["settings"] = settings
            existing["result"] = {"status": batch["jobs"][0]["status"]}
            del retries[key]
            save()
            print("Retry queued", key, existing["job_id"], flush=True)
            return
        # Commit the idempotency token before sending an expensive request.
        intents = report.setdefault("intents", {})
        token = intents.setdefault(key, uuid.uuid4().hex)
        save()
        batch = api("/jobs", {"request_id": token, "variants": 1, **settings})
        if len(batch["jobs"]) != 1:
            raise RuntimeError("Benchmark jobs must be individually traceable")
        job = batch["jobs"][0]
        report["runs"].append({"key": key, "job_id": job["id"], "settings": settings, **metadata})
        save()
        print("Queued", key, job["id"], flush=True)

    if args.stage == "references":
        for character in CASES["characters"]:
            revision = "/v" + str(character["revision"]) if character.get("revision", 1) > 1 else ""
            launch("reference/" + character["id"] + revision, {"mode": "create", "engine": "moss", "prompt": character["description"], "negative": character.get("negative", ""), "seed": character["seed"], "format": "portrait", "quality": "standard"}, character=character["id"], purpose="reference")
    elif args.stage in {"smoke", "compare"}:
        characters = CASES["characters"][:1] if args.stage == "smoke" else CASES["characters"]
        scenes = CASES["scenes"][:1] if args.stage == "smoke" else CASES["scenes"]
        seeds = CASES["seeds"][:1] if args.stage == "smoke" else CASES["seeds"]
        for character in characters:
            if character["id"] not in report["references"]:
                raise RuntimeError(f"Reference {character['id']} has not finished. Run status first.")
            if not report["references"][character["id"]].get("visually_approved"):
                raise RuntimeError(f"Inspect and approve reference {character['id']} before comparing engines.")
        for engine in args.engine or ("moss-charref", "flux-klein"):
            for character in characters:
                for scene in scenes:
                    for seed in seeds:
                        key = f"compare/{engine}/{character['id']}/{scene['id']}/{seed}"
                        prompt = scene["description"] + "\nCharacter appearance: " + character["appearance"] + "."
                        launch(key, {"mode": "reference", "engine": engine, "input_id": report["references"][character["id"]]["output_id"], "prompt": prompt, "seed": seed, "format": "portrait", "quality": "standard"}, character=character["id"], scene=scene["id"], purpose="comparison", engine=engine, seed=seed)

    previous = {}
    while True:
        active = 0
        for run in report["runs"]:
            job = api("/jobs/" + run["job_id"])
            run["result"] = {key: job.get(key) for key in ("status", "output_id", "elapsed", "error", "prompt_id")}
            if run["purpose"] == "reference" and job["status"] == "done":
                approved = report["references"].get(run["character"], {})
                report["references"][run["character"]] = {**approved, "job_id": job["id"], "output_id": job["output_id"], "visually_approved": approved.get("visually_approved", False)}
            if job["status"] in {"pending", "submitting", "queued", "running"}:
                active += 1
            if not args.summary and previous.get(run["key"]) != job["status"]:
                print(run["key"], job["status"], job.get("error") or "", flush=True)
                previous[run["key"]] = job["status"]
        save()
        if args.summary:
            from collections import Counter
            print("Recorded states:", dict(Counter((run.get("engine", "reference"), run["result"]["status"]) for run in report["runs"])), flush=True)
            print("Live handles:", [(run["job_id"], run["result"].get("prompt_id")) for run in report["runs"] if run["result"]["status"] in {"queued", "running"}], flush=True)
        if not args.wait or not active:
            print("Active:", active, "Report:", args.report, flush=True)
        if not args.wait or not active:
            break
        time.sleep(15)


if __name__ == "__main__":
    main()
