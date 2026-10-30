"""Use the same softened mask for noise and final compositing."""

import numpy as np
from PIL import Image, ImageFilter
import torch


class FeatherMask:
    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {"mask": ("MASK",), "width": ("INT", {"default": 1024, "min": 16, "max": 8192}), "height": ("INT", {"default": 1024, "min": 16, "max": 8192}), "radius": ("INT", {"default": 8, "min": 0, "max": 64})}}

    RETURN_TYPES = ("MASK",)
    FUNCTION = "apply"
    CATEGORY = "MOSS GO"

    def apply(self, mask, width, height, radius):
        result = []
        for item in mask:
            picture = Image.fromarray((item.detach().float().cpu().numpy().clip(0, 1) * 255).round().astype(np.uint8))
            if picture.size != (width, height):
                picture = picture.resize((width, height), Image.Resampling.BILINEAR)
            if radius:
                picture = picture.filter(ImageFilter.GaussianBlur(radius))
            result.append(torch.from_numpy(np.array(picture, copy=True).astype(np.float32) / 255))
        return (torch.stack(result).to(device=mask.device),)
