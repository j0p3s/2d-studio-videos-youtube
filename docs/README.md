# Documentation

Updated 2026-11-13. These guides describe the current source; historical observations are
labelled separately. Generation success must be established by the actual job, not test counts.

| Guide | Use it for |
|---|---|
| [Studio README](../README.md) | Installation, providers, voice engines, Auto, updating and validation commands. |
| [Offline workflow](OFFLINE-WORKFLOW.md) | Ollama code-generated animation, scene audits, recovery and local model settings. |
| [CastWorkshop integration](CASTWORKSHOP.md) | Local Krea2/H3 clips in Studio Auto, D: setup, server/job recovery and current limits. |
| [Portable CastWorkshop](../integrations/castworkshop/README.md) | Optional manual packaging after the D: test; no automatic migration. |
| [Standalone test](../integrations/castworkshop/test-kit/TEST-README.md) | Launch-Test.cmd, the independent Krea2 → MOSS → H3 test and its logs. |
| [Current handoff](../HANDOFF.md) | Current implementation, verified results, unfinished work and user constraints. |
| [Historical handoff](HANDOFF-HISTORY.md) | Earlier sessions and measurements; not current instructions. |

## Which local animation path?

**Ollama animation** writes JavaScript scenes for the installed stick-figure kit. It uses
the rig, scene checker and kit renderer. **CastWorkshop animation** uses local ComfyUI
image/video models and assembles visual clips under Studio's selected narration. Its
model setup, GPU requirements and failure logs are separate from Ollama's scene checker.
Both work through Auto; neither publishes without the Publish action.

The standalone D: CastWorkshop test generates a MOSS voice reference and a talking-video
test. It is distinct from Studio's narration-backed montage integration. Telegram is not
required by either route; it is also optional in upstream CastWorkshop's browser UI.

## Model storage and GitHub

Keep the current installation on D: until testing is finished and migration is explicitly
requested. Download completion does not trigger a move. The optional importer copies and
verifies before any later user-directed removal of the original installation.

`.gitignore` excludes `models/` and `Models/` at any depth, common weight files and partial
safetensors/GGUF downloads. Runtime, cache, media and credential directories are also
excluded. No model weights were tracked at the latest source review. Gitignore does not
remove an already tracked file, so verify the index before publishing a new model location.

Do not commit models, credentials, virtual environments, third-party application trees,
logs or generated videos. The repository contains source, launchers, tests and documentation.
