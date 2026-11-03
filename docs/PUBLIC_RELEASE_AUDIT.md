# Final public release audit — November 3, 2026

## Public state found

At the start of this audit, `origin/main` was already
`8bf02fbaff54ee24364fba478687cd571c325d6d`, the FLUX 3 application release.
Tag `v0.2.0-rc.1` points to that commit. GitHub Pages was built successfully
from the same commit, using `main:/docs`. A live signed-out browser showed the
FLUX 3 README; the search retrieval showed an older 0.1 README snapshot.
No missing unpublished application change was found by comparing that public
snapshot with the working FLUX 3 adapter and execution evidence.

The development checkout has a separate private history and an older local
`main`; that local branch is not the public repository's `origin/main`.
The public checkout's existing history, both release tags, prior artifacts and
user data were preserved. The final presentation changes were prepared on
`release/final-public-audit` for a reviewed fast-forward publication.

## Verified functionality

- Dedicated FLUX 3 native graphs and a FLUX 3 default in Create, Reference and
  Refine. The actual core uses the INT8 distilled model and official local
  image-aware prompt upsampler; no silent FLUX.2 fallback.
- All 13 saved evaluation jobs matched successful native ComfyUI histories
  during this audit. These are existing real executions, not new mocked GPU tests.
- Three actual UI modes, persistent history, original/observed prompt metadata,
  exact graph export, old/new recipe import and actual legacy engine runs.
- Four tested edits retained size and zero outside-effective-mask pixel changes.
  Native exported Refine replay ran with no cached nodes and was pixel-identical
  on the measured setup. [Execution review](evidence/public-audit-gpu-review.json).
- [Four installed-package Windows/Ubuntu × Python 3.11/3.13 jobs passed](https://github.com/Oceannin/MOSS-GO/actions/runs/41630755942).
  Local results: 119 Python passes, one Windows symlink skip, 30 Node passes,
  syntax/format checks, fresh wheel/source installs and archive/HTTP/CLI smoke.
- Actual public Pages content and resource downloads. Responsive CSS at 390 and
  320 px was checked using live browser iframes: no horizontal overflow and the
  demo CTA worked. This is not a physical mobile-device test.

## Presentation update

The README and landing now identify the November 3 FLUX 3 release explicitly,
show original-reference scene results, actual Before/Mask/After images, the
studio UI, setup/download links and native graph/recipe reproduction guidance.
Openjutsu informed the result-first presentation; its branding/assets were not copied.
The new named 117.4-second video uses actual FLUX 3 captures with Drama 3 narration,
Yue2 accompaniment and English captions. [Audio provenance](AUDIO_PROVENANCE.md)
documents generated sources, model licenses, permission and verification.
The separate filename prevents reuse of a cached October 30 video URL.

The immutable application tag/binaries remain at `8bf02fb`; presentation-only
updates are visible in [main's history](https://github.com/Oceannin/MOSS-GO/commits/main/).
[Latest Actions](https://github.com/Oceannin/MOSS-GO/actions) and the Pages build
record identify the deployment commit. Release artifacts carry their own checksums.

## Limits and author actions

Only RTX 4070 Ti SUPER 16 GB / 32 GB RAM / Windows has real GPU evidence.
Other physical GPU sizes, BF16, Linux GPU and a clean driver/Torch installation
remain unverified. Identity was recognizable in 6/6 limited illustrated cases,
requested action/pose in 5/6; the failed Mira walk is retained. Live sampling
cancellation, screen-reader navigation, 200% browser zoom and the new application's
narrow-screen controls remain manual checks. The public landing has separate
responsive verification. [Manual checklist](MANUAL_CHECK_RU.md).

No application feature, dependency upgrade or broad refactor was added during
this audit. The author still owns the social post, agreements and submission.
No competition form was sent. Deadline: November 3, 09:00 PST = 17:00 UTC =
22:00 Asia/Yekaterinburg. [Submission fields and URLs](SUBMISSION_RU.md).
