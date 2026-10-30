# Install and verify MOSS GO

This is the 0.1.0-rc.1 contest preview. Both wheel and source installation have been tested
in fresh Windows Python 3.12 environments without Torch or ComfyUI. A full
new ComfyUI GPU environment remains unverified. The installed-wheel CPU matrix
passed on GitHub for Windows/Ubuntu and Python 3.11/3.13. See
[release limits](RELEASE_NOTES.md). The studio can run without a GPU
runtime; image generation requires a separately configured ComfyUI.

## Studio from source

Use Python 3.11 or newer. Run these commands from the checkout. The dedicated
environment keeps the studio dependencies separate from ComfyUI and your other apps.

Windows PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install --require-hashes --only-binary=:all: -r requirements.lock -r build-requirements.lock
.\.venv\Scripts\python.exe -m pip install --no-deps --no-build-isolation .
.\.venv\Scripts\moss-go.exe
```

Linux studio commands exercised by the CI matrix:

```sh
python3 -m venv .venv
.venv/bin/python -m pip install --require-hashes --only-binary=:all: -r requirements.lock -r build-requirements.lock
.venv/bin/python -m pip install --no-deps --no-build-isolation .
.venv/bin/moss-go
```

Open `http://127.0.0.1:8191/moss-go/`. English is the first-launch language.
An explicit Russian/English choice is saved in the browser. **Try an original
example** works before the GPU runtime is connected; loading one prepares your
workspace without generation. Start ComfyUI, open Models & connection and choose
Check again when you are ready to generate.

`moss-go --comfy http://127.0.0.1:8188 --port 8191 --data /path/to/catalog` selects
the runtime, studio port and catalog. Omit `--data` to retain the default local
catalog. The service binds to loopback. Optional assistant setup is separate in
[ASSISTANT.md](ASSISTANT.md); it is not required for images or reference selection.

## ComfyUI, nodes and model files

ComfyUI runs in its own environment. Install this source checkout as
`ComfyUI/custom_nodes/moss-go`; its root `__init__.py` is the node-pack entry point.
The standalone studio wheel is not a substitute for that custom-node directory.
The pack uses `MossGo*` node names and preserves the personal MOSS Image Studio.

MOSS uses the pinned OpenMOSS plugin loader family. Follow
[MODELS.md](MODELS.md) for exact tested runtime/plugin revisions, model sources,
SHA-256 values, hardware limitations and the download command. The manifest tool
will not overwrite different existing files. It does not install GPU drivers or
update a personal ComfyUI installation.

## Verify a built package

`requirements.lock` exports every runtime dependency and distribution hash from
`uv.lock`. `build-requirements.lock` pins the build backend separately. Node and
Prettier are contributor tools; users do not need Node to run the studio.

With the tested uv 0.12.22:

```sh
uv lock --check
uv build --build-constraint build-requirements.lock --require-hashes --out-dir .local/dist
python scripts/check_archives.py .local/dist
python scripts/check_install.py --wheel-dir .local/dist --work-dir .local/installed-check
python scripts/check_install.py --source --work-dir .local/source-check
```

Use a new, empty `--work-dir`. The verifier keeps it for inspection and never
overwrites an existing environment. It creates a fresh venv, installs dependencies
with hashes, installs only the local wheel, copies tests away from the checkout
and runs them with Python's isolated mode. The HTTP smoke checks every packaged
web asset and relative JavaScript import, fonts/licenses/model manifests, original
example image hashes, preparation without jobs, English HTML and offline runtime
handling. Both installed console commands are exercised. No weights are downloaded
and no model generation runs in these package checks.

The archive check also verifies every source package module/asset is included and
rejects catalogs, model weights, caches, local QA data and the internal development
ledger. A normal `uv build` builds the wheel from the source distribution, so this
tests the packaging path rather than only an editable checkout.

The GitHub workflow uses the same installed-wheel checks on Windows/Linux with
Python 3.11/3.13, plus JavaScript tests, syntax and formatting. The official actions
are pinned to immutable commits. The first successful hosted run is
[Core checks](https://github.com/Oceannin/MOSS-GO/actions/runs/41044203888).
These CPU checks do not establish GPU-runtime compatibility.
