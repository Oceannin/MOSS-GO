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
in [ASSISTANT.md](ASSISTANT.md). The experimental CharRef adapter and the full GPU
runtime dependency audit remain release work. Model weights and runtime binaries
are not bundled in the studio wheel or source archive.
