"""Run with python -m moss_go; ComfyUI runs independently."""

import argparse
import logging
import os
from pathlib import Path

from aiohttp import web

from .server import create_app


def main():
    parser = argparse.ArgumentParser(description="MOSS GO — local image studio")
    parser.add_argument("--comfy", default="http://127.0.0.1:8188", help="ComfyUI server URL")
    parser.add_argument("--port", type=int, default=8191)
    parser.add_argument("--ollama", default="http://127.0.0.1:11434", help="Local loopback Ollama URL")
    parser.add_argument("--data", type=Path, default=Path(os.environ.get("LOCALAPPDATA", Path.home() / ".local/share")) / "MOSS-GO")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    web.run_app(create_app(data_root=args.data, comfy_url=args.comfy, ollama_url=args.ollama), host="127.0.0.1", port=args.port, access_log=None)


if __name__ == "__main__":
    main()
