import hashlib
import json
import os

import comfy.lora
import comfy.lora_convert
import comfy.utils
from comfy.weight_adapter.lora import LoRAAdapter
import folder_paths

from .adapters import SafetensorError, inspect_adapter, parse_adapters


def resolve_adapter(name):
    if name not in folder_paths.get_filename_list('loras'):
        raise ValueError(f'LoRA «{name}» не найдена в библиотеке ComfyUI. Обновите список и выберите файл.')
    return folder_paths.get_full_path_or_raise('loras', name)


def validate_patch_shapes(patches, state, name):
    for key, patch in patches.items():
        if isinstance(patch, LoRAAdapter):
            up, down, _, mid, _, reshape = patch.weights
            target = state[key].shape
            if mid is None and reshape is None and len(target) == up.ndim == down.ndim == 2:
                if up.shape[1] != down.shape[0] or (up.shape[0], down.shape[1]) != tuple(target):
                    raise ValueError(f'LoRA «{name}» несовместима с MOSS: размер слоя {key} не совпадает.')


def split_moss_qkv(weights, key_map, state, name):
    converted = weights.copy()
    for down_name in weights:
        if not down_name.endswith('.proj.qkv.lora_A.weight'):
            continue
        source = down_name.removesuffix('.lora_A.weight')
        targets = [source.removesuffix('qkv') + part for part in ('q', 'k', 'v')]
        if not all(target in key_map for target in targets):
            continue
        up_name = source + '.lora_B.weight'
        if up_name not in weights:
            raise ValueError(f'LoRA «{name}»: отсутствует парный QKV-блок {up_name}.')
        up, down = weights[up_name], weights[down_name]
        sizes = [state[key_map[target]].shape[0] for target in targets]
        if up.ndim != 2 or down.ndim != 2 or up.shape[0] != sum(sizes) or up.shape[1] != down.shape[0]:
            raise ValueError(f'LoRA «{name}»: QKV-блок не подходит для выбранной MOSS.')
        pieces = up.split(sizes, dim=0)
        dora = weights.get(source + '.dora_scale')
        dora_pieces = dora.split(sizes, dim=0) if dora is not None else None
        for index, target in enumerate(targets):
            converted[target + '.lora_A.weight'] = down
            converted[target + '.lora_B.weight'] = pieces[index].clone()
            if source + '.alpha' in weights:
                converted[target + '.alpha'] = weights[source + '.alpha']
            if dora_pieces is not None:
                converted[target + '.dora_scale'] = dora_pieces[index].clone()
        for key in (down_name, up_name, source + '.alpha', source + '.dora_scale'):
            converted.pop(key, None)
    return converted


class MOSSImageLoRAStack:
    @classmethod
    def INPUT_TYPES(cls):
        return {'required': {
            'model': ('MODEL',),
            'adapters': ('STRING', {'default': '[]', 'multiline': False}),
        }}

    RETURN_TYPES = ('MODEL',)
    RETURN_NAMES = ('model',)
    FUNCTION = 'apply'
    CATEGORY = 'MOSS-Image/Studio'
    DESCRIPTION = 'Общий список LoRA для модели MOSS. Пустой список не изменяет модель.'

    @classmethod
    def VALIDATE_INPUTS(cls, adapters):
        try:
            for row in parse_adapters(adapters):
                path = resolve_adapter(row['name'])
                info = inspect_adapter(path)
                if info['compatible'] is False:
                    return f'LoRA «{row["name"]}» обучена для {info["architecture"]} и не подходит для MOSS Image.'
        except (ValueError, OSError, SafetensorError) as error:
            return str(error)
        return True

    @classmethod
    def IS_CHANGED(cls, adapters, **kwargs):
        files = []
        for row in parse_adapters(adapters):
            stat = os.stat(resolve_adapter(row['name']))
            files.append((row, stat.st_size, stat.st_mtime_ns))
        return hashlib.sha256(json.dumps(files, sort_keys=True).encode()).hexdigest()

    def apply(self, model, adapters):
        rows = parse_adapters(adapters)
        if not rows:
            return (model,)
        key_map = comfy.lora.model_lora_keys_unet(model.model, {})
        state = model.model.state_dict()
        result = model.clone()
        for row in rows:
            name = row['name']
            path = resolve_adapter(name)
            if inspect_adapter(path)['compatible'] is False:
                raise ValueError(f'LoRA «{name}» не подходит для MOSS Image.')
            weights = comfy.utils.load_torch_file(path, safe_load=True)
            weights = comfy.lora_convert.convert_lora(weights)
            weights = split_moss_qkv(weights, key_map, state, name)
            patches = comfy.lora.load_lora(weights, key_map, log_missing=False)
            if not patches:
                raise ValueError(f'LoRA «{name}» несовместима с MOSS: подходящие слои не найдены.')
            consumed = set()
            for patch in patches.values():
                if hasattr(patch, 'loaded_keys'):
                    consumed.update(patch.loaded_keys)
            missing = set(weights) - consumed
            if missing:
                example = sorted(missing)[0]
                raise ValueError(f'LoRA «{name}» загружается не полностью: не поддерживается {example}.')
            validate_patch_shapes(patches, state, name)
            applied = result.add_patches(patches, row['strength'])
            if set(applied) != set(patches):
                raise ValueError(f'LoRA «{name}» несовместима с MOSS: применены не все слои.')
        return (result,)
