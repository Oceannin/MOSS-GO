import math
import json
from pathlib import Path
import struct
import importlib
import torch
import torch.nn.functional as F
import folder_paths
import node_helpers
from .lora_stack import MOSSImageLoRAStack
from .reference_transformer import patch_reference_model

BASE_NAME = 'moss_image_base_int8_convrot.safetensors'
LORA_NAME = 'moss/moss_image_charref_poc.safetensors'
CLIP_NAME = 'qwen3.5_9b_moss_image_sft_w4a8_gptq.safetensors'
PREFIX = 'Same character and art style as Picture 1. '


def split_base_qkv(state):
    """Split output rows and per-output scales; retain ConvRot input-basis metadata."""
    state = state.copy()
    for key in list(state):
        if key.endswith('.comfy_attention.config'):
            state.pop(key)  # Optional native fused-attention acceleration; local attention is equivalent.
            continue
        if not key.endswith('.proj.qkv.weight') or not key.startswith('layers.'):
            continue
        prefix = key.removesuffix('weight')
        weight = state.pop(key)
        if weight.shape[0] % 3:
            raise ValueError('MOSS Base: некорректный объединённый QKV-блок.')
        pieces = weight.chunk(3, dim=0)
        scales = state.pop(prefix + 'weight_scale', None)
        scale_pieces = scales.chunk(3, dim=0) if scales is not None and scales.ndim and scales.shape[0] == weight.shape[0] else [scales] * 3
        quant = state.pop(prefix + 'comfy_quant', None)
        for index, part in enumerate(('q','k','v')):
            target = prefix.removesuffix('qkv.') + part + '.'
            state[target + 'weight'] = pieces[index]
            if scale_pieces[index] is not None:
                state[target + 'weight_scale'] = scale_pieces[index]
            if quant is not None:
                state[target + 'comfy_quant'] = quant
    return state


def local_file(folder, name):
    normalized = str(name).replace('\\', '/')
    match = next((item for item in folder_paths.get_filename_list(folder) if item.replace('\\', '/') == normalized), None)
    if match is None:
        raise ValueError(f'MOSS Reference: файл «{name}» не найден. Установите его и обновите библиотеку.')
    return match, folder_paths.get_full_path_or_raise(folder, match)


def reference_status():
    result = {'ready': False, 'base': BASE_NAME, 'lora': LORA_NAME, 'clip': CLIP_NAME, 'errors': []}
    for key, folder in [('base', 'diffusion_models'), ('lora', 'loras'), ('clip', 'text_encoders')]:
        try:
            _, path = local_file(folder, result[key])
            result[key + '_bytes'] = Path(path).stat().st_size
            if key == 'clip':
                with open(path, 'rb') as stream:
                    size = struct.unpack('<Q', stream.read(8))[0]
                    if size > 8 * 1024 * 1024:
                        raise ValueError('Слишком большой заголовок энкодера.')
                    header = json.loads(stream.read(size))
                result['vision_tensors'] = sum('visual.' in name for name in header)
                if not result['vision_tensors']:
                    result['errors'].append('Энкодер не содержит визуальной части Qwen3.5.')
        except (ValueError, OSError, struct.error) as error:
            result['errors'].append(str(error))
    result['ready'] = not result['errors']
    return result


class MOSSImageReferenceModelLoader:
    @classmethod
    def INPUT_TYPES(cls):
        # STRING keeps missing reference-only files from invalidating unrelated modes.
        return {'required': {'base_name': ('STRING', {'default': BASE_NAME}), 'edit_lora': ('STRING', {'default': LORA_NAME}), 'strength': ('FLOAT', {'default': 1.0, 'min': .01, 'max': 2., 'step': .05})}}
    RETURN_TYPES = ('MODEL',)
    FUNCTION = 'load'
    CATEGORY = 'MOSS-Image/Studio'
    def load(self, base_name, edit_lora, strength):
        import nodes
        import comfy.utils
        name, path = local_file('diffusion_models', base_name)
        adapter, _ = local_file('loras', edit_lora)
        loader = nodes.NODE_CLASS_MAPPINGS.get('MOSSImageUNETLoader')
        if loader is None:
            raise ValueError('Не установлен загрузчик moss-image. Перезапустите ComfyUI после установки.')
        # Reuse the installed plugin's loader/quantization path with canonical
        # separate Q/K/V keys. Never modify the checkpoint on disk.
        loaders = importlib.import_module(loader.__module__.rpartition('.')[0] + '.loaders')
        state, metadata = comfy.utils.load_torch_file(path, return_metadata=True)
        model = loaders.load_model_state(split_base_qkv(state), None, False, metadata=metadata)
        return MOSSImageLoRAStack().apply(model, json.dumps([{'name': adapter, 'strength': strength, 'enabled': True}]))


class MOSSImageReferencePatch:
    @classmethod
    def INPUT_TYPES(cls):
        return {'required': {'model': ('MODEL',), 'kv_cache': ('BOOLEAN', {'default': True})}}
    RETURN_TYPES = ('MODEL',)
    FUNCTION = 'patch'
    CATEGORY = 'MOSS-Image/Studio'
    def patch(self, model, kv_cache):
        return (patch_reference_model(model, kv_cache),)


def fit_reference(image, pixels, snap=16):
    if image.ndim != 4 or image.shape[0] != 1:
        raise ValueError('Выберите одно изображение-референс.')
    height, width = image.shape[1:3]
    scale = min(1., math.sqrt(pixels / (height * width)))
    target_h, target_w = max(snap, round(height * scale / snap) * snap), max(snap, round(width * scale / snap) * snap)
    value = image[..., :3].movedim(-1, 1)
    return F.interpolate(value, size=(target_h, target_w), mode='bicubic', align_corners=False).movedim(1, -1).clamp(0, 1)


def vision_tokens(clip, prompt, image):
    # Local MOSS tokenizer has the correct chat template, but doesn't substitute
    # image-pad tokens. Match Qwen35ImageTokenizer without changing either plugin.
    text = 'Picture 1: <|vision_start|><|image_pad|><|vision_end|>' + prompt
    tokens = clip.tokenize(text)
    replaced = 0
    for rows in tokens.values():
        for row in rows:
            for index, token in enumerate(row):
                if token[0] == 248056:
                    row[index] = ({'type': 'image', 'data': image, 'original_type': 'image'},) + token[1:]
                    replaced += 1
    if replaced != 1:
        raise ValueError('MOSS Reference: энкодер не поддерживает визуальный токен Qwen3.5.')
    return tokens


class MOSSImageReferenceConditioning:
    @classmethod
    def INPUT_TYPES(cls):
        return {'required': {'clip': ('CLIP',), 'vae': ('VAE',), 'image': ('IMAGE',), 'positive': ('STRING', {'multiline': True, 'default': ''}), 'negative': ('STRING', {'multiline': True, 'default': ''}), 'reference_megapixels': ('FLOAT', {'default': 1., 'min': .1, 'max': 1., 'step': .1})}}
    RETURN_TYPES = ('CONDITIONING', 'CONDITIONING')
    RETURN_NAMES = ('positive', 'negative')
    FUNCTION = 'encode'
    CATEGORY = 'MOSS-Image/Studio'
    def encode(self, clip, vae, image, positive, negative, reference_megapixels):
        if not positive.strip():
            raise ValueError('Опишите новую сцену, позу и внешность персонажа.')
        vl = fit_reference(image, 384 * 384)
        reference = vae.encode(fit_reference(image, reference_megapixels * 1_000_000))
        result = []
        for prompt in (PREFIX + positive, negative):
            conditioning = clip.encode_from_tokens_scheduled(vision_tokens(clip, prompt, vl))
            result.append(node_helpers.conditioning_set_values(conditioning, {'reference_latents': [reference]}, append=True))
        return tuple(result)


class MOSSImageImproveMode:
    @classmethod
    def INPUT_TYPES(cls):
        return {'required': {'image': ('BOOLEAN', {'default': False}), 'reference': ('BOOLEAN', {'default': False})}}
    RETURN_TYPES = ('BOOLEAN',)
    FUNCTION = 'select'
    CATEGORY = 'MOSS-Image/Studio'
    def select(self, image, reference):
        return (image and not reference,)
