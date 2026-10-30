"""Verify a wheel in a fresh environment, without importing the source checkout."""

import argparse
import os
from pathlib import Path
import shutil
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    wheels = parser.add_mutually_exclusive_group(required=True)
    wheels.add_argument("--wheel", type=Path)
    wheels.add_argument("--wheel-dir", type=Path)
    wheels.add_argument("--source", action="store_true", help="Test the documented pinned source installation")
    parser.add_argument("--work-dir", required=True, type=Path, help="New empty QA directory; retained for review")
    args = parser.parse_args()
    wheel = None
    if not args.source:
        candidates = list(args.wheel_dir.glob("moss_go-*.whl")) if args.wheel_dir else [args.wheel]
        if len(candidates) != 1:
            parser.error("Select exactly one MOSS GO wheel.")
        wheel = candidates[0].resolve(strict=True)
    work = args.work_dir.resolve()
    if work.exists() and any(work.iterdir()):
        parser.error("Use an empty work directory; existing environments are never overwritten.")
    work.mkdir(parents=True, exist_ok=True)
    environment = os.environ.copy()
    for key in ("PYTHONPATH", "PYTHONHOME", "VIRTUAL_ENV"):
        environment.pop(key, None)
    environment.pop("PIP_EXTRA_INDEX_URL", None)
    environment.update(PYTHONNOUSERSITE="1", PYTHONUTF8="1", PIP_DISABLE_PIP_VERSION_CHECK="1")
    environment["PIP_CONFIG_FILE"] = os.devnull
    outside = work / "outside-source"
    outside.mkdir()
    def run(command, expected=0):
        result = subprocess.run([str(part) for part in command], cwd=outside, env=environment)
        if result.returncode != expected:
            raise RuntimeError(f"Verification command returned {result.returncode}, expected {expected}: {command[0]}")
    venv = work / "venv"
    run([sys.executable, "-m", "venv", venv])
    executable_dir = venv / ("Scripts" if os.name == "nt" else "bin")
    python = executable_dir / ("python.exe" if os.name == "nt" else "python")
    dependencies = [python, "-I", "-m", "pip", "install", "--index-url", "https://pypi.org/simple", "--require-hashes", "--only-binary=:all:", "-r", ROOT / "requirements.lock"]
    if args.source:
        dependencies.extend(["-r", ROOT / "build-requirements.lock"])
    run(dependencies)
    run([python, "-I", "-m", "pip", "install", "--no-deps", "--no-build-isolation", ROOT] if args.source else
        [python, "-I", "-m", "pip", "install", "--no-deps", "--no-index", wheel])
    tests = work / "tests"
    shutil.copytree(ROOT / "tests", tests, ignore=shutil.ignore_patterns("__pycache__"))
    run([python, "-I", "-m", "unittest", "discover", "-s", tests])
    run([python, "-I", ROOT / "scripts/installed_smoke.py"])
    suffix = ".exe" if os.name == "nt" else ""
    run([executable_dir / ("moss-go" + suffix), "--help"])
    run([executable_dir / ("moss-go-models" + suffix), "plan", "--models-dir", work / "missing-models", "--pack", "moss-balanced", "--pack", "flux-balanced"])
    print(f"Installed-{'source' if args.source else 'wheel'} checks passed. Evidence environment retained at {work}")


if __name__ == "__main__":
    main()
