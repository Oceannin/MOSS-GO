# 0.1.0-rc.1 — contest preview

MOSS GO is a standalone local studio over the ComfyUI API. This preview includes
creation, character reference scenes, masked refinement, sequential scene packs,
durable takes and versions, portable recipes and compiled ComfyUI graph export.
The default language is English; explicit language and theme choices persist.

The interface includes three original references and a safe character constructor.
An optional local prompt assistant presents changes for explicit review. Neither
loading an example nor preparing settings starts image generation.

## Evidence

- Real creation, an 18-case reference follow-up and six localized refinement cases
  on RTX 4070 Ti SUPER 16 GB / 32 GB system RAM, Windows. See [BENCHMARK](BENCHMARK.md).
- Fresh standalone studio installation from source and wheel on Windows Python 3.12,
  without Torch or ComfyUI in the studio environment.
- Hosted installed-wheel CPU checks passed on Windows and Ubuntu with Python
  3.11 and 3.13: [four passing jobs](https://github.com/Oceannin/MOSS-GO/actions/runs/41044203888).
- The recorded release-candidate demo completed a real reference scene and a
  masked color edit. Both retained 768×1024 output; pixels outside the softened
  edit mask matched the source. [Demo details](DEMO.md).
- CPU tests cover persistence, validation, recipe handling, launch recovery,
  addressed queue ownership and controlled memory-failure handling.
- Responsive checks cover both themes and languages at five viewport sizes.
  Mobile settings follow the keyboard order, actions wrap, and offline status is explicit.

## Known limits

- This is a release candidate. A clean ComfyUI GPU-runtime installation and physical
  12/24 GB cards have not been validated. Linux GPU execution is unverified;
  the standalone studio has passing Ubuntu CPU CI. Hardware profiles are recommendations.
- Experimental MOSS CharRef and High precision need additional weights outside
  the verified default packs. CharRef is excluded from the contest demonstration.
- Sampling-stage cancellation still needs a manual check. Earlier ownership
  checks do not establish sampling-stage behavior for every runtime revision.
- Real browser UI zoom at 200% and a screen-reader walkthrough remain manual checks.
  Image inspection at 200% is a separate, implemented feature.
- The reference scores are limited development evidence for illustrated characters,
  not a general identity guarantee or an independently blinded evaluation.
- The studio binds to loopback. No public inference service is provided.

Optional checks are in [the manual checklist](MANUAL_CHECK_RU.md). They are not
represented as passing checks in this release.
