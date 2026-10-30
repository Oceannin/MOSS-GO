# Recorded contest demonstration

[Watch the demo](https://oceannin.github.io/MOSS-GO/) or download
[the MP4](https://oceannin.github.io/MOSS-GO/demo.mp4).

The 1:48 English walkthrough uses real captures of the installed 0.1.0rc1
studio, with pauses edited and generation waiting explicitly shortened. It has
English captions and no music. The comparison wipe was operated through the
application's own keyboard-accessible slider.

The demo starts from the bundled original Mira reference, generates a railway
station scene with a paper ticket, then changes the messenger bag to teal through
a selected mask. Both jobs completed in the installed wheel against the local
ComfyUI runtime. No model weights or paid APIs were fetched for the recording.

- Engine: FLUX.2 Klein distilled 4B FP8, Qwen3 4B encoder and FLUX.2 VAE.
- Reference and final image: 768×1024; seed 42; four sampling steps.
- Machine: RTX 4070 Ti SUPER 16 GB, 32 GB system RAM, Windows.
- Edit: 8 px Gaussian feather radius, context crop and composite into the original.
  Pixels outside the resulting softened mask matched the source in this case.
- The two saved takes and their parent/version relationship survived page reload.
- The exported example ZIP includes source, mask, result, actual native graph,
  recipe manifest and contact sheet. It is attached to the release.

This is a bounded demonstration, not a general identity or hardware guarantee.
The broader development benchmark and limitations are in [BENCHMARK.md](BENCHMARK.md).
