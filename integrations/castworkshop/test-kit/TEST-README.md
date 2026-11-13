# Local 15-second CastWorkshop test

Double-click **Launch-Test.cmd**. It installs missing CUDA PyTorch, ComfyUI requirements
and the pinned CastWorkshop nodes/models, then runs reference image → MOSS voice →
approximately 15-second H3 video. First setup may download many gigabytes.

- No Telegram account, bot token, Ollama or publishing is used by this isolated test.
- Models remain in `D:\CastWorkshop-Test\ComfyUI\models`. Nothing is migrated to Studio.
- Existing pip installers and the original `download_models.py` process are allowed to
  finish first. The launcher does not kill them or write to their partial downloads.
- Test ComfyUI runs locally on port **8190**, using `--lowvram` for the 16 GB GPU.
  Other workflows' model and sampler settings are preserved. This test explicitly changes
  duration to 15 seconds, image aspect to widescreen, prompts, seed and output prefixes.
- A 15-second video is a test target, not a runtime estimate. The H3 frame lattice can make
  the result slightly longer. Model/GPU compatibility is established only by actual rendering.
- Edit **test_settings.json** to change the presenter, dialogue and video action. Keep the
  dialogue and quoted text in the video prompt consistent.
- Output is saved in **test-output\<settings hash>\final.mp4** (or the container returned
  by ComfyUI). Individual reference/voice files, submitted workflows and job histories are
  saved beside it. Logs are in **logs\**.
- Rerunning with identical settings reuses completed stages and polls saved job IDs.
  An ambiguous submission is stopped for inspection rather than automatically duplicated.
  Ctrl+C stops the launcher; a GPU job already accepted may continue on the local server.
  Do not clear state or resubmit until its queue/history is resolved.
- Final checks require FFprobe to find audio, video and approximately the requested duration.
  They do not certify acting, visual quality or lip synchronization.

Optional commands from this folder:

```powershell
.\Launch-Test.cmd --check        # readiness only; no installs or GPU job
.\Launch-Test.cmd --setup-only   # finish installation, do not render
.\Launch-Test.cmd --skip-setup   # render/resume with already-installed dependencies
```

The standalone launcher lives alongside the two repositories and does not edit their
application code or start CastWorkshop's Telegram/VPS stack. Test it on D: before any
later portable migration. Dependencies and models must finish before a full test can pass.
