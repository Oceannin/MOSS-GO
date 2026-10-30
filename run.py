"""Launch from source, including with ComfyUI's isolated portable Python."""

from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))

from moss_go.__main__ import main

if __name__ == "__main__":
    main()
