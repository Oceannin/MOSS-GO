import json
import math

from safetensors import SafetensorError, safe_open


def parse_adapters(value):
    try:
        rows = json.loads(value)
    except (json.JSONDecodeError, TypeError) as error:
        raise ValueError('Список LoRA повреждён. Удалите строку и добавьте LoRA заново.') from error
    if not isinstance(rows, list):
        raise ValueError('Список LoRA должен содержать строки с файлом, силой и переключателем.')
    result = []
    for index, row in enumerate(rows, 1):
        if not isinstance(row, dict):
            raise ValueError(f'LoRA #{index}: неверная строка.')
        name = row.get('name', '')
        strength = row.get('strength', 1.0)
        enabled = row.get('enabled', True)
        if not isinstance(name, str) or not isinstance(enabled, bool):
            raise ValueError(f'LoRA #{index}: неверный файл или переключатель.')
        if not enabled:
            continue
        if isinstance(strength, bool) or not isinstance(strength, (int, float)) or not math.isfinite(strength):
            raise ValueError(f'LoRA #{index} «{name}»: сила должна быть конечным числом.')
        if strength != 0:
            if not name.strip():
                raise ValueError(f'LoRA #{index}: выберите файл или выключите строку.')
            result.append(dict(name=name, strength=float(strength)))
    return result


def inspect_adapter(path):
    if not str(path).lower().endswith('.safetensors'):
        return dict(architecture='Не определена', compatible=None)
    with safe_open(str(path), framework='pt', device='cpu') as file:
        metadata = file.metadata() or {}
        keys = file.keys()
    base = metadata.get('ss_base_model_version', '').lower()
    if 'moss' in base:
        return dict(architecture='MOSS Image', compatible=True)
    if base and base not in ('unknown', 'other'):
        architecture = 'SDXL / SD' if 'sdxl' in base or base.startswith('sd_') else 'Z-Image' if 'zimage' in base else base
        return dict(architecture=architecture, compatible=False)
    if any(key.startswith('diffusion_model.layers.') and '.proj.ffn_up_gate.' in key for key in keys):
        return dict(architecture='MOSS Image', compatible=True)
    if 'sdxl' in base or any(key.startswith(('lora_te1_', 'lora_te2_', 'lora_unet_down_blocks_')) for key in keys):
        return dict(architecture='SDXL / SD', compatible=False)
    return dict(architecture=base or 'Не определена', compatible=None)
