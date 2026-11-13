# Portable CastWorkshop

Open **Launch.cmd** in this folder. Everything imported for this integration stays here;
the Studio root and its existing video projects are not reorganized.

For **Studio Auto**, use **Setup → Animation & character designs → CastWorkshop (local)**.
See [the Studio integration guide](../../docs/CASTWORKSHOP.md). This works with the D:
installation without importing it. `test-kit/` holds maintained sources for the standalone
`D:\CastWorkshop-Test\Launch-Test.cmd` test; it does not contain models or third-party code.

## Test on D: first; import only when you choose

The user wants to run the original D: test before any migration. Download completion
does not trigger import, copy or move. Nothing here watches the download or schedules
a migration. Keep testing on D: until the user explicitly chooses to proceed.

1. Finish downloads/dependency installation and run the original test on D: first.
   When you are ready to import, close CastWorkshop, ComfyUI and their installers/downloaders.
2. Open **Launch.cmd**, choose **1** to check the source, then **2** to import.
3. Import verifies the pinned model checksums, copies and verifies file contents, bundles
   separate Python runtimes with each application's installed dependencies, and copies
   FFmpeg/FFprobe. It refuses incomplete downloads and differing destination files.
4. Choose **3** for runtime smoke checks, then **4** to start ComfyUI. Run a real generation
   before removing the original D: installation. Option **5** starts CastWorkshop's configured
   services, including Telegram when configured; it is never started by import/check.

The import deliberately keeps the source installation intact. It uses additional space
on C: rather than risking the only copy of a large download. You can remove D: manually
after a successful real generation. Re-running import reuses identical verified files.
Do not change packages or project files during import. An existing different destination
is preserved and reported for review, never silently overwritten.

```text
integrations/castworkshop/
  Launch.cmd             one menu for checks, import and launch
  portable.py             importer/launcher (no extra Python dependencies)
  README.md
  apps/ComfyUI/           application and custom nodes
  apps/CastWorkshop/      application and private local configuration
  models/comfyui/         original model categories and filenames
  models/castworkshop/    CastWorkshop identity-segmentation model
  runtime/python-comfy/   isolated Python + ComfyUI packages
  runtime/python-cast/    isolated Python + CastWorkshop packages
  bin/                   FFmpeg and FFprobe
  cache/                 Hugging Face, Torch and pip caches
  tmp/                   integration temporary files
```

The two application `models` paths are Windows directory junctions pointing into this
folder's `models/` tree. Launch repairs these links after moving the whole package.
Keep the full folder together, on a writable Windows NTFS drive. Use **Launch.cmd**
rather than old D: virtual-environment shortcuts. Python and tools are resolved relative
to this folder; a working imported package does not need the original system Python.
Generated media stays in each application's own output folders.

## Scope and current readiness

This prepares a portable Windows application package, not a single executable containing
tens of gigabytes of model weights. Windows and a compatible NVIDIA driver remain machine
requirements. The importer does not download or install missing GPU packages or models.
All downloads in the source manifest must finish first, including project-owned models.

Ollama and its LLM weights are **not** in `ComfyUI/models` and are **not bundled** by this
importer. CastWorkshop operations that call Ollama still need the separately installed
local Ollama service and a configured model. Telegram needs user configuration and network
access. A completely offline, machine-independent CastWorkshop stack has not been certified.

The D: installation still has unfinished model downloads. CUDA PyTorch, ComfyUI requirements
and pinned custom nodes have since been installed, and a real local ComfyUI startup/node
registration check passed. No real models have been moved, no complete import has run,
and no GPU generation or relocated full stack has been verified.

Advanced commands (from this folder):

```powershell
.\Launch.cmd check
.\Launch.cmd import --source 'D:\CastWorkshop-Test'
.\Launch.cmd health
.\Launch.cmd comfy
```
