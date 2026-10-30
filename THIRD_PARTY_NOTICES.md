# Third-party notices

- **Mira, Theo and Nia reference images** are original fictional characters
  created for this project with MOSS-Image SFT. They are bundled project assets
  under the project license; they are not downloaded third-party character art.
- External Python runtime dependencies are pinned in `requirements.lock`.
  Their license declarations are recorded in [docs/DEPENDENCIES.md](docs/DEPENDENCIES.md).
  Installed wheels retain their own license files; the studio wheel does not
  repackage these dependencies under its own license.

- **Inter**, Rasmus Andersson: SIL Open Font License, bundled in
  `moss_go/web/fonts/OFL.txt`.
- **Reference attention design**, Ostris: MIT notice preserved in
  `moss_go/nodes/THIRD_PARTY_OSTRIS_LICENSE.txt`.
- The reference-loading and adapter modules are reused from the user's MOSS Image
  Studio implementation, with the original attribution retained.
- **MOSS-Image SFT**, OpenMOSS-Team, Apache-2.0. The tested single-file INT8/W4A8
  conversion is by Epyan, an independent community repackager. Exact source commits,
  file sizes and SHA-256 values are in `moss_go/assets/model_manifest.json`.
  See the [conversion's attribution and license](https://huggingface.co/Epyan/MOSS-Image-SFT-ComfyUI/blob/8b31b8214b29861078be74964656ccd944f99e66/README.md).
- **FLUX.2 Klein 4B FP8**, Black Forest Labs, Apache-2.0. Its Qwen3 text encoder
  is from the Comfy-Org Klein 4B package. The separate FLUX.2 VAE is also released
  under Apache-2.0 by the [publisher](https://bfl.ai/blog/flux-2); the manifest's
  `Comfy-Org/flux2-dev` URL selects only that VAE. It selects no dev diffusion model.
- **Qwen3 4B Instruct 2507**, Qwen Team, Apache-2.0, is an optional external prompt
  assistant. Its tested Ollama manifest digest is in
  `moss_go/assets/assistant_model.json`; see [assistant setup](docs/ASSISTANT.md).
- **MOSS CharRef** is experimental. Its additional adapter is not included in the
  verified default model packs; its source/weight audit remains a release gate.
  No model weights are included in this repository or covered by its code license.
- **ComfyUI** is an external runtime, not bundled or relicensed by this application.
- This is an independent project. The theme references Comfy's published palette;
  MOSS GO is not an official Comfy product.
