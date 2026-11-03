# Studio dependency record

The dedicated studio environment is pinned by `uv.lock` and the hashed
`requirements.lock` export. The declarations below were read from the actual
installed wheels during the fresh Windows check. Each dependency retains its own
license files in its distribution; they are not relicensed by MOSS GO.

| Package | Pinned version | Packaged license declaration |
| --- | --- | --- |
| [aiohappyeyeballs](https://pypi.org/project/aiohappyeyeballs/2.7.1/) | 2.7.1 | PSF-2.0 |
| [aiohttp](https://pypi.org/project/aiohttp/3.14.5/) | 3.14.5 | Apache-2.0 AND MIT (includes llhttp notice) |
| [aiosignal](https://pypi.org/project/aiosignal/1.4.0/) | 1.4.0 | Apache-2.0 |
| [attrs](https://pypi.org/project/attrs/26.1.0/) | 26.1.0 | MIT |
| [frozenlist](https://pypi.org/project/frozenlist/1.8.0/) | 1.8.0 | Apache-2.0 |
| [idna](https://pypi.org/project/idna/3.20/) | 3.20 | BSD-3-Clause |
| [multidict](https://pypi.org/project/multidict/7.2.1/) | 7.2.1 | Apache-2.0 |
| [Pillow](https://pypi.org/project/pillow/12.3.0/) | 12.3.0 | MIT-CMU |
| [propcache](https://pypi.org/project/propcache/0.5.4/) | 0.5.4 | Apache-2.0, including NOTICE |
| [typing_extensions](https://pypi.org/project/typing_extensions/4.16.0/) | 4.16.0, Python below 3.13 | PSF-2.0 |
| [yarl](https://pypi.org/project/yarl/1.25.1/) | 1.25.1 | Apache-2.0, including NOTICE |

The source-build backend is setuptools 84.2.1 (MIT), pinned and hashed in
`build-requirements.lock`. Prettier 3.6.2 (MIT) is pinned by `package-lock.json` for
development checks. The wheel includes the project's Apache-2.0 license,
THIRD_PARTY_NOTICES, the bundled Inter OFL text and the retained reference adapter
MIT notice.

This is the **studio** dependency record. ComfyUI, PyTorch, GPU kernels and the
optional Ollama service have separate environments and licenses. Tested image
weights and their sources are in [MODELS.md](MODELS.md); the optional Qwen model is
in [ASSISTANT.md](ASSISTANT.md). The full GPU environment is not a fresh-install dependency lock.
The additional model-source audit below covers the retained CharRef alternative. Model weights and runtime binaries
are not bundled in the studio wheel or source archive.


## Observed FLUX 3 runtime dependencies

The isolated ComfyUI 0.41.2 source uses the compatible existing portable Python
packages below. Their installed wheel metadata/license files were inspected.
This is a bounded component record, not a new GPU lockfile or a claim that every
unrelated package in the portable environment was executed. Windows, the NVIDIA
driver and CUDA platform binaries are separate host components.

| Package | Observed version | License declaration |
| --- | --- | --- |
| `torch` | 2.14.1+cu130 | Apache-2.0 AND Apache-2.0 WITH LLVM-exception AND BSD-2-Clause AND BSD-3-Clause AND BSL-1.0 AND MIT |
| `torchvision` | 0.29.1+cu130 | BSD-3-Clause |
| `torchsde` | 0.2.6 | Apache-2.0 |
| `transformers` | 5.19.0 | Apache-2.0 |
| `tokenizers` | 0.23.3 | Apache-2.0 |
| `safetensors` | 0.8.0 | Apache-2.0 |
| `numpy` | 2.5.3 | BSD-3-Clause AND 0BSD AND MIT AND Zlib AND CC0-1.0 |
| `Pillow` | 12.3.0 | MIT-CMU |
| `scipy` | 1.18.1 | BSD-3-Clause plus bundled dependency notices |
| `einops` | 0.8.2 | MIT |
| `aiohttp` | 3.14.4 | Apache-2.0 AND MIT |
| `yarl` | 1.25.1 | Apache-2.0 |
| `pyyaml` | 6.0.3 | MIT |
| `sentencepiece` | 0.2.2 | Apache-2.0 |
| `psutil` | 7.2.2 | BSD-3-Clause |
| `av` | 19.0.1 | BSD-3-Clause |
| `comfy-kitchen` | 0.2.37 | Apache-2.0 |
| `comfy-aimdo` | 0.5.6 | GPL-3.0; verified from installed wheel LICENSE |
| `blake3` | 1.0.11 | CC0-1.0 OR Apache-2.0 |
| `simpleeval` | 1.0.8 | MIT |
| `filelock` | 4.1.0 | MIT |
| `sqlalchemy` | 2.1.4 | MIT |
| `alembic` | 1.20.0 | MIT |
| `pydantic` | 2.14.0 | MIT |
| `pydantic-settings` | 2.15.0 | MIT |
| `kornia` | 0.8.3 | Apache-2.0 |
| `spandrel` | 0.4.2 | MIT |
| `PyOpenGL` | 3.1.10 | BSD |
| `comfy-angle` | 0.1.1 | BSD-3-Clause |

ComfyUI and comfy-aimdo use GPL-3.0; they run in the separate ComfyUI process.
The studio wheel does not bundle their binaries. The official template-derived
API graphs and upsampler prompts retain the included MIT notice. Model weights
are separately licensed, as recorded in [MODELS.md](MODELS.md).

## Retained experimental CharRef components

- Local `moss_image_charref_poc.safetensors` exactly matches
  [pleiades7/MOSS-Image-CharRef-PoC](https://huggingface.co/pleiades7/MOSS-Image-CharRef-PoC/tree/ac6de745a751a63a78be5ce10e911c3c695a042b):
  145,157,240 bytes, SHA-256
  `71e65ba732ae419b011020a51f8f89b73353fca7b0827d3d255a36f4def89d1c`.
  The publisher declares Apache-2.0.
- Local `moss_image_base_int8_convrot.safetensors` exactly matches
  [Comfy-Org/MOSS-Image](https://huggingface.co/Comfy-Org/MOSS-Image/tree/530a4c94f92c35ef6818b1b035a983fe9dcf5f54):
  5,413,698,958 bytes, SHA-256
  `f601c1e1161915fb3fea003da0c1782e374dd960fbb3978bc0e4e3fa1f2d8e6f`.
  The repository declares Apache-2.0.

These source/hash checks do not establish image quality or training-data rights.
CharRef remains experimental, outside the default FLUX 3 pack and new demo.
