"""Reference-token conditioning for the local OpenMOSS transformer implementation.

Adapted from Ostris' index_timestep_zero / cached reference attention design.
See THIRD_PARTY_OSTRIS_LICENSE.txt. No global model or ComfyUI changes.
"""
import hashlib
import math
import torch
from comfy.ldm.modules.attention import optimized_attention
from ..reference_memory import reference_memory_shape


def image_ids(index, frame, height, width, device):
    ids = torch.zeros(height * width, 4, device=device, dtype=torch.float32)
    ids[:, 0] = index
    ids[:, 1] = frame
    ids[:, 2] = (torch.arange(height, device=device) - (height - 1) / 2).repeat_interleave(width)
    ids[:, 3] = (torch.arange(width, device=device) - (width - 1) / 2).repeat(height)
    return ids


def rope_for_ids(dit, ids, dtype):
    bands = dit.rope._default_bands(ids.device)
    phase = ids.unsqueeze(-1) * bands
    return torch.cat((phase.sin(), phase.cos()), -2).flatten(-2).unsqueeze(0).to(dtype)


def rotate(tensor, rope):
    sin, cos = rope.chunk(2, -1)
    sin = torch.cat((sin, sin), -1).unsqueeze(-2)
    cos = torch.cat((cos, cos), -1).unsqueeze(-2)
    first, second = tensor.chunk(2, -1)
    return tensor * cos + torch.cat((-second, first), -1) * sin


def time_vectors(dit, timestep, dtype):
    half = dit.freq_dim // 2
    frequency = 10000 ** (-torch.arange(half, device=timestep.device, dtype=torch.float64) / half)
    phase = timestep.double().reshape(-1, 1) * frequency
    embedding = torch.cat((phase.cos(), phase.sin()), -1).float()
    vector = dit.time_embedding(embedding.to(dit.time_embedding[0].weight.dtype)).float()
    modulation = dit.shared_block_modulation(vector.to(dit.shared_block_modulation.weight.dtype)).view(-1, 6, 1, vector.shape[-1])
    return vector, modulation.to(dtype)


def block_forward(block, hidden, rope, modulation, reference_mod=None, split=None, capture=None, cached=None):
    shift_a, scale_a, gate_a, shift_f, scale_f, gate_f = modulation.unbind(1)
    def normalized(norm, value, shift, scale, index):
        value = norm(value)
        if reference_mod is None:
            return value * (1 + scale) + shift
        rshift, rscale = reference_mod[:, index], reference_mod[:, index + 1]
        return torch.cat((value[:, :split] * (1 + scale) + shift, value[:, split:] * (1 + rscale) + rshift), 1)
    def gated(value, gate, index):
        if reference_mod is None:
            return value * gate
        return torch.cat((value[:, :split] * gate, value[:, split:] * reference_mod[:, index]), 1)
    dtype = block.proj['q'].weight.dtype
    value = normalized(block.norm1, hidden, shift_a, scale_a, 0).to(dtype)
    query = block.q_norm(block.proj['q'](value).unflatten(-1, (block.heads, -1)))
    key = block.k_norm(block.proj['k'](value).unflatten(-1, (block.heads, -1)))
    query, key = rotate(query, rope), rotate(key, rope)
    value = block.proj['v'](value).unflatten(-1, (block.heads, -1))
    if capture is not None:
        capture.append((key, value))
    if cached is not None:
        key, value = torch.cat((key, cached[0].to(key.dtype)), 1), torch.cat((value, cached[1].to(value.dtype)), 1)
    attention = optimized_attention(query.transpose(1, 2), key.transpose(1, 2), value.transpose(1, 2), block.heads, skip_reshape=True)
    hidden = hidden + gated(block.proj['o'](attention), gate_a, 2)
    value = normalized(block.norm2, hidden, shift_f, scale_f, 3).to(dtype)
    up, gate = block.proj['ffn_up_gate'](value).chunk(2, -1)
    activated = (4 * torch.tanh(gate / 4) * torch.sigmoid(gate)) * (25 * torch.tanh(up / 25))
    return hidden + gated(block.proj['ffn_down'](activated), gate_f, 5)


def run_blocks(dit, hidden, rope, modulation, options, *, reference_mod=None, split=None, capture=None, cache=None):
    replacements = options.get('patches_replace', {}).get('dit', {})
    options['total_blocks'], options['block_type'] = len(dit.layers), 'single'
    for index, block in enumerate(dit.layers):
        options['block_index'] = index
        def execute(args, block=block, index=index):
            recorded = [] if capture is not None else None
            output = block_forward(block, args['img'], args.get('pe', rope), args.get('vec', modulation), reference_mod, split, recorded, cache.get(index) if cache else None)
            if recorded:
                capture[index] = recorded[0]
            return {'img': output}
        args = {'img': hidden, 'pe': rope, 'vec': modulation, 'transformer_options': options}
        if ('single_block', index) in replacements:
            hidden = replacements[('single_block', index)](args, {'original_block': execute})['img']
        else:
            hidden = execute(args)['img']
    return hidden


def ref_fingerprint(references, batch, text_length, skipped):
    digest = hashlib.sha256()
    digest.update(repr((batch, text_length, skipped)).encode())
    for reference in references:
        # Exact content key: equal sums alone can alias different references.
        value = reference.detach().to(device='cpu', dtype=torch.float32).contiguous()
        digest.update(repr(tuple(value.shape)).encode())
        digest.update(value.numpy().tobytes())
    return digest.hexdigest()


def make_reference_forward(dit, original, kv_cache=True):
    state = {'last_time': None, 'caches': {}}
    def forward(x, timestep, context, attention_mask=None, transformer_options=None, ref_latents=None, **kwargs):
        options = {} if transformer_options is None else transformer_options.copy()
        if not ref_latents:
            return original(x, timestep, context, attention_mask=attention_mask, transformer_options=options, **kwargs)
        if x.ndim != 4 or x.shape[1] != dit.latent_channels:
            raise ValueError('MOSS Reference: неверный размер латента.')
        batch, _, height, width = x.shape
        times = torch.as_tensor(timestep, device=x.device, dtype=torch.float32).reshape(-1).expand(batch)
        mask = attention_mask if attention_mask is not None else torch.ones(context.shape[:2], device=context.device, dtype=torch.bool)
        if mask.shape != context.shape[:2] or not torch.all((mask == 0) | (mask == 1)):
            raise ValueError('MOSS Reference: неверная маска текста.')
        current_time = float(times.max())
        if state['last_time'] is None or current_time > state['last_time']:
            state['caches'].clear()
        state['last_time'] = current_time
        skipped = tuple(sorted(key[1] for key in options.get('patches_replace', {}).get('dit', {}) if isinstance(key, tuple) and key[0] == 'single_block'))
        outputs = []
        for sample in range(batch):
            text_context = context[sample:sample + 1, mask[sample].bool()]
            text_length = text_context.shape[1]
            if not text_length:
                raise ValueError('MOSS Reference: текст не содержит токенов.')
            dtype = dit.video_embedder.weight.dtype
            video = dit.video_embedder(x[sample:sample + 1].flatten(2).transpose(1, 2).to(dtype).contiguous())
            dtype = video.dtype
            text_ids = torch.zeros(text_length, 4, device=x.device)
            text_ids[:, 1] = torch.arange(text_length, device=x.device)
            main_ids = torch.cat((image_ids(0, text_length, height, width, x.device), text_ids))
            main_rope = rope_for_ids(dit, main_ids, dtype)
            text = dit.text_embedder(text_context, main_rope[:, height * width:])
            vector, modulation = time_vectors(dit, times[sample:sample + 1], dtype)
            refs, ids = [], []
            for ref_index, reference in enumerate(ref_latents):
                if reference.ndim == 5 and reference.shape[2] == 1:
                    reference = reference.squeeze(2)
                if reference.ndim != 4 or reference.shape[1] != dit.latent_channels or reference.shape[0] not in (1, batch):
                    raise ValueError('MOSS Reference: размер референса не совместим с моделью.')
                reference = reference[0:1] if reference.shape[0] == 1 else reference[sample:sample + 1]
                refs.append(reference.to(device=x.device, dtype=dtype))
                ids.append(image_ids(ref_index + 1, text_length, *reference.shape[-2:], x.device))
            ref_rope = rope_for_ids(dit, torch.cat(ids), dtype)
            ref_tokens = torch.cat([ref.flatten(2).transpose(1, 2) for ref in refs], 1)
            _, zero_mod = time_vectors(dit, torch.zeros_like(times[sample:sample + 1]), dtype)
            if kv_cache:
                key = ref_fingerprint(refs, batch, text_length, skipped)
                cached = state['caches'].get(key)
                if cached is None:
                    cached = {}
                    run_blocks(dit, dit.video_embedder(ref_tokens), ref_rope, zero_mod, options.copy(), capture=cached)
                    if len(state['caches']) >= 4:
                        state['caches'].pop(next(iter(state['caches'])))
                    state['caches'][key] = cached
                hidden = run_blocks(dit, torch.cat((video, text), 1), main_rope, modulation, options, cache=cached)
            else:
                rope = torch.cat((main_rope, ref_rope), 1)
                hidden = run_blocks(dit, torch.cat((video, text, dit.video_embedder(ref_tokens)), 1), rope, modulation, options, reference_mod=zero_mod, split=height * width + text_length)
            head = dit.video_head_modulation(vector.to(dit.video_head_modulation.weight.dtype)).view(1, 2, -1)
            hidden = dit.final_norm_video(hidden[:, :height * width].to(dit.final_norm_video.weight.dtype))
            hidden = hidden * (1 + head[:, 1, None]) + head[:, 0, None]
            hidden = dit.final_linear_video(hidden.to(dit.final_linear_video.weight.dtype))
            outputs.append(hidden.transpose(1, 2).reshape(1, -1, height, width))
        return torch.cat(outputs)
    def clear_cache():
        state['caches'].clear()
        state['last_time'] = None
    forward.clear_reference_cache = clear_cache
    return forward


def patch_reference_model(model, kv_cache=True):
    import comfy.conds
    result = model.clone()
    base, dit = result.model, result.get_model_object('diffusion_model')
    if not all(hasattr(dit, name) for name in ('rope', 'freq_dim', 'layers', 'text_embedder')) or not hasattr(dit.rope, '_default_bands'):
        raise ValueError('MOSS Reference: требуется локальная нода MOSSImageUNETLoader из moss-image.')
    original_conds, original_shapes = base.extra_conds, base.extra_conds_shapes
    def extra_conds(**kwargs):
        out = original_conds(**kwargs)
        references = kwargs.get('reference_latents')
        if references:
            out['ref_latents'] = comfy.conds.CONDList([base.process_latent_in(ref) for ref in references])
        return out
    def extra_shapes(**kwargs):
        out = original_shapes(**kwargs)
        references = kwargs.get('reference_latents')
        if references:
            out['ref_latents'] = reference_memory_shape([tuple(ref.shape) for ref in references], dit.latent_channels)
        return out
    result.add_object_patch('extra_conds', extra_conds)
    result.add_object_patch('extra_conds_shapes', extra_shapes)
    result.add_object_patch('memory_usage_factor_conds', tuple(set(base.memory_usage_factor_conds) | {'ref_latents'}))
    forward = make_reference_forward(dit, dit.forward, kv_cache)
    result.add_object_patch('diffusion_model.forward', forward)
    import comfy.patcher_extension
    def sampling_scope(executor, *args, **kwargs):
        forward.clear_reference_cache()
        try:
            return executor(*args, **kwargs)
        finally:
            # Do not pin reference K/V in VRAM during downstream SFT/FaceDetailer.
            forward.clear_reference_cache()
    result.add_wrapper_with_key(comfy.patcher_extension.WrappersMP.OUTER_SAMPLE, 'moss_studio_reference', sampling_scope)
    return result
