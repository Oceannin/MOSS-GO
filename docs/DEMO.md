# FLUX 3 demonstration — 0.2.0-rc.1

[Watch](https://oceannin.github.io/MOSS-GO/) or download
[the MP4](https://oceannin.github.io/MOSS-GO/demo-flux3-voiced-20261103.mp4).

The **1:57 English narrated walkthrough** uses actual MOSS GO interface captures and
real FLUX 3 outputs. It is an edited screenshot walkthrough, not a continuous
screen recording. Processing waits are omitted and explicitly labeled. Burned-in captions remain; optional English narration captions are included.
The new soundtrack uses Drama 3 for a synthetic narrator and Yue2 for original
quiet accompaniment. [Audio provenance](AUDIO_PROVENANCE.md) records models,
permissions, actual graphs, cue transcripts and the measured mix. No promotional
image generation replaces the actual interface evidence.

Create shows the actual generated original courier. Reference shows the bundled
original Mira in a station scene. Refine shows the bag selection, teal result,
keyboard comparison, observed expanded prompt and portable recipe export. The
Theo scene strip uses the original anchor and three actual FLUX 3 scene outputs.
Original bundled anchors were created with MOSS-Image SFT; new scenes and edits
use FLUX 3. The separate evaluation records all 13 cases, including the failed
Mira walking pose.

The initial three UI jobs used the FLUX 3 integration build. Final result,
mask, comparison and export captures use the freshly installed 0.2.0rc1 wheel.
Its new-seed Refine job `e1d21a731e634242a5a2c58300f789d0` completed in 35.11 s
with actual prompt and image computation (model-loader/input nodes were cached).
A repeated seed-42 job reused execution cache in 2.09 s; that is not claimed as
uncached generation latency. Saved execution metadata preserves its original
runtime version; exporting it later does not rewrite its provenance.

- FLUX 3 Image Klein distilled INT8 ConvRot; official Qwen3-VL 4B INT8 encoder,
  Qwen3.5 9B INT8 prompt upsampler and compatible VAE.
- Euler/simple, CFG 1, 16 steps, shift ln(16); seed 42 in the original three jobs,
  seed 43 in the final installed-wheel edit.
- RTX 4070 Ti SUPER 16 GB, 32 GB RAM, Windows / isolated ComfyUI 0.41.2.
- Original seed-42 UI edit: 768×1024 retained, 8 px feather radius, 38,105 changed
  pixels, zero outside the effective mask. The close-up refers to that edit.
- Three release ZIPs contain actual Create, Reference and Refine recipes with
  input files, masks where applicable, result, observed caption and native graph.
  Import into 0.2.0rc1 and old 0.1 FLUX.2 ZIP import both prepared work without jobs.
- Exported Refine replay in native ComfyUI used no cached nodes and produced a
  pixel-identical result. See [complete evidence](FLUX3_BENCHMARK.md).

The previous FLUX.2 demo remains attached to the
[0.1.0-rc.1 release](https://github.com/Oceannin/MOSS-GO/releases/tag/v0.1.0-rc.1).
This public page is a recorded demonstration, not a remote inference endpoint.

The original 106-second silent FLUX 3 version remains at `demo.mp4`. The
107.53-second October 30 video demonstrates FLUX.2 and remains with 0.1.0-rc.1.
The narrated edit holds actual captured frames longer for speech; its video and
audio streams both measure 117.4 seconds.
