# HANDOFF — 2D Animation Studio (2026-11-11, after PR #20)

## 1. Goal
- Portable Windows studio: ideas → script → Microsoft narration → GrowKaz animation → thumbnail → explicit YouTube upload.
- Scripts and animation can each use Claude, OpenAI (Codex), Gemini (CLI) or Gemini API (key from `.env`).

## 2. Current status
- Repo: private `j0p3s/2d-studio-videos-youtube`. PR #20 (Gemini API provider) is merged into `main`.
- Source checkout: `C:/Users/Joao/Desktop/2D-Animation-Studio-Setup`. Active app folder: `C:/Users/Joao/Desktop/2d-studio-videos-youtube-main`. The active folder had disappeared and was recreated on 2026-11-11 from `main` (PR #20) with `.env`, `settings.json` and `youtube/token.json` copied from the source checkout; the installer ran there and its check passed. Its `work/` is empty.
- Everything studio-owned (settings, credentials, skills, caches, tools, `.venv`, projects) lives beside each folder's `.cmd` launchers. Legacy `C:/Users/Joao/2D-Animation-Studio` is a backup only.
- Working: real Auto Short and private Publish (https://youtu.be/ZzwRZC0lCG4, channel "The Thought Lab"). Auto never publishes by itself.
- Working: Auto offers Start fresh / Continue / Cancel; new idea scripts get their own project; Revise keeps the current one.
- Working: GPU capture/encoding with CPU fallback (1080p sample: ~72 s → 16 s for 480 frames).
- Working: speech passages recover in smaller cached pieces (PR #15); Codex on Windows runs sandboxed with a trusted workspace (PR #16).
- Working: `app/host_render.py` renders and mixes in the app, asks the agent for visual QC, and checkpoints approved passes (PRs #18, #19).
- The source checkout is also a complete studio (own `.env`, `.venv`, kit) and holds the two earlier projects in `work/`.
- New in PR #20: "Gemini API" provider. Ideas/scripts use one direct REST call; animation runs through the Gemini CLI with the same key. 33 Python tests pass; a live call returned text on `gemini-3.5-flash`.
- Working: session log `studio.log` beside the launchers (fresh on every launch, secrets masked) and a "Show logs" button in the sidebar with an Errors-only filter.
- Not yet run end to end: the host-render flow on a full multi-pass video, and any GUI script/Animate run with Gemini API.
- Android prototype in `Adnroid-App/` (spelling intentional): separate native renderer, not a GrowKaz port.

## 3. Key decisions and reasons
- Gemini API is an **additional** provider, not a replacement. A rewrite that replaced `ai_providers.py` broke the GUI calls, the provider menu, Codex and the tests, so the CLI providers were restored.
- Animation with Gemini API goes through the Gemini CLI, because a plain API call cannot write files or run the render kit.
- The studio `.env` wins over inherited Windows variables, and a `GEMINI_MODEL` that is not a model name is dropped. A Windows user variable `GEMINI_MODEL=<model-that-succeeded>` (a pasted placeholder) made the Gemini CLI fail with HTTP 400 "unexpected model name format".
- The Gemini key is read from `.env` in the studio folder and sent in the `x-goog-api-key` header, never in the URL. `.env` is gitignored.
- A Gemini API request that waits the full 600 s fails at once instead of retrying; retries apply only to 429/500/503 and connection errors.
- Everything studio-owned stays beside the launchers; no persistent Windows environment variables. Python 3.12 in the local `.venv`; reuse system Git/Node/FFmpeg/browser.
- All generated content is English. Microsoft Edge Neural narration, default `en-US-AndrewMultilingualNeural`.
- Canvas + three.js in Chrome/Edge + FFmpeg, not Remotion. Video frames are JPEG; inspected stills/sheets stay PNG. Encoder probe: NVENC → QSV → AMF → CPU.
- Codex always stays sandboxed; the Full auto checkbox applies to Claude and Gemini only.

## 4. Failed approaches — do not repeat
- Replacing `ai_providers.py` with a Gemini-only module (different `run_agent`/`portable_prompt` signatures, lowercase provider names).
- Whole-script Edge speech requests truncate or fail; use sentence-based passages with cache and retries.
- Bundled Playwright Chromium hung under antivirus; use installed Chrome/Edge. Python 3.15 broke faster-whisper/PyAV.
- Render errors left Chrome alive ~7 min (patch now exits). Deleting an output folder that is a shell cwd gives EPERM; empty it instead.
- Reusing an old slug overwrote earlier media. YouTube refresh with app-requested scopes gave `invalid_scope`; load the saved granted scopes.
- Codex `workspace-write` alone gave read-only sessions in the non-Git folder; explicit trust + Windows sandbox fixed it.
- Whisper/PyAV direct decoding failed with `metadata_errors`; decode PCM through FFmpeg first.

## 5. Files that matter
- `app/studio_gui.py`: UI and pipeline. `.env` load at line 109, `ask_ai` ~442, provider menu ~724 (search names; lines drift).
- `app/ai_providers.py`: providers. `load_env_file` 22, `gemini_api_text` 45, `run_agent` 208. Tests: `app/test_ai_providers.py`.
- `app/session_log.py`: the session log (tested). The GUI logs jobs, child-process output, dialogs and tracebacks through it.
- `app/host_render.py`: host rendering, visual QC checkpoints, final validation (has tests).
- `app/portable_paths.py`, `app/language_policy.py`: local paths/migration and English-only policy (both tested).
- `app/patch_kit.py`, `app/video_encoder.mjs`: idempotent kit patches and encoder selection.
- `Install-2D-Studio.cmd`, `Launch-2D-Studio.cmd`; `plugin/GrowKaz_Stickman.plugin` holds the original kit and skills.
- Local-only, gitignored: `.env`, `settings.json`, `youtube/`, `work/`, `growkaz-stickman-studio/`, `.claude/`, `.codex/`, `.runtime/`, `.cache/`, `.tools/`, `.venv/`.

## 6. Next steps
1. Start the GUI from the active folder (`Launch-2D-Studio.cmd`); `settings.json` still selects Gemini (CLI) for scripts and animation.
2. In Setup choose "Gemini API" for "Ideas & script"; generate ideas and one script. If the model is overloaded, set another in the Model box (e.g. `gemini-3.5-flash`).
3. Try Animate with Gemini API (needs the Gemini CLI installed from Setup); check that the CLI accepts the key and writes scenes.
4. Run Auto on a long video (~500 s, four passes); the earlier `5-tiny-rules-that-make-discipline-easier-11110026` project was lost with the old active folder. Check host-rendered sheets, checkpoint resume and cross-pass style.
5. After code changes run `.venv/Scripts/python.exe -m unittest discover -s app -p "test_*.py"` and `node --test app/video_encoder.test.mjs`.

## 7. Open questions / gotchas
- The Windows user variables `GEMINI_MODEL` (placeholder text) and `GEMINI_API_KEY` still exist; the studio no longer depends on them, but the user may want to delete `GEMINI_MODEL`.
- The recreated active folder has no `.tools` (the installer found Claude Code already on the machine); Codex and Gemini CLI may need installing from Setup. Why the old folder vanished is unknown.
- Run the installer non-interactively by full path with stdin redirected; its last `choice` prompt then errors harmlessly.
- On 2026-11-11 `gemini-3.8-flash` (code default) and `gemini-flash-latest` (in `.env`) returned 503 or did not answer; Google-side. `GEMINI_MODEL` in `.env` overrides the default; the Setup Model box overrides both.
- A Gemini API script request blocks until it returns (no streaming, no progress, Cancel does not interrupt it).
- GUI instances keep old code until restarted. Never print API keys, OAuth tokens or provider auth files, and never commit runtime data.
- Logs: start with `studio.log` (or Show logs). Agent detail: Codex `.codex/sessions/**/*.jsonl`, Claude `.claude/projects/`. Quiet logs can mean thinking or rendering.
- Untested: Intel/AMD encoders, a mid-render GPU failure, Gemini CLI live sign-in and output quality.
- Exit code zero from an agent does not prove a video exists; verify the project output.
