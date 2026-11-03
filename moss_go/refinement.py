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


def edit_mask(add, settings, mask_image):
    """Feather in source coordinates before any crop, shared by all engines."""
    mask = add("mask", "LoadImageMask", image=mask_image, channel="red")
    mask = add("feather", "MossGoFeatherMask", mask=mask,
               width=settings.get("source_width", settings["width"]),
               height=settings.get("source_height", settings["height"]), radius=settings["feather"])
    if settings.get("edit_region"):
        mask = add("focus_mask", "CropMask", mask=mask, **settings["edit_region"])
    return mask


def finish_refinement(add, settings, source, base, result, mask):
    """Restore the generated crop and composite into the untouched source."""
    region = settings.get("edit_region")
    original_size = (region["width"], region["height"]) if region else (
        settings.get("source_width", settings["width"]), settings.get("source_height", settings["height"]))
    if original_size != (settings["width"], settings["height"]):
        result = add("restore_size", "ImageScale", image=result, upscale_method="lanczos",
                     width=original_size[0], height=original_size[1], crop="disabled")
    if mask:
        result = add("composite", "ImageCompositeMasked", destination=source if "source_width" in settings else base,
                     source=result, x=region["x"] if region else 0, y=region["y"] if region else 0,
                     resize_source=False, mask=mask)
    return result
