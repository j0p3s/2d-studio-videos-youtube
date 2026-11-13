# Portable CastWorkshop

Updated 2026-11-13. [Documentation index](../../docs/README.md).

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
on C: rather than risking the only copy of a large download. Re-running import reuses identical verified files.
Do not change packages or project files during import. An existing different destination
is preserved and reported for review, never silently overwritten.

## Copying models by hand and retiring D:

Close the importer with Ctrl+C before copying. In File Explorer, copy the contents of
`D:\CastWorkshop-Test\ComfyUI\models` into this folder's `models\comfyui`, and the
contents of `D:\CastWorkshop-Test\CastWorkshop\models` into `models\castworkshop`.
Do not delete the originals. Run **Launch.cmd → 2** afterward: it verifies the copied
files and finishes both applications, Python runtimes and FFmpeg. Copying virtual
environments alone does not make them portable. The space check counts remaining
files rather than requiring room for a second copy of models already present.
Progress messages appear every 200 copied files and after each file of at least 1 GiB;
checksum validation of a large existing file can still take time.
The generated TTS Audio Suite `.inline_tag_settings_cache.json` and Python bytecode
caches are skipped during import and source comparison. TTS uses its built-in defaults
if this settings cache is absent. Permission errors on required files still stop import.

After import finishes, restart Studio so its installation path refreshes, run option 3,
and validate a real generation from the imported package. **Option 6** is an explicit
cleanup command: it verifies application, dependency and model contents against the
source, preserves test settings/logs/outputs under `source-backup`, runs runtime/model
checks, and then deletes only `D:\CastWorkshop-Test`. It refuses incomplete imports,
active processes, differing files or another source path. Download caches and temporary
files are disposable and are not archived. Source cleanup never runs automatically
when import or download finishes. Restart the menu after a launcher update.

Studio supports this layout directly. Import updates its saved CastWorkshop path when
it is empty or points to the old D: test folder. Ollama remains separate; check its
model location before formatting D:. Other unrelated D: files are outside this check.

```text
integrations/castworkshop/
  Launch.cmd             one menu for checks, import and launch
  portable.py             importer/launcher (no extra Python dependencies)
  test-kit/              maintained test launcher and pread ComfyUI bootstrap
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
  source-backup/         private test settings, logs, outputs and source metadata
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

The D: installation now passes its 31/31 model-asset check. CUDA PyTorch, ComfyUI requirements
and pinned custom nodes are installed, and a real local ComfyUI startup/node registration
check passed. No real models have been moved, no complete import has run,
and no complete GPU video generation or relocated full stack has been verified.

The latest standalone retry verified 31/31 downloaded assets and reused a successfully
rendered reference image. The following voice-stage server exit prompted polling/diagnostic
fixes; a complete talking-video and relocated-package acceptance remain separate checks.
Keep models on D: while testing. The repository ignores model folders
at every depth, common weight files and these runtime folders; weights are not published.

Advanced commands (from this folder):

```powershell
.\Launch.cmd check
.\Launch.cmd import --source 'D:\CastWorkshop-Test'
.\Launch.cmd health
.\Launch.cmd comfy
.\Launch.cmd retire-source
```
