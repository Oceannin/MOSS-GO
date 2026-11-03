# Narrated demonstration provenance

The primary video is `demo-flux3-voiced-20261103.mp4`: **117.4 seconds**, 1920×1080 H.264 with
48 kHz stereo AAC. Its audio and video streams have equal duration. Every visual
is an actual application capture or a labeled original result. Frame holds were
retimed for narration; generation waiting is explicitly omitted.

## Generation

- Voice: Fish Audio Drama 3, installed `drama3_w4a8experts_bf16.safetensors`,
  with `drama3_codec.safetensors`, through existing ComfyUI-Drama3 revision
  `67a733a96890637dc27b1914974ad00c569405fb`. Fish Audio Community License v1.0.
- The narrator reference is six seconds of our own Drama 3 generation, not a
  real person's likeness. Fourteen short cue generations use that synthetic
  anchor, seed 71, temperature 1, top-p 0.9 and top-k 0.
- Original instrumental accompaniment: installed `yue2_3b_bf16.safetensors`,
  metadata origin `m-a-p/YuE2-3B`, CC-BY-NC-4.0. Native ComfyUI Yue2 generation,
  seed 71, 112 seconds, 32-step DPM-2 / SGM-uniform synthesis. No reference song
  or named artist imitation was requested.
- The author confirmed separate permission for the contest promotional video
  on November 3. This is an author-provided permission statement, not a general
  commercial-use claim about the upstream license. Raw music stems remain local.
- Models were already installed. An isolated ComfyUI 0.41.2 process used the
  existing GPU packages. No dependency upgrade or model download was required.

## Verification and edit

Qwen3-ASR 0.6B checked all 14 cues. Normalized token agreement was 1.0 for every
cue and for the final mixed soundtrack, including the numerical results and the
failed walking case. This is an automatic intelligibility/transcript check,
not an independent listening study. The initial long narration had truncated
endings and was discarded; the published version uses the complete short cues.

Narration tempo adjustment: 1.02×, preserving pitch. Music is time-fitted to the
video, normalized quietly and ducked under speech. Measured final loudness:
**-16.48 LUFS**, true peak
**-4.36 dBTP**. English WebVTT captions are included.

[Machine-readable provenance, cues and transcript](evidence/presentation-audio.json)
records the actual media SHA-256: `4ee95a247354e6afa4fb82becf65106426c4beb469e40eb9e75bfa1033aebffa`.
The release's presentation-workflows ZIP retains actual API graphs, cue text,
timing and transcript evidence. It is an audit kit, not a bundled speech/music
feature or a redistribution of model weights. Local stems are outside that kit.

The original 106-second silent FLUX 3 walkthrough remains `demo.mp4`. The old
107.53-second FLUX.2 walkthrough remains attached to v0.1.0-rc.1. Those files
are not relabeled as newly generated footage.
