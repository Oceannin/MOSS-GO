"""Deterministic context around a painted selection, in original-image coordinates."""

from PIL import Image


def selection_region(width, height, bounds, feather):
    if bounds is None:
        return None
    left, top, right, bottom = bounds
    # Keep local structure around the edit. A tiny mark still needs a useful view
    # of the object; large selections naturally fall back to the complete frame.
    side = max(240, 4 * max(right - left, bottom - top), 8 * feather + max(right - left, bottom - top))
    crop_width, crop_height = min(width, side), min(height, side)
    if (crop_width, crop_height) == (width, height):
        return None
    x = max(0, min(width - crop_width, (left + right - crop_width) // 2))
    y = max(0, min(height - crop_height, (top + bottom - crop_height) // 2))
    return {"x": x, "y": y, "width": crop_width, "height": crop_height}


def region_from_mask(path, width, height, feather):
    with Image.open(path) as mask:
        return selection_region(width, height, mask.getbbox(), feather)
