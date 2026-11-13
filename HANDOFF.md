# Handoff — 2D Animation Studio

Updated 2026-11-13. This file describes current behavior. Older release/session notes are
archived in [HANDOFF-HISTORY.md](docs/HANDOFF-HISTORY.md) and are not current instructions.

## Project and publication

- Model-upload protection: `.gitignore` excludes `models/` and `Models/` at any depth,
  common model weight extensions and partial safetensors/GGUF downloads, in addition
  to the existing portable-runtime exclusions. Verified no model folders or weights
  were tracked before this update. Models remain local; none were moved or uploaded.

- Current integration update (2026-11-13): Studio now offers **CastWorkshop (local)** as
  animation-only provider, including Auto and a **Shorts 15s test** script option. Setup
  has root/loopback URL fields plus check/finish-setup actions. It uses the installed
  Krea2 text-to-image and H3 ref-to-video graphs directly, sequentially, as 8s visual clips;
  Studio retains its selected narration. Optional H3 audio-reference inputs are removed.
  No Telegram, VPS/database, CastWorkshop conversation worker, MOSS voice audition or
  model migration is invoked by Studio Auto. Native H3 generated audio is discarded by
  the existing shot assembler. Captions/generated music/authored SFX remain unsupported
  for this route and are disclosed in its log. See `docs/CASTWORKSHOP.md` for contracts.
  Source follows upstream checkout `24a9462`; setup/model/performance/voice doc hashes
  matched GitHub main on this date. Job IDs/ambiguous submissions are preserved, queues
  are checked and the upstream GPU lock is used. Changed inputs require a fresh project.
- D: launcher created at `D:\CastWorkshop-Test\Launch-Test.cmd`, with standalone Krea →
  MOSS → target-15s H3 runner and settings. Maintained sources live under
  `integrations/castworkshop/test-kit/`. This standalone talking-video test differs from
  Studio's narrated montage route. CUDA torch 2.14.1+cu130, torchvision and torchaudio
  installed successfully; torch detects RTX 3080 Laptop GPU. ComfyUI requirements also
  installed. All four pinned custom-node packages installed; models are still downloading
  through the user's IDLE process. Setup waits for that process to close rather than
  racing its `.part` writes. No complete real CastWorkshop render has been verified.
  Studio GUI initialized in an isolated settings smoke test; desktop screenshot capture
  timed out, so do not claim visual-layout approval. Final regression run: 145 Python,
  16 Node and seven standalone launcher tests pass. Nothing is copied/moved off D: or
  scheduled for later migration.
  Real local ComfyUI startup/API check passed on RTX 3080 with no required image/video
  nodes missing and both MOSS nodes registered. The owned smoke-test server was stopped.
  Final D: readiness check: **30/31 model assets ready**; only
  `minimax_h3_hybrid_fl2va_ref2va_b25-49_nvfp4.safetensors` remains incomplete.
  `pip check` reports no broken requirements. The owned setup waiter was stopped after
  dependencies installed; the user's original IDLE/downloader was not stopped. Finish
  that download/close its IDLE window, then rerun Setup or Launch-Test.cmd as appropriate.

- CastWorkshop organization: user requested a fully portable package inside the Studio,
  then explicitly said **do not move anything after download completion; test on D: first**.
  No migration/copy of real runtimes or model weights has been performed or scheduled.
  Prepared `integrations/castworkshop/Launch.cmd`, `portable.py`, README and eight passing
  offline tests (including actual Windows junction relocation). Import is manual only:
  preserves D:, checks incomplete downloads/running source processes, verifies model
  manifest hashes and copies with SHA256 checks; bundles each app's Python/dependencies
  and FFmpeg when invoked. Runtime/media/private folders are gitignored. At preparation
  source still had 24 partial/metadata files, a Python process and no ComfyUI torch.
  Full import/GPU generation remains untested. Ollama service/LLM weights are not bundled;
  do not claim a completely standalone stack. Await user after the original D: test.

- Latest follow-up: attached Desktop `studio.log` ended at 09:53:07 with Ollama
  `prediction aborted, token repeat limit reached` during animation, not a cloud quota.
  `ollama_provider.text` now retries that specific error locally within its existing
  three-attempt budget, discards aborted answers, varies sampling seed/settings and
  lowers GPT-OSS recovery reasoning. Animation logs retry notices. Other errors and Stop
  still propagate. Regression coverage includes streamed/HTTP failures, bounded retries,
  discarded partial output and cancellation. Restart GUI to load this local change.
  The failed real video run has not yet been resumed or validated end to end.
- Fresh audits of the rebuilt 12-shot morning and 7-shot tiny-habits projects completed
  without technical failures. Morning contact sheet inspected and 30s preview rendered;
  final exports were not run in this follow-up. Tiny-habits s002 still combines wake and
  journal narration while showing only journaling; that narrative correction is pending.

- IN PROGRESS: user rejected the last video aesthetically and requested all rigs/scenes
  rechecked. Added `rig_safety.mjs`, `patch_rig.py` and portable patch_kit integration;
  installed pose-copy/finite-coordinate fixes locally. Added `offline_cinematic.js` and
  rebuilt the 12-shot morning and 7-shot tiny-habits project sources with backups under
  their `build/scene_audit/backups/full-visual-rebuild-*` folders. These latest rebuilt
  sources have since cleared fresh technical audits, but are not visually approved or exported. Existing MP4s are
  the prior versions. Do not claim this work complete. The approved 15-shot reference
  sources were preserved. User then switched focus to a separate CastWorkshop 15s test
  and explicitly authorized installing its experimental stack on D:.
- Latest local blocker fixed: `3-morning-habits-that-build-iron-like-di-11130831/s003`
  was a static whiteboard/pen scene despite the line “The 1-minute breathe.” Replaced it
  with a deterministic breathing action, backed up its source/story/checkpoint under
  `build/scene_audit/backups/breathing-fix`, and updated its description/hash with manual
  protection so Auto reuses the correction. Full 12-shot audit clears all detected issues;
  s003 residual motion is 0.0663. Repair prompts now prioritize narration and stateless
  animation over an incorrect previous storyboard. This does not certify the other shots'
  artistic quality.
  Export completed successfully to that project's `out/final.mp4`; the current HTML
  report was rebuilt. The GUI may retain its old error dialog until dismissed/restarted.
- Latest local change: geometry-aware offline checking (`app/offline_geometry.mjs`).
  Browser-only instrumentation checks every drawn rig pose for invalid joint arrays,
  malformed segments and shared-preset mutation; Canvas checks catch non-finite coordinates
  and distant filled circles accidentally connected into polygons. Reports show frame/time,
  open previews by default and replace unconditional Passed labels with visual review required.
  Geometry failures block export, including audit-only export. Generation/repair guidance
  now specifies connected anatomical joints, finite array coordinates and safe pose copying.
  Regression: the generated `5-tiny-habits-that-build-unbreakable-dis-11130720` video had
  seven scenes incorrectly cleared by the old pixel-only audit. New checks flag all seven
  (broken anatomy, object-valued hands, preset mutation, connected corner circles).
  The user-approved 15-scene reference still clears the full 1,624-frame audit.
  Live local-model repair of the seven-scene project accepted s001/s002/s004/s005/s007
  by technical checks and reverted s003/s006, which still had malformed anatomy. Export
  was stopped; the existing MP4 is unchanged. Do not describe the whole film as fixed.
  This change is included in the current source update.
- Previously published feature: `Check-Offline-Animations.cmd` rebuilds a combined HTML dashboard
  each run and asks **Open the HTML report? [Y/N]**. New module `app/offline_report.py`
  writes identical `reports/offline-animations/.index.html` and `index.html`, with project/
  scene states, repairs/errors and expandable copied previews. Direct CLI supports
  `--report-dir`; launcher pins the folder beside itself. Failures/cancellation/empty runs
  replace old results; failed checks do not substitute stale successful audit data. A fallback
  entry page is written by the launcher even if Python cannot start. The dashboard uses no
  external assets; untrusted text is escaped and previews must resolve within the project's
  audit folder. Root `reports/` is now gitignored. Opening HTML alone shows a snapshot;
  running the launcher performs new checks and rebuilds it. The user explicitly authorized
  publishing this feature and its updated documentation directly to `main`. Generated HTML,
  report assets, private settings and videos remain excluded from the source commit.
- Checkout: `C:\Users\Joao\Desktop\2D-Animation-Studio-Setup`.
- Repository: https://github.com/j0p3s/2d-studio-videos-youtube, branch `main`.
- User explicitly requested the folder, GitHub and all documentation be updated with the
  latest reliability fixes. Direct pushes to `main` are authorized for this update; no PR
  merge is required when the commit is pushed directly. Use `git log`/remote refs for the
  current commit ID instead of assuming this document's own commit hash.
- Prior published commits: `8a270d0` added offline generation/auditing; `6eccb5a` recorded that
  publication; `2a07820` published stricter acceptance, cancellation, cache protection,
  full-frame checks, early failure reporting and consolidated documentation. The current
  update adds the rebuilt HTML dashboard, open-report prompt and report regression tests.
- Only source, tests, launchers and documentation belong in Git. Keep `.env`, credentials,
  logs, private settings, virtual environments, models, caches and generated media excluded.
  The third-party animation kit is supplied separately and remains git-ignored.

## Current product behavior

- Pipeline: ideas/script → English narration → animation or OpenArt shots → thumbnail →
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

- Latest automated results: **145 Python tests and 16 Node tests pass**, plus seven standalone
  D: launcher tests, plus clean Python syntax and Git whitespace checks. Run the commands
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
