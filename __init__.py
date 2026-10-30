"""ComfyUI node-pack entry point; the studio also runs as python -m moss_go."""

from .moss_go.nodes import NODE_CLASS_MAPPINGS, NODE_DISPLAY_NAME_MAPPINGS
from .moss_go.bridge import install_bridge

install_bridge()

__all__ = ["NODE_CLASS_MAPPINGS", "NODE_DISPLAY_NAME_MAPPINGS"]
