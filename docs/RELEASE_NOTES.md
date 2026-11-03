# 0.2.0-rc.1 — FLUX 3 local studio

Create, Reference and masked Refine now default to FLUX 3 Image Klein distilled
INT8. The native adapter uses official local Qwen3.5 prompt upsampling,
image-aware conditioning, 16-step Euler/simple sampling and explicit component
identifiers. Failed requests never silently change engines.

Details retains original and actual observed expanded prompts, seed, steps,
precision, model files and runtime versions. Recipes carry the saved API graph,
inputs, mask and outputs. The catalog keeps schema 2, with an additive results
table; existing jobs and explicit FLUX.2/MOSS choices remain readable.

## Verified evidence

- Real UI Create, Reference and Refine on Windows / RTX 4070 Ti SUPER 16 GB /
  32 GB RAM, using the official upsampler. Persistent history survived reload.
- A frozen 13-case FLUX 3 evaluation: 3 Create, 6 Reference, 4 Refine; all jobs
  completed. All four edits preserved every pixel outside the effective
  feathered mask and retained the original dimensions.
- Assistant visual review recognized identity in 6/6 reference cases; requested
  action/pose succeeded in 5/6. The initial Mira walking failure is retained.
- Actual legacy MOSS Create, FLUX.2 Reference and CharRef Reference completed
  on the new runtime. CharRef remains experimental and outside the default demo.
- Idle explicit cache release reduced sampled device memory from 14,524 to
  1,127 MiB. This is not automatic per-job unloading.
- Official model files match four pinned SHA-256 values. Model licensing is
  separate from Apache-2.0 application code.

Full conditions, timings, visual sheets and limitations are in
[FLUX3_BENCHMARK](FLUX3_BENCHMARK.md). Old FLUX.2 scores are not reused.

## Compatibility and rollback

Back up the catalog before switching versions. The new FLUX 3 VAE has a distinct
installed filename, preserving the old pack's different bytes. The prior
[0.1.0-rc.1 release](https://github.com/Oceannin/MOSS-GO/releases/tag/v0.1.0-rc.1)
remains available. Restore that version's environment and catalog backup for a
complete rollback; do not overwrite the original ComfyUI installation.

## Known limits

- Other physical GPU sizes, BF16 high precision and Linux GPU execution are
  unverified. Profiles are budgets, not compatibility promises. Prompt upsampling
  uses substantial RAM; this 32 GB machine had little spare system memory.
- A fresh driver/Torch/CUDA installation was not tested. The isolated runtime
  reused existing GPU packages. CPU package/CI tests are separate evidence.
- Exact limb choreography, gaze and rendered text are not guaranteed. The
  character study uses two original illustrated designs and assistant review,
  not a blinded independent evaluation.
- Sampling-stage cancellation, browser zoom at 200% and screen-reader navigation
  remain manual checks. Controlled queue ownership/recovery/failure tests do
  not establish every runtime's live sampling cancellation behavior.
- The studio binds to loopback; no public inference service is supplied.

See [manual checks](MANUAL_CHECK_RU.md) for explicitly unverified cases.
