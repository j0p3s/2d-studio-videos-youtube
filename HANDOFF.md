# Handoff — 2D Animation Studio

Updated 2026-11-13. This file describes current behavior. Older release/session notes are
archived in [HANDOFF-HISTORY.md](docs/HANDOFF-HISTORY.md) and are not current instructions.

## Project and publication

- Checkout: `C:\Users\Joao\Desktop\2D-Animation-Studio-Setup`.
- Repository: https://github.com/j0p3s/2d-studio-videos-youtube, branch `main`.
  Published implementation `18def2f`; model-ignore update `cc6882e`; skeletal rig `5b7f753`. Use Git refs for the
  current tip. Direct source/documentation updates to `main` are authorized; no PR merge
  is necessary for a direct push. Source updates do not publish generated videos.
- `.gitignore` excludes `models/` and `Models/` at every depth, common weight extensions,
  partial safetensors/GGUF downloads, portable runtimes, caches, logs and media. No model
  folders or weights were tracked at the latest index check. Never print keys/tokens or
  commit credentials, private settings, third-party application trees or model weights.
- The user has now authorized portable migration and eventual deletion of
  `D:\CastWorkshop-Test`, because they plan to format D:. Import/manual copying is in
  progress, not complete. Never infer that the destination is ready from copied models
  alone. Preserve the source until import and validation succeed; deletion is an explicit
  option, never triggered automatically by download/import completion.

## CastWorkshop integration and current test

- Portable migration update (2026-11-13): local import was interrupted/incomplete;
  no `integrations/castworkshop/runtime/ready.json` was present at the latest check.
  No source deletion has been performed. Launch.cmd avoids incomplete bundled Python
  until the ready marker exists. Manual model copies are supported; import estimates
  remaining copy space and prints progress. Explicit menu option 6 verifies retained
  application/dependency/model files, archives test outputs/settings under ignored
  `source-backup/`, checks runtimes and then deletes only the real D: test folder.
  Run a real generation from C: before choosing cleanup or formatting D:.
  Import updates an empty/old-D: Studio installation setting; restart Studio afterward.
- Latest import stopped after 28,000 verified copies on an unreadable generated cache:
  `ComfyUI/custom_nodes/tts_audio_suite/utils/audio/.inline_tag_settings_cache.json`.
  The importer now skips precisely this upstream disposable cache and `__pycache__`
  during space estimates, copy and source comparison. Upstream uses built-in defaults
  when the cache is absent. Required-file permission errors still stop the import.
  The source files were not deleted or permissions changed. Reopen Launch.cmd and
  choose option 2; identical verified destination files are reused.
- Manual copying: put the contents of D: `ComfyUI/models` in integration
  `models/comfyui`, and D: `CastWorkshop/models` in `models/castworkshop`. Close the
  importer first; do not run simultaneous copies. Option 2 still finishes code,
  dependencies, isolated Python runtimes and FFmpeg/FFprobe. The last user-reported
  remaining-space estimate was 3.91 GiB plus a 2 GiB reserve, not a completion marker.
  Progress prints every 200 copied files and after individual files of at least 1 GiB.
- Before source removal: complete option 2, run option 3, restart Studio, validate a
  real generation using the imported C: installation, then close Studio/ComfyUI and
  use option 6. It archives test settings/logs/media and source-control metadata in
  ignored `source-backup/`; download caches/temp data are disposable. Its destructive
  path has not been exercised against the real source. No claim that D: is safe to
  format; unrelated D: data is outside this migration check. Ollama's default model
  folder was observed on C: with no OLLAMA_MODELS override; its API was not responding.

- Studio offers **CastWorkshop (local)** as an animation-only provider, with editable
  installation root/local URL and check/setup actions. Use `D:\CastWorkshop-Test` and
  loopback port 8190 for the current installation. Restart Studio after Python updates.
  For Auto choose **Shorts 15s test**, then **Start fresh**; otherwise Auto may reuse an
  existing completed video. The script target is about 30-35 words; audio controls duration.
- Studio uses installed Krea2 reference-image and H3 ref-to-video graphs, sequentially,
  as 8-second visual clips under the selected Studio narration. It removes optional H3
  voice-reference inputs and discards generated native audio when assembling the film.
  Telegram, the VPS/database, conversation worker and MOSS auditions are not invoked.
  Captions, generated mood music and authored SFX are not implemented for this route.
  Optional supplied music is supported. See `docs/CASTWORKSHOP.md` for all limitations.
- The standalone `D:\CastWorkshop-Test\Launch-Test.cmd` instead runs a Krea -> MOSS ->
  target-15s talking-video test. Its maintained sources are in
  `integrations/castworkshop/test-kit/`. Its stages and results are separate from Studio Auto.
- CUDA torch 2.14.1+cu130, torchvision/torchaudio, ComfyUI requirements and all four pinned
  node packages are installed. Torch detects RTX 3080 Laptop GPU. Real ComfyUI startup/API
  checks passed; required image/video and MOSS nodes registered. `pip check` passed.
- The latest test confirms **31/31 model assets present**. Its Krea reference image completed
  in 68.42 seconds. It then exposed a launcher/adapter bug: `/free` returns an empty success
  body, which was incorrectly parsed as JSON. Both copies now accept empty success bodies;
  regression tests cover the response. The corrected retry reused the image and reached
  MOSS voice generation, but the server then stopped without a Python traceback; cause
  remains unconfirmed. Polling now detects owned-server exits and bounded connection
  failures, preserves job IDs and enables Python fault-handler logging. Both launchers
  disable dynamic VRAM so `--lowvram` is effective. A new render must verify this policy.
  Confirmed no server/no voice output before archiving the failed voice state under
  D: `logs/update-backups/`; reference media and models are preserved. The user was told
  they can deliberately retry with `Launch-Test.cmd --skip-setup`. Do not auto-submit
  another concurrent test. Do not claim a complete video until actual final validation.
- Completed media and saved job IDs survive launcher restarts; ComfyUI history itself
  may be lost on server restart. The standalone launcher checks both history and queue,
  then rechecks history after three missing observations. With an idle queue it backs up
  the old state as `*-state-lost-*.json` and submits at most one replacement per stage
  invocation. Busy queues, unreachable servers and uncertain submissions do not trigger
  replacements. This recovery is covered by three offline regression tests.
  Ambiguous submissions are not blindly resubmitted; queues and upstream GPU locks are checked. Stop can leave an accepted job
  running. Changed generation inputs require a fresh Studio project to preserve jobs.
- Follow-up log: MOSS voice succeeded (29.78s); H3 server exited with 0xC0000005 in
  safetensors/PyTorch mapped encoder loading. The full encoder SHA256 matches the pinned
  manifest. Added source/test-folder `comfy_bootstrap.py` to select the installed `pread`
  backend without editing ComfyUI. Isolated loading of all 2,054 encoder tensors passed.
  Full video generation is still unverified. Preserve completed reference.png and voice.flac.
- Bootstrap initialization was also corrected to avoid importing torch before ComfyUI
  configures the CUDA allocator. A subsequent real H3 job loaded the text encoder and
  both VAEs and reached 0/20 sampling. The user stopped/restarted an earlier run; a later
  replacement job `c17d4f37-1a47-43e5-bd48-9225545f40df` was observed active at 0/20.
  No final MP4 or measured total render time has been verified. Do not restart generation
  merely to update documentation or finish file import.
- Upstream checkout `24a9462` and the linked setup/model/performance/voice documentation
  informed this adapter. No third-party code or weights are bundled in the source commit.
  Studio GUI initialized with isolated settings; screenshot capture timed out, so no visual
  layout approval is claimed. Ollama service/LLM weights and GPU drivers are not part of
  the optional portable ComfyUI-model importer.

## Offline reliability and unfinished visual work

- Ollama repetition-loop errors (`token repeat limit reached`) now receive bounded local
  recovery, not a quota/paywall message. Aborted answers are discarded; at most three
  attempts are made, adjusting sampling and GPT-OSS reasoning. Stop/other errors propagate.
- Geometry audits check rig arrays/segment lengths, preset mutation, finite drawing data
  and connected-circle artifacts. Runtime/geometry failures block export, including
  audit-only export. Reports distinguish technical clearance from visual approval.
  Rig patches deep-copy pose arrays and provide checked arm/world-joint helpers.
- The rebuilt 12-shot morning and 7-shot tiny-habits sources clear fresh technical audits.
  Morning contact sheets were inspected and a 30s preview rendered. These rebuilt versions
  have not received user visual approval or new final exports; existing MP4s are older.
  Tiny-habits s002 still shows journaling for a line naming both wake and journaling.
  That narrative correction remains outstanding. Preserve their scene-audit backups.
- The approved 15-shot reference is preserved. Its manually directed quality is not proof
  that a fresh automatic Ollama run matches it. Full-frame technical checks do not certify
  acting, contact, relevance or aesthetic quality. Older failure/repair snapshots are in
  `docs/HANDOFF-HISTORY.md`, not the active next-step instructions.

## Current product behavior

- Characters: new skeletal rig (`app/skeleton.mjs`, docs in the offline guide). Poses are fixed-length
  bone angles with joint limits, IK reach/plant and planted-foot walk/run; they solve to the existing
  11 joints, so the old `pose()` API and all checkers still work. Installed by `patch_rig.py`
  (upgrades already-patched studios); the local animation prompt (`SCENE_GUIDE`) prefers it for
  Ollama scene generation and repair, but this is guidance only: the model may still write legacy
  joint arrays, which the checker accepts. Published in `5b7f753` on `main`. `SCENE_GUIDE` is part of
  the scene cache key, so non-manual projects may regenerate scenes on their next offline run; manual
  or approved scenes are kept. `offline_cinematic.js` (approved reference) still uses the old pose API.
  Verified: 34 JS and 154 Python tests, one skeleton scene through the scene checker, contact sheets
  of every pose and gait, and a render through the real `drawFigure`. Not verified: how well the local
  Ollama model follows the new API, the run cycle's look (slightly crouched), or a full new video.
  First real offline Auto run (2026-11-13 13:44, `gpt-oss:20b`) exposed integration gaps: the model read
  `pose.hF` (undefined on angle poses), passed joint names such as `head` to `rigPose`, and invented
  `neckF`. Fixed: rig poses now expose read-only solved joints (`pose.hF`, non-enumerable), joint-name
  errors explain angles vs positions, and `SCENE_GUIDE` teaches `jointWorld(fig,'hF')` for props. The
  failed project re-rendered with no shot errors; press Auto again to continue from step 4. Other errors
  in that log (`g.fillStyle is not a function`, `const g` redeclared, `sh += n`) are generic model
  mistakes the existing repair pass fixed. Second run (14:07) showed the model using the API
  correctly but repeating two slips (`neckF`, and `rigReach(pose,'hF',...)`): the side argument now
  also accepts joint names, errors say what was received and suggest the real channel, and the prompt
  lists exact channel names. Restart the GUI so the new prompt loads. Not yet re-run end to end.
  Hoodie/face rendering is unchanged (uniform-width limbs; tapered limbs/hands/feet are a possible
  next step). Restart the GUI to load the engine update.

- Pipeline: ideas/script → English narration → kit animation, OpenArt or CastWorkshop clips → thumbnail →
  explicit YouTube Publish. Nothing is uploaded merely by generating a video.
- Script providers: Claude, OpenAI (Codex), Gemini CLI, Gemini API and Ollama. Animation
  also offers OpenArt and CastWorkshop (local). Check actual account/model availability;
  do not assume historic results.
- Voice: Piper is the default (`en_US-joe-medium`), Qwen3 is optional/local, Edge is online.
  Offline mode replaces Edge with Piper but retains an explicitly selected Qwen3 engine.
  English output applies to all providers; imported recordings are checked with Whisper.
- Automatic Ollama uses the local API rather than a general coding agent: the app owns
  project setup, Whisper alignment, beats, storyboard, per-shot source, checks, rendering/mixing.
  Automatic animation needs no Claude login/CLI; optional tool-based design/interactive
  operations retain the existing CLI bridge. Codex/Gemini/OpenArt adapters remain separate.
- Agent-based Codex visual QC remains explicit image inspection with sandboxed project writes
  and app-owned rendering. Do not apply its visual approval claims to text-only Ollama checks.

## Offline generation and reliability

- `app/local_animation.py`: whole-video storyboard followed by bounded scene-code requests.
  Enforces IDs/order, concrete setting/action/start/end states, camera variety and limited
  action repetition. Code prompts require consistent characters, layered sets, grounded props
  and actual anticipation/action/settle; avoid unrelated drinking/reaching/idle poses.
- Requests use 16K context by default. Script/text GPT-OSS reasoning defaults to low;
  storyboard/animation/repairs use medium. Optional `.env` overrides are documented in
  [OFFLINE-WORKFLOW.md](docs/OFFLINE-WORKFLOW.md). The model name can contain `studio64k`;
  automatic requests override context directly. Other models need JSON and JavaScript capability.
- Syntax errors receive up to three attempts with the latest failed code. Misplaced whitespace
  escapes are locally normalized only after Node rejects the original; strings/templates/regex
  literals and Unicode are preserved. Do not decode all JavaScript with `unicode_escape`.
- `build/local_animation.json` records input/prompt/source hashes, storyboard and visual settings.
  Completed unchanged scenes are reused. Approved/manual scenes are never rewritten by quality
  heuristics. A changed aspect/style/look stops their reuse before changing source/config, so
  they can be reviewed/reframed or a new project can be used. The approved project has a saved baseline.
- `app/ollama_provider.py`: streamed requests have a bounded queue, cancellation monitor and
  socket abort while awaiting headers/tokens. Local stalled-server tests return Stop under 1.5s.
  Studio-owned selected models are released before competing Qwen/alignment/render stages.
- `build/ollama_performance.json` covers setup through export, recording elapsed time, status,
  stage, failure/cancellation and available request metrics. Early planning failure preserves
  the prior checkpoint. A report-write error does not replace the original failure.
- `app/patch_kit.py`: uses the complete bundled browser binary checked on disk, or installed
  Chrome/Edge; missing scene modules are rejected even in still/contact-sheet renders.
  Apply the patcher after kit updates and restart the GUI after Python changes.

## Reusable scene checker

- `app/check_offline_scenes.py` orchestrates `app/offline_scene_audit.mjs`, which uses the
  same local player in Chromium/Chrome. Automatic offline runs invoke it before final export.
- Every output frame is drawn for runtime checking; up to eight snapshots/shot provide
  residual-motion and color/detail measurements in the action area, excluding captions.
  `app/offline_motion.mjs` compensates translation/zoom before measuring changes.
- Flagged generated scenes get one targeted local repair attempt with source backup, Node
  syntax validation and another real audit. Replacements must clear all warnings plus motion
  >=0.008 and color spread >=9; tiny gains/rounded-boundary warnings are insufficient.
  Failed replacements are rolled back. Remaining generated-scene warnings stop repair/export
  for review; approved/manual scenes stay protected from quality-heuristic rewrites.
- Reports, snapshots and backups live under `build/scene_audit/`. Reports always retain
  `visually_approved: false`. Metrics cannot establish beauty, narrative relevance, correct
  contact or meaningful acting, and camera compensation is not a perfect visual judge.
- Existing projects: double-click `Check-Offline-Animations.cmd` (default `--all --repair`),
  or run `.venv\Scripts\python.exe app\check_offline_scenes.py --all` for audit-only mode.
  Add `--project projects/<slug> --repair --export` for explicit single-project re-export.
  Without `--export`, repairs do not update an existing MP4. Do not run concurrent writers
  against the same project. `--all` requires an offline checkpoint and excludes `_` test projects.

## Approved visual reference and local media

- User rejected the first technically valid video, then approved the rebuilt version:
  "The animation now is awesome. Love it" and "Its awesome this way".
- Accepted direction: teal-hoodie figures, navy interiors, warm amber key/rim light, grounded
  desk/prop actions, timer inserts, close-ups and explanatory diagrams tied to narration.
- Local project: `growkaz-stickman-studio/projects/the-habit-that-halves-procrastination-11130433`.
  Its 15 scenes were hand-directed with `scenes/sets/cinematic.js`, not automatically generated
  to that quality by a proven end-to-end new-video run. Manual markers protect this reference.
- Local `out/final.mp4`: verified 67.64 seconds, 720x1280, audio and video. Original code/media
  backed up under `work/visual-rebuild-backup-1113`; earlier pose fixes under
  `work/scene-fix-backup-1113`. Latest reliability changes did not regenerate/change the MP4.
- The previous blank-video cause was an agent substituting FFmpeg `color=c=black` after
  browser/path failures. App-owned export now renders real scenes rather than accepting that substitute.

## Validation and remaining limits

- Last full-suite baseline: **149 Python tests and 16 Node tests passed** before the
  latest portable-import additions. Latest targeted portable suite: **13/13 pass**,
  including cache skipping, required-file permission failures, partial/manual-copy
  space estimates and deletion-path rejection. Provider suite: **14/14 pass**;
  standalone launcher suites: **9 existing + 3 recovery tests pass**. Git whitespace
  checks passed. These targeted counts are not a fresh full-suite total. Run the commands
  in [README](README.md#validation) from the checkout root.
- Real approved-project audit: **1,624 frames, 120 snapshots, 15 shots**, zero runtime failures
  or visual flags. A synthetic error on frame 11, outside snapshot times, was detected.
- Tests cover repair acceptance/rollback, warning thresholds, protected scenes, changed visual
  settings, setup/alignment/planning failures, early cancellation, stalled headers/tokens,
  camera-only translation and independent character movement.
- HTML regression tests cover repeated-run replacement, both entry filenames, escaped
  untrusted content, preview path restrictions, setup failures, stale-audit rejection and
  fresh findings retained after a stop for review.
- The updated Windows launcher was exercised against the approved project: it rebuilt the
  dashboard and displayed the Y/N prompt; No exited successfully. Chrome rendered the local
  report with 1 project, 15 scene sections, 120 previews and no page errors. The first preview
  decoded successfully and the dashboard layout was visually inspected.
- Live new-transport request to `gpt-oss-20b-studio64k:latest` returned OK and completion metrics.
  The whole-story planner previously validated 15 shots in 66.6 seconds. A blank synthetic
  scene was repaired and rerendered successfully. Scratch projects start `_` and are excluded.
- Do not claim a measured whole-video 10–25 minute duration: no complete new automatic run
  has established that estimate or parity with the manually directed reference. The 28-second
  NVENC render measured rendering existing code only.
- Development machine: RTX 3080 Laptop GPU, 16GB VRAM. Base model was seen 100% GPU at 16K;
  this does not prove residency of a separate 64K request. Windows user settings were saved
  for Flash Attention, q8_0 cache and one parallel request. A restart attempt was blocked by
  automatic approval review; do not assert those settings were activated or benchmarked.
  The prior settings backup is `work/ollama-environment-before-performance.json`.
- SoX/Python `flash-attn` warnings came from Qwen voice imports, not Ollama. They alone do
  not establish failure or active attention mode. Do not install unrelated acceleration
  packages merely to suppress a warning. See the offline guide for the observed tokenizer detail.
- Still unverified in this follow-up: a complete new automatic video matching the accepted
  reference, the full fresh installer, every provider/account combination and real YouTube upload.

## Documentation and next use

- [README](README.md): install/update, providers, voice engines, app usage, checker commands and tests.
- [Offline guide](docs/OFFLINE-WORKFLOW.md): detailed pipeline, reports, settings, recovery and limitations.
- [History](docs/HANDOFF-HISTORY.md): older observations and release context, not active instructions.
- Source/module and ScriptForge descriptions now reflect Piper/Qwen3/Edge and app-owned Ollama
  animation. Installed local ScriptForge documentation is synchronized from its tracked source.
- Restart the GUI to load code updates. On the next user-requested new video, check narrative
  relevance, framing, physical motion/contact and audio/video, then compare real end-to-end timing.
- Never print API keys/tokens or auth files. Retain manual/approved scenes and runtime backups;
  do not publish generated media or third-party kit content as part of a source update.
