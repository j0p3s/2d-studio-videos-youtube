# Offline animation workflow

This guide describes the automatic Ollama path and scene checker. The agent-based Claude,
Codex/Gemini workflows and OpenArt shot generation are separate adapters.

## Setup and updating

1. Install the studio and third-party animation kit using the root installer. The kit is
   supplied separately, not published in this repository.
2. Install Ollama in Setup and download a local model while online. Select installed models
   independently for script and animation. The tested animation model on the development
   laptop was `gpt-oss-20b-studio64k:latest`; it is not a requirement for other installations.
3. Install a Piper voice or optional Qwen3-TTS model and the alignment dependencies/model.
   These need downloads once. Edge voices, connected providers and YouTube upload need
   internet. Offline mode keeps an explicitly selected Qwen3 engine, or replaces Edge with Piper.
4. Close the GUI before applying updates. Update the entire `app` directory and root launchers;
   the pipeline depends on several Python/JavaScript modules. For a clean checkout,
   `git pull --ff-only` updates tracked files; preserve local changes first.
5. From the root, run `.\.venv\Scripts\python.exe app\patch_kit.py growkaz-stickman-studio`
   after a kit update, then reopen the GUI. The kit patcher checks full Chromium and can
   fall back to installed Chrome/Edge. A separate Playwright headless-shell package is not assumed.

Automatic offline animation does not need a Claude login or CLI agent. Optional interactive
or tool-based character-design operations still use the existing CLI bridge. Models other
than GPT-OSS need reliable JSON output and JavaScript generation; tool calling is unnecessary
for the automatic path. Not every model/backend implements named reasoning controls.

## What happens during generation

1. The app creates the project, copies narration/script, aligns English words with Whisper,
   and builds timed beats.
2. Ollama plans the whole storyboard together. Validation requires exact shot IDs/order,
   concrete locations/actions, different start/end states, varied framing and limited action repetition.
3. One bounded scene-code request is made per shot. Prompts specify consistent character
   design, layered locations, grounded props and actual anticipation/action/settle phases.
4. Node checks syntax before source is accepted. If misplaced whitespace escapes caused
   invalid JavaScript, the app tries a local correction that preserves literal escapes and
   Unicode, then reruns Node. Failed code gets up to three model attempts with its latest source/error.
5. Contact sheets expose missing modules/runtime failures. Bounded repairs target shot IDs;
   unrelated browser/setup errors stop instead of asking the model to reinstall dependencies.
6. The scene checker draws every output frame and captures up to eight moments per shot.
   It checks runtime errors, missing modules, nearly uniform action areas and residual motion
   after translation/zoom alignment. Captions are excluded from its action-area measurements.
   Audit-only engine instrumentation also validates finite joint arrays, anatomical segment
   lengths against the shipped pose library, shared preset mutation, invalid Canvas coordinates
   and distant circles joined into accidental filled polygons. Findings include frame/time.
   Runtime and geometry failures block export even in audit-only mode with `--export`.
   Normal engine files are not modified by this instrumentation.
7. Flagged generated scenes get a targeted local repair attempt with backup, syntax check and
   another browser audit. A replacement must clear all warnings and motion/detail thresholds.
   A repair cannot remove a previously present rig character just to eliminate its errors.
   Rejected changes are rolled back. Unresolved generated-scene flags stop export for review.
8. The installed renderer/mixer produce `out/final.mp4`. Stream and duration checks require
   audio and video; an arbitrary model-created substitute MP4 is not accepted as the final result.

The checker is a diagnostic aid, not an aesthetic judge. Global-motion alignment reduces
camera-only false passes but cannot guarantee real acting or correct physical contact.
Narrative relevance and visual quality still require human review. Reports retain
`visually_approved: false`; do not interpret a successful runtime check as visual approval.
The HTML report expands previews by default and labels clear scenes **Visual review required**.
Rig geometry checks apply to the existing `drawFigure` rig; arbitrary custom drawing and
semantic prop contact are not fully assessed. Suspected defects can require human correction
when the local model's single repair attempt does not clear all checks.

## Visual direction and approved scenes

The user-approved reference has consistent teal-hoodie characters, navy interiors, amber
key/rim light, grounded desk/prop actions, timer inserts, close-ups and explanatory diagrams.
Actions should follow the narration rather than repeat random drinking, reaching or idle poses.
That reference was manually directed. A full new automatic generation matching its quality
has not been established as a general guarantee.

Completed scene prompt/source hashes are recorded in `build/local_animation.json`.
Unchanged completed code is reused after a stop. Input changes rebuild timing/plan, and
visual changes invalidate generated scenes. Approved/manual entries are never auto-rewritten
by quality heuristics. Their saved `visual_settings` guard aspect ratio, style and look notes:
changing those stops reuse while preserving the previous config/source. Use a new project
for a changed direction, or review and reframe approved scenes before reapproval.

## Checker commands for existing projects

Run from the root folder with the GUI closed or idle; do not run concurrent writers against
the same project. The default Windows launcher checks and attempts repairs for all recorded
offline projects:

```powershell
.\Check-Offline-Animations.cmd
```

Direct commands allow audit-only mode and explicit export:

```powershell
.\.venv\Scripts\python.exe app\check_offline_scenes.py --all
.\.venv\Scripts\python.exe app\check_offline_scenes.py --all --repair
.\.venv\Scripts\python.exe app\check_offline_scenes.py --project projects/my-video --repair --export
```

- `--all` selects projects with `build/local_animation.json`; underscore-prefixed test
  projects are excluded. Legacy projects without this checkpoint are not inferred to be offline.
- `--repair` requests local-model replacements for flagged non-manual scenes. Without it,
  the tool audits only. Runtime/missing-module failures still report failure.
- `--export` rerenders/remixes the final video explicitly. Repairs alone update scene source,
  not an already exported MP4. Keep an additional MP4 copy if you need earlier exports.
- `--model NAME` overrides the recorded model. Otherwise the project's performance report
  model is used, falling back to the adapter/environment default.
- `--studio PATH` selects another installed kit. Explicit projects must be directly inside
  that studio's `projects` folder.
- `--report-dir PATH` selects the combined HTML dashboard folder for direct Python runs.
  By default it is `reports/offline-animations` beside the studio. The Windows launcher
  always uses that folder beside its own root and asks whether to open `.index.html`.

The HTML dashboard is rebuilt on every launcher/CLI run, including failures and cancellations.
Both `.index.html` and `index.html` contain the same report. It summarizes projects/scenes,
warnings, runtime failures and repair decisions, and copies allowed scene preview images
under `assets` so the HTML can be viewed locally without network assets. Earlier successful
audit JSON is not presented as the result of a failed new check. The launcher also replaces
the old entry pages with an explanatory fallback before starting Python. Opening an HTML
file alone shows the latest snapshot; rerun the launcher to perform new checks/rebuild it.
Generated root `reports/` content is private runtime output and is gitignored.

## Files and diagnostics

| File/folder | Meaning |
|---|---|
| `build/local_animation.json` | Input identity, scene hashes, storyboard and visual-settings checkpoint. |
| `build/ollama_performance.json` | Request token/duration metrics, elapsed time, output, status, stage and failure/cancellation. Covers setup through export. |
| `build/scene_audit/report.json` | Per-shot frame counts, sampled times/images, raw/residual motion, color spread, warnings and repair decisions. |
| `build/scene_audit/backups/` | Source backups before proposed repairs. |
| `build/scene_audit/*.png` | Up to eight snapshots per shot; runtime checks also cover frames between snapshots. |
| `build/sheets/`, `build/stills/` | Renderer contact sheets and other requested stills. |
| `out/final.mp4` | App-owned final export. |
| `reports/offline-animations/.index.html` (root) | Rebuilt combined HTML dashboard; `index.html` is an identical entry point. |
| `studio.log`, `gui_error.log` | Current session operations and GUI errors; the session log resets at launch. |

On failure, inspect the reported stage and last error. A failed setup/alignment/plan now
has a performance report; a failed plan preserves the previous checkpoint. Reporting errors
do not replace the original failure. Stop is checked while waiting for Ollama connection
headers/tokens and aborts the active socket; queued output is bounded. Stop does not imply
remote services outside Ollama (for example an already submitted OpenArt job) were cancelled.

`prediction aborted, token repeat limit reached` means the local model entered a repetition
loop, not that offline credits or a usage allowance ran out. Studio discards the aborted
answer and retries locally within a three-attempt budget, changing the sampling seed and
repetition settings; GPT-OSS recovery uses low reasoning. Animation logs show recovery
attempts. Stop remains responsive. If recovery fails, no partial answer is accepted and
the error explains the local loop. Restart Studio after updating Python code, then press
Auto again to resume the saved project. Recovery cannot guarantee that a model will finish.

## Model and memory configuration

Studio `.env` overrides:

```dotenv
OLLAMA_THINKING=low
OLLAMA_ANIMATION_THINKING=medium
OLLAMA_REPAIR_THINKING=medium
OLLAMA_SCENE_CONTEXT=16384
```

Named reasoning is sent to GPT-OSS models. Script/text defaults to low; storyboard and
animation/repair default to medium. Automatic requests set context directly, even when the
selected model name contains `studio64k`. Model loading is retained between requests, then
the studio releases its selected script model before Qwen/alignment and animation model before
rendering so those stages have GPU memory available.

Optional **Ollama server** settings for a memory-limited GPU are `OLLAMA_FLASH_ATTENTION=1`,
`OLLAMA_KV_CACHE_TYPE=q8_0`, and `OLLAMA_NUM_PARALLEL=1`. Quit/reopen Ollama after setting them.
They are server-wide; adding them only to the studio `.env` does not reconfigure an existing
server. Support varies by model/backend and quantization may affect output. Measure a
successful full run before claiming a speedup. Inspect `ollama ps` during the actual animation
request to determine GPU residency; an idle/base-model reading does not prove 64K residency.

No fixed whole-video generation time is promised. A measured scene request or a render of
existing code does not establish the duration of planning, retries, voice, alignment and export.

## Voice dependency warnings

SoX and Python `flash-attn` warnings come from Qwen/Python voice dependencies, not the
Ollama animation model. The observed `flash-attn` warning originated in an imported 25Hz
tokenizer module, while this studio configures the 12Hz Qwen voice model. That warning alone
does not establish the active model's attention implementation, CPU fallback or failure.
Inspect device/completion messages and actual error status. Python `flash-attn` is a separate
package from Ollama Flash Attention; installing it does not accelerate Ollama requests.

## Verification

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s app -p "test_*.py"
node --test app\video_encoder.test.mjs app\offline_motion.test.mjs app\offline_geometry.test.mjs
git diff --check
```

Latest verified results: 122 Python tests and 13 Node tests pass. Stalled-header/token tests
verify cancellation under 1.5 seconds in the local test server. A synthetic frame-11 error
outside snapshot times was detected by the full-frame audit. A real approved-video audit
checked 1,624 frames and 120 snapshots without runtime failures or visual flags. These are
specific test results, not proof that every model or new video will succeed.
