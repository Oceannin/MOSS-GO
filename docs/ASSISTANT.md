# Optional local prompt assistant

The image workflows do not require Ollama. For the optional assistant, install
[Ollama](https://ollama.com/download) and pull the tested model:

```sh
ollama pull qwen3:4b-instruct-2507-q4_K_M
```

The model name and full manifest hash are in
`moss_go/assets/assistant_model.json`. A different revision is reported as not
ready. This avoids relying on a mutable short alias. The model's
[official card](https://ollama.com/library/qwen3:4b-instruct-2507-q4_K_M)
identifies the Q4_K_M Instruct model and Apache-2.0 license. Weights are not bundled.

The development check used Ollama 0.40.13. Its official Windows standalone archive
was verified against the GitHub release SHA-256, and its executable had a valid
Ollama Inc. Authenticode signature. Only CPU runtime libraries were extracted into
the ignored local tools directory. No startup service or global PATH change was
made. The test server used loopback binding, a separate model directory,
`CUDA_VISIBLE_DEVICES=-1` and `OLLAMA_NO_CLOUD=1`. See the official
[CPU selection guidance](https://docs.ollama.com/gpu) and
[local-only configuration](https://docs.ollama.com/faq#how-do-i-disable-ollamas-cloud-features).

Requests also set `num_gpu: 0` and `keep_alive: 0`. The returned structured prompt
is checked before the UI offers it. Quoted visible text, digits and supplied
canonical character traits cannot silently disappear. Character traits stay in
application state and are not sent to the editing model. They are attached by the
image-request builder; traits already stated in the scene are not added again.
The review exposes those held traits separately from the editable scene.
Truncated responses and
newly invented quoted captions are rejected. These checks do not establish full
semantic equivalence; the user still reviews and accepts the suggestion.

## Development evidence

Seven predefined briefs covered minimal composition, digit counts, Russian visible
text, Russian-to-English translation, canonical Nia traits, exclusions and an
instruction-like phrase used as a literal caption. Assistant text review, not an
independent human study, initially required at least six usable results.

The first round yielded only 2/7 usable outputs under a no-manual-repair criterion:
several prompts had outer quotation wrappers, one remained in Russian, and one
invented a Lighthouse caption. All failures were retained. The structured-output
follow-up repeated all seven briefs, including the earlier successes.

The first follow-up yielded six usable suggestions and one protected rejection:
the Nia case omitted an exact canonical trait, so the original was retained.
The accepted outputs retained the requested counts, literal captions, exclusions
and composition; the Russian brief was translated. Clear minimal English briefs
were left unchanged rather than decorated with unnecessary additions.

A third round tested keeping traits separate while still supplying them as model
context. The model injected that context into the scene and repeated the pilot
role; that character result was rejected in review. The final boundary sends only
the scene to the editor, preserves the full character dictionary outside it, and
compiles the generation-facing prompt in code. All seven original cases were
repeated again and passed text review. In the Nia case all nine canonical traits
occur exactly once in the compiled prompt, including the role already stated in
the scene. A workflow test also checks the actual positive-conditioning text,
rather than only the assistant response.

These rounds used the same fixed briefs and model revision; all prior outputs are
retained. This remains seven-case assistant review, not broad proof of semantic
equivalence or visual identity across generated images. The final round is in
`.local/qa/assistant-real-v4.json`; the failed context-injection attempt is v3.

Both real rounds sampled Ollama's loaded-model API during inference and observed
zero VRAM allocation. The model was unloaded after the requests. First-round times
were 4.6–11.3 seconds on this development computer; these are not cross-device
performance guarantees. Complete local evidence is in
`.local/qa/assistant-real.json` and `.local/qa/assistant-real-v2.json`.

Live browser checks used real CPU suggestions. Closing retained the Russian
original; the improved translation view separated removed and added paragraphs;
Apply explicitly replaced the workspace text. No image jobs were created. Browser
storage and image history remained separate from the assistant response.
