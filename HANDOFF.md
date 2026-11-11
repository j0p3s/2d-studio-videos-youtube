# HANDOFF — 2D Animation Studio (2026-11-11)

## 1. Goal
- Portable Windows studio: ideas → script → Microsoft narration → GrowKaz animation → thumbnail → explicit YouTube upload. Scripts/animation support Claude, Codex and Gemini independently.

## 2. Current status
- Repo: private `j0p3s/2d-studio-videos-youtube`; latest code merged in PR #16, main `c4d17b1` before this handoff update.
- Source checkout: `C:/Users/Joao/Desktop/2D-Animation-Studio-Setup`; active app folder: `C:/Users/Joao/Desktop/2d-studio-videos-youtube-main`. Tracked files match; runtime data differs intentionally.
- All studio-owned settings, credentials, skills, caches, tools, Python environment and projects live beside each folder's .cmd launchers. Legacy `C:/Users/Joao/2D-Animation-Studio` remains a backup.
- Real Auto Short and private Publish succeeded: https://youtu.be/ZzwRZC0lCG4, channel “The Thought Lab”. Auto never publishes automatically.
- Auto offers Start fresh / Continue / Cancel; fresh reset waits for summary confirmation. New idea scripts get separate projects; Revise keeps the current project.
- GPU capture/encoding and CPU fallback are implemented. Earlier 1080p sample improved ~72 s → 16 s for 480 frames; this is not a guarantee for every project.
- PR #14: Gemini installation allows only @github/keytar's install script for that command; upstream deprecation warning can remain.
- PR #15: failed speech passages recover sequentially in smaller cached pieces. A real 9-passage narration recovered to 529.44 s and decoded cleanly.
- PR #16: Codex Windows animation explicitly trusts its workspace, enables a Windows sandbox when unset, preserves existing choices, enables rendering network access and stops blocked passes immediately.
- Current validation: sandboxed scene creation works, but Chrome spawn EPERM blocked contact-sheet QC. New app/host_render.py runs rendering/mixing in the app, requests agent visual review, and checkpoints approved passes plus pending QC. Three repairs get a separate final verification; resume skips rebuilding a pending pass. Real host rendering and sandboxed agent image inspection succeeded; 29 Python tests pass. The complete new flow is not yet run end to end.
- Android prototype exists in `Adnroid-App/` (spelling intentional): independent native renderer, free Edge speech, API-based AI, diagnostic exports. Device-tested 10-minute silent 1080p render; not a GrowKaz port.

## 3. Key decisions and reasons
- Everything studio-owned stays beside launchers; no persistent Windows environment variables or shared AI settings. Process-local environment overrides isolate caches/provider state.
- Use Python 3.12 and the local .venv. Reuse existing system Git/Node/FFmpeg/browser executables; do not relocate shared programs.
- All newly generated video content must be English. Microsoft Edge Neural narration is required; default en-US-AndrewMultilingualNeural. Old ElevenLabs/Portuguese settings migrate.
- Use canvas + three.js in Chrome/Edge + FFmpeg, not Remotion. AI generation remains online; offline/template generation was rejected.
- Video frame capture uses JPEG; inspected stills/sheets remain PNG. Probe NVENC → Intel QSV → AMD AMF; unavailable/failed GPU encoding falls back to CPU. Scene logic/audio stay CPU.
- Codex animation uses standalone CLI in the active folder's .tools; avoid Desktop bundled executable. Codex always remains sandboxed; the Full auto checkbox now applies only to Claude/Gemini.
- PowerShell 7 was discussed only: no change requested or made; installing it alone is unlikely to materially speed this pipeline.

## 4. Failed approaches — do not repeat
- Whole-script Edge request truncates/fails; use sentence-based passages, cache and retries. Service failures can occur with valid text/voice; do not discard completed audio.
- Bundled Playwright Chromium unpack hung under antivirus; prefer installed Chrome/Edge. Python 3.15 also failed faster-whisper/PyAV installation.
- Render errors left Chrome/server alive for ~7 min; patch exits on failure. Deleting an output directory used as a shell cwd causes Windows EPERM; empty it instead.
- Reusing an old slug overwrote earlier media; new ideas must discard old media/upload references. Do not rename an in-progress project casually.
- YouTube refresh with app-requested scopes caused invalid_scope; load saved granted scopes and accept broad youtube access.
- Codex workspace-write flag alone yielded read-only sessions in the portable non-Git folder. Explicit workspace trust + Windows sandbox passed; blocked zero-exit responses must raise errors before later passes.
- Whisper/PyAV direct decoding failed with metadata_errors; English import checks decode PCM through FFmpeg first.

## 5. Files that matter
- `app/studio_gui.py`: UI and pipeline; Auto ~581, install_ai ~859, script project reset ~1079, speech ~1328, Animate ~1763, YouTube ~2179 (search names as lines drift).
- `app/ai_providers.py`: CLI discovery, Windows sandbox and blocked-pass detection. `app/host_render.py`: project-scoped host rendering, visual QC checkpoints and final validation; both have tests.
- `app/portable_paths.py`: process-local paths, non-overwriting legacy migration/rebased copied JSON, local skill extraction; `app/test_portable_paths.py` covers migration.
- `app/language_policy.py`: English-only prompts/voices/import validation; `app/test_voice_recovery.py` covers cached speech recovery/outages.
- `app/patch_kit.py`, `app/video_encoder.mjs`: idempotent renderer/browser patches and adaptive encoder selection; `app/video_encoder.test.mjs` tests selection.
- `Install-2D-Studio.cmd`, `Launch-2D-Studio.cmd`: provision/run in their own directory; `plugin/GrowKaz_Stickman.plugin` contains the original kit and skills.
- Local-only: `settings.json`, `youtube/`, `work/<slug>/`, `growkaz-stickman-studio/projects/`, `.claude/`, `.codex/`, `.runtime/`, `.cache/`, `.tools/`, `.venv/`; all gitignored.

## 6. Next steps
1. Restart the active app, press Auto → Continue this project; confirm host-rendered sheets are visually inspected and the new checkpoint resumes correctly. Preserve existing authored scenes.
2. Finish the current ~502 s, four-pass project `5-tiny-rules-that-make-discipline-easier-11110026`; inspect its contact sheets, final audio/video and cross-pass style consistency.
3. Run `.venv/Scripts/python.exe -m unittest discover -s app -p "test_*.py"` and `node --test app/video_encoder.test.mjs` after relevant code changes.
4. For updates, push/merge a PR and sync tracked files into the active app folder, preserving runtime/config files. Reapply patch_kit.py to that folder's kit when needed; restart GUI after Python changes.

## 7. Open questions / gotchas
- GUI instances retain old code until restarted. Active project's settings.json is authoritative; never print API keys, OAuth tokens or provider auth files, or commit runtime data.
- Codex logs: active folder `.codex/sessions/**/*.jsonl`; Claude logs: `.claude/projects/`. Quiet logs can mean thinking/rendering, so check processes before calling it stalled.
- Intel/AMD hardware and a real mid-render GPU failure remain untested. Gemini live authentication/quality and full long multi-pass output still need verification.
- Migration copies only missing legacy files and rebases copied JSON paths; destination files win and original backup is retained. Local AI sign-in may be needed.
- Never treat an agent's exit code zero as proof a video exists. Verify actual project output and surface policy errors; do not silently bypass sandbox restrictions.
