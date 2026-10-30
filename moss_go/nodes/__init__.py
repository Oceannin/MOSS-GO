"""Only the nodes needed by the standalone studio. Names do not shadow old MOSS GO."""

from .reference_nodes import MOSSImageReferenceModelLoader, MOSSImageReferencePatch, MOSSImageReferenceConditioning
from .mask import FeatherMask

NODE_CLASS_MAPPINGS = {
    "MossGoReferenceModelLoader": MOSSImageReferenceModelLoader,
    "MossGoReferencePatch": MOSSImageReferencePatch,
    "MossGoReferenceConditioning": MOSSImageReferenceConditioning,
    "MossGoFeatherMask": FeatherMask,
}
NODE_DISPLAY_NAME_MAPPINGS = {
    "MossGoReferenceModelLoader": "MOSS GO · Reference model",
    "MossGoReferencePatch": "MOSS GO · Reference attention",
    "MossGoReferenceConditioning": "MOSS GO · Reference conditioning",
    "MossGoFeatherMask": "MOSS GO · Feather mask",
}
