"""Source entry point, also compatible with isolated ComfyUI portable Python."""

from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))

from moss_go.model_setup import main

if __name__ == "__main__":
    raise SystemExit(main())
