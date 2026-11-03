# FLUX 3 contest integration

Status: Gates A, B and C passed on actual hardware: official probes, UI Create,
Reference and Refine, followed by the frozen 13-case evaluation and three legacy
engine runs. Gate D package/publication checks are recorded with the release;
manual exceptions remain explicit. See [FLUX3_BENCHMARK](FLUX3_BENCHMARK.md).

## Scope and execution gates

FLUX 3 Image Klein distilled must run Create, Reference and masked Refine on the
RTX 4070 Ti SUPER 16 GB / 32 GB RAM Windows machine. Retain explicit legacy engine
choices, stored jobs and recipe compatibility. Never fall back silently.

1. **Gate A:** run the official model through isolated ComfyUI, with actual image
   output and measured time/memory, before modifying application execution.
2. **Gate B:** complete an application job with its actual execution graph,
   original/expanded prompt and correct model identifiers saved in history.
3. **Gate C:** execute all three modes, verify reference identity and localized
   mask compositing, and reproduce an exported workflow.
4. **Gate D:** run applicable Python/Node checks and real GPU regression cases;
   publish only claims supported by the resulting evidence.

The official current deadline is November 3, 2026 at 09:00 PST (17:00 UTC,
22:00 Asia/Yekaterinburg). Stop feature development by 16:00 UTC; reserve the
remaining hour for critical fixes, release verification and author submission.
The final competition form requires the author's explicit approval.

## Focused change plan

The existing application is Python/aiohttp with plain JavaScript modules and
SQLite persistence. Generation is serial, with native ComfyUI API graphs and
durable submission/recovery identifiers. Preserve these systems.

- `moss_go/flux3.py` (new): model-specific graph adapter, using official FLUX 3
  CLIP loading, prompt generation, image conditioning and sampling settings.
- `moss_go/workflows.py`, `settings.py`, `readiness.py`: explicit engine selection,
  exact model roles, mode-specific readiness, validated parameters and defaults.
- `moss_go/runner.py`, `comfy.py`, `store.py`: reuse execution/recovery and saved
  graphs; add expanded prompt/component metadata without rewriting old jobs.
- `moss_go/recipes.py`: preserve executed graphs and new parameters while keeping
  existing recipe import compatible.
- `moss_go/assets/model_manifest.json`, `model_setup.py`: pinned official files,
  hashes, license-specific access guidance and no restricted weights in Git.
- `moss_go/web/app.js`, `equipment.js`, `index.html`, `i18n.js`: recommended engine,
  relevant controls, actual result metadata, English default and Russian locale.
- Focused tests under `tests/`, plus actual GPU evidence, workflows and original
  output assets; update README, landing, licenses, changelog and release notes
  after execution gates pass.

## Runtime baseline and official specification

- Original ComfyUI: 0.39.0, source `08ff3c11`; preserve it unchanged.
- Isolated validation ComfyUI: v0.41.2, source
  `b53f77a74e21091cbdebfdf7b85fc80326932646`; existing compatible Torch/CUDA
  packages are reused without changing the portable Python installation.
- Official model repository:
  `black-forest-labs/flux-3-image-klein-comfy`, pinned revision
  `9d36114cf7a2e03a45c28f5cc4987d20ebfdb6c1`.
- Start with `flux3-image-klein-int8-convrot.safetensors`,
  `qwen3vl_4b_int8_convrot.safetensors`, the official Qwen3.5 9B prompt upsampler,
  and the exact compatible `flux2-vae.safetensors`. NVFP4 is excluded on Ada.
- The new VAE is installed as `flux3-vae.safetensors` without changing its bytes.
  Its hash differs from the previous FLUX.2 VAE, so the distinct name preserves
  legacy graphs instead of overwriting their identically named component.
- Official distilled defaults: 16 steps, CFG 1, Euler/simple; the official
  template also sets Flux model sampling shifts to ln(16). Do not reuse the
  FLUX.2 four-step graph by changing its checkpoint.
- Bounding boxes guide layout; they are not pixel masks. Reuse source-coordinate
  crop, feathering and compositing for strict outside-mask preservation.
- The checkpoint uses FLUX Kommunity License, separately from Apache-2.0 app
  code. The encoder and prompt upsampler have their own Apache-2.0 notices.

## Local evidence and rollback

Private downloads, official templates, runtime checkout, hardware measurements
and raw validation records live under `.local/flux3/`, excluded from publication.
Only reviewed original outputs and non-secret reproducibility evidence may be
copied into public documentation.

Development is isolated on `feature/flux3-contest-release`. Publication keeps
the existing public repository history and excludes private development data.
The public previous release and its artifacts remain available at
<https://github.com/Oceannin/MOSS-GO/releases/tag/v0.1.0-rc.1>.
No database migration or deletion is planned. A separate validation catalog keeps
existing user data intact.

An additive `execution_results` table records observed captions without mutating
the launch graph/settings snapshot. Existing schema-2 catalogs and legacy jobs
remain readable; existing tables and rows are preserved.
