# CastWorkshop in Studio Auto

Updated 2026-11-13. [Documentation index](README.md).

Studio supports **CastWorkshop (local)** as an animation provider. It uses the installed
CastWorkshop Krea2 and MiniMax H3 API workflow files directly through local ComfyUI.
Telegram, the CastWorkshop VPS/database and its conversation worker are not started.
Upstream also offers a browser interface; Telegram is optional there too.

## Test on D: first

1. Restart Studio after this update.
2. In **Setup**, select **CastWorkshop (local)** for **Animation & character designs**.
   Keep a text-capable provider, such as Ollama, under **Ideas & script**.
3. Set the CastWorkshop folder to `D:\CastWorkshop-Test` and the local ComfyUI address
   to `http://127.0.0.1:8190`. The folder contains both `CastWorkshop/` and `ComfyUI/`.
4. Use **Check CastWorkshop**. If dependencies are incomplete, use
   **Finish CastWorkshop setup** with offline mode off, or run `D:\CastWorkshop-Test\Launch-Test.cmd --setup-only`.
   Installation needs internet; subsequent generation uses local files and loopback HTTP.
   Setup waits for existing installers/downloaders rather than overwriting their partials.
   If the original download ran through IDLE, let it finish and close that IDLE window
   before setup proceeds to model download/resume.
5. On **Script**, choose **Shorts 15s test**, then press **Auto → Start fresh**. Auto reuses
   an existing completed project's video, so use a fresh project when testing a new provider.
6. Review the resulting video. Auto stops on Upload; only **Publish** uploads anything.

All models and Python environments stay in their current D: location. No automatic model
migration is scheduled. Do not move the installation until the original D: test is complete
and the user explicitly requests migration.

## What this integration renders

The selected text provider plans narration-matched image/action prompts. Krea2 generates
reference images; H3 generates **8-second** visual clips, one GPU job at a time. Studio
then cuts/blends them to the narration and validates the final audio/video streams and
duration. A roughly 15-second narration therefore normally requires two visual clips.
The exact recorded voice duration determines the final film length.

This is a narrated-video integration, not CastWorkshop's character conversation or
talking-head path. The existing Studio voiceover remains the soundtrack. H3's native audio
is discarded during assembly; optional audio-reference inputs are removed from its graph.
No new MOSS voice job is required. Upstream model/sampler settings are otherwise retained;
test-specific changes are prompts, references, seed, aspect, duration and output prefixes.
The H3 generation resolution remains its installed preset size; Studio's resolution setting
controls final export and can upscale that result. In Look notes, describe the desired
character, clothing, setting and style. The stick-figure engine's colour-grade dropdown
does not apply its renderer grade to generated CastWorkshop footage.

Supported audio is the selected narration plus an optional supplied music track. Burned-in
captions, generated mood music, authored SFX, CastWorkshop character selection, MOSS voice
auditions, two-character performance planning and continuation are not wired into Studio
Auto in this version. The log identifies these limitations instead of claiming they ran.

## Local service, recovery and files

- ComfyUI starts with `--lowvram`, `--disable-dynamic-vram`, a loopback bind and `--offline`.
  Dynamic VRAM is disabled so this ComfyUI version actually honors its low-VRAM mode.
  Python fault-handler diagnostics are enabled for native failures. The explicit port defaults
  to 8190. The adapter refuses a responding server whose command line does not identify
  the configured installation. If the standalone D: test's server is still running,
  close that idle server or use a different free port for Studio.
- The Windows launcher uses `comfy_bootstrap.py` to select safetensors' `pread` reader for
  PyTorch files before ComfyUI starts. This bypasses the mapped-reader path that crashed
  loading the H3 encoder, without changing ComfyUI's repository or model files. The encoder's
  complete SHA256 matched the pinned manifest, and an isolated `pread` load read all 2,054
  tensors successfully. Full H3 generation remains a separate acceptance check. See the
  [upstream mapped-loader report](https://github.com/Comfy-Org/ComfyUI/issues/15424).
- The upstream GPU lock and queue checks prevent overlapping submissions. Text-model
  generation completes and the selected Ollama model unloads before GPU media generation.
- Stop ends Studio's waiting. A job already accepted by ComfyUI may continue. Its saved
  prompt ID is polled on resume; a timeout or ambiguous POST is never blindly resubmitted.
  Inspect queue/history and the saved state before clearing an unresolved submission.
- ComfyUI's `/free` can return an empty HTTP success response. Both the Studio adapter
  and standalone launcher accept this. An older launcher could finish a reference image,
  save it successfully and then stop with a JSON decode error during memory release.
  Update both copies and resume: the completed image is reused, not generated again.
- If an owned server exits, polling stops and records its exit code while preserving the
  accepted job ID. Repeated connection failures also stop instead of silently waiting for
  hours. Do not clear an ambiguous submission. A confirmed stopped server with no matching
  output can be reviewed and its failed stage state archived before a deliberate retry.
- Runtime errors, missing workflow nodes or incomplete required models stop generation.
  A successful offline test does not prove H3's quantized models run on a particular GPU.
- Generated frames/clips, plan and job states live in `work/<project>/castworkshop/`.
  Server logs live in `work/<project>/castworkshop-server/server.log`; ComfyUI also retains
  its original media. Existing completed media is reused for unchanged inputs. Changing
  voice, narration, look, aspect, root or workflow files requires a fresh project rather
  than silently deleting the existing jobs. Final output is in `work/<project>/out/`.
- Readiness uses the upstream filename/size convention, not full model hashing. The manual
  portable-copy tool separately verifies model hashes when it is explicitly invoked.

Messages about missing optional `audio_separator`, Triton, torch-npu or OpenGL acceleration
do not by themselves identify the failed stage. Check the saved stage history and final
exception before adding packages. `pip check` passing confirms dependency metadata, not
that every model can render successfully on the GPU.

## Standalone launcher and portable packaging

The independent D: launcher runs Krea2 → MOSS → a target 15-second talking-video test.
It is a different test from Studio's narrated montage path. Maintained launcher sources
are under `integrations/castworkshop/test-kit/`; copy these files into the existing test
root to provision another installation. They do not include third-party code or weights.

Manual portable packaging is documented in
[`integrations/castworkshop/README.md`](../integrations/castworkshop/README.md).
It preserves D:, never runs automatically, and has not yet been validated by a complete
real import. It bundles Python/dependencies and ComfyUI models when invoked; it does not
bundle the separately installed Ollama service/LLM weights or the NVIDIA driver.

## Documentation used and validation limits

Implementation follows upstream
[Getting started](https://github.com/kenfox0115/CastWorkshop/blob/main/docs/GETTING_STARTED.md),
[model setup](https://github.com/kenfox0115/CastWorkshop/blob/main/docs/MODELS.md),
[image defaults](https://github.com/kenfox0115/CastWorkshop/blob/main/docs/IMAGE_DEFAULTS.md)
and [performance planning](https://github.com/kenfox0115/CastWorkshop/blob/main/docs/PERFORMANCE_PLANNER.md).
The installed checkout is `24a9462`; the four setup/model/performance/voice documents were
checked against the GitHub main directory blob hashes on 2026-11-13.

Observed: CUDA PyTorch 2.14.1 detects the RTX 3080 Laptop GPU; ComfyUI requirements and
all four pinned custom-node packages install;
adapter/copy/launcher regression tests pass; Studio's isolated GUI starts without a Python
exception. Desktop screenshot capture timed out, so no visual-layout approval is claimed.
The real local ComfyUI startup/API check passed on the RTX 3080; every required image/video
node and both MOSS test nodes registered successfully. The smoke-test server was then stopped.
The latest D: readiness check verified **31/31 assets**, working CUDA and no broken pip
requirements. Its reference image rendered in 68.42 seconds, then exposed the empty `/free`
response bug. After that fix, a retry reused the image and reached MOSS voice generation.
The server stopped during that attempt without a Python traceback; its cause is not yet
confirmed. Server-exit detection, bounded connection recovery and fault-handler logging
are now enabled. The confirmed stopped voice job had no output and was archived under
`D:\CastWorkshop-Test\logs\update-backups/` before preparing a deliberate retry.
The next run completed MOSS voice generation in 29.78 seconds, then H3 exited with
`0xC0000005` while loading the text encoder through the mapped safetensors path. The new
non-mapped loader passed the isolated full-encoder load. Completed image and voice media
are preserved. A complete video, Studio Auto GPU run and relocated portable stack remain
unverified. No models moved.
