"""ComfyUI's extra_conds_shapes contract is one flat shape per condition."""

import math


def reference_memory_shape(shapes, channels):
    if not isinstance(channels, int) or channels <= 0:
        raise ValueError("Reference latent channels must be a positive integer")
    elements = 0
    for shape in shapes:
        if not shape or any(not isinstance(value, int) or value <= 0 for value in shape):
            raise ValueError("Reference latent dimensions must be positive integers")
        elements += math.prod(shape)
    if not elements or elements % channels:
        raise ValueError("Reference latent size is incompatible with the model")
    # sampler_helpers.estimate_memory appends this value to its shape list itself.
    return [1, channels, elements // channels]
