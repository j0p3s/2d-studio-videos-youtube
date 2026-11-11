# HANDOFF — 2D Animation Studio (2026-11-11, after PR #28)

## 1. Goal
- Portable Windows studio: ideas → script → narration → GrowKaz animation → thumbnail → explicit YouTube upload.
- Scripts and animation can each use Claude, OpenAI (Codex), Gemini (CLI), Gemini API (key from `.env`) or Ollama (offline).
- It must keep working with no AI credits: local AI through Ollama and a local Piper voice.

## 2. Current status
- Repo: **public** `j0p3s/2d-studio-videos-youtube` (earlier notes wrongly said private). `main` is at PR #28 (third-party files untracked; #27 was the empty-answer retry and GPL-3.0 license); no open PRs. The source checkout is on `main`, level with `origin/main`.
- Source checkout: `C:/Users/Joao/Desktop/2D-Animation-Studio-Setup` (git). Active app folder the user launches: `C:/Users/Joao/Desktop/2d-studio-videos-youtube-main` (not git). It is synced from `main` with `git archive HEAD | tar -x -C <folder>`; files deleted in the repo must be removed there by hand.
- Everything studio-owned (settings, credentials, skills, caches, tools, `.venv`, projects) lives beside each folder's `.cmd` launchers. Both folders are complete studios with their own `.env`, `.venv`, `.cache` and `work/`. Legacy `C:/Users/Joao/2D-Animation-Studio` is a backup only.
- The user launches the GUI themself, on 2026-11-11 from the source checkout (its `studio.log` showed the run). Do not launch it for them; hidden smoke runs that do not save settings are fine.
- 47 Python tests pass in both folders (2026-11-11). The Node encoder test was not re-run after PR #20.
- Working: real Auto Short and private Publish (https://youtu.be/ZzwRZC0lCG4, channel "The Thought Lab"). Auto never publishes by itself.
- Working: Auto offers Start fresh / Continue / Cancel; new idea scripts get their own project; Revise keeps the current one.
- Working: GPU capture/encoding with CPU fallback (1080p sample: ~72 s → 16 s for 480 frames).
- Working: Edge speech passages recover in smaller cached pieces (PR #15); Codex on Windows runs sandboxed with a trusted workspace (PR #16).
- Working: `app/host_render.py` renders and mixes in the app, asks the agent for visual QC, and checkpoints approved passes (PRs #18, #19).
- Working: session log `studio.log` beside the launchers (fresh on every launch, secrets masked) and a "Show logs" sidebar button (PR #21).
- PR #20: "Gemini API" provider. PR #22: the Gemini CLI signs in with the key for Gemini API animation.
- PR #23: offline mode (Ollama provider, "Always work offline" switch, installer step). PR #24: Piper voice replaces the Windows voice. PR #25: Piper is the default voice engine. PR #26: Upload is allowed in offline mode.
- 2026-11-11: the user ran Auto offline with `gpt-oss:20b` (now downloaded). Ideas worked; "Writing script" failed once with "returned no text" after 30 s. Six direct repeats with the real ScriptForge prompt all answered (20-43 s), so the cause is unconfirmed; `ollama_provider.text` now asks again up to twice on an empty answer and reports reasoning length and stop reason (PR #27).
- Not yet run end to end: the host-render flow on a full multi-pass video; a GUI Animate run with Gemini API; a full offline Animate run; a whole voiceover from the Voice page with Piper; the full installer after its offline/Piper changes.
- Android prototype in `Adnroid-App/` (spelling intentional): separate native renderer, not a GrowKaz port.

## 3. Key decisions and reasons
- Offline mode: provider "Ollama (offline)" plus a Setup switch "Always work offline" that overrides both provider menus, forces the Piper voice and sets `HF_HUB_OFFLINE` for Whisper. It means local AI and voice, not "no internet": Upload is not blocked (user request).
- Ollama is a system app like Git/Node, not studio-owned: its models live in the real user profile, so the server is started with the real environment, not the studio's.
- Offline animation runs the Claude Code CLI against Ollama's Anthropic-compatible endpoint (`claude_env` in `app/ollama_provider.py`), so the same skill and tools are used and no Claude login is needed. The model is copied once with a 64k context (`agent_model`), because Ollama's default window is too small and that endpoint cannot set it per request.
- Default offline model `gpt-oss:20b` (14 GB) was picked because it fits the 16 GB GPU, not from a quality comparison.
- Voice: Piper is the default engine (user request); "Free (Edge)" stays selectable on the Voice page. Settings saved before Piper existed always said Edge, so that value only counts as a choice once the `piper_default` setting exists. Offline mode forces Piper without changing the saved engine.
- Piper: `piper-tts` (pip, GPL-3) runs inside the studio's Python. Voices are `.onnx` files in `.cache/piper`, downloaded by the installer, by Setup's install, or on first use. Default `en_US-ryan-high` (120 MB); setting `piper_voice`. About 30 s of speech per 8 s on this CPU. The Windows SAPI voice was removed (too robotic).
- Gemini API is an **additional** provider, not a replacement. A rewrite that replaced `ai_providers.py` broke the GUI calls, the provider menu, Codex and the tests, so the CLI providers were restored.
- Animation with Gemini API goes through the Gemini CLI, because a plain API call cannot write files or run the render kit. It uses its own config folder (`.runtime/home/gemini-api-key`, see `gemini_key_home`) that selects key sign-in, because the CLI's normal folder keeps a Google login once chosen and ignores the key.
- Google now rejects the Google-account login in the Gemini CLI (`IneligibleTierError`, "migrate to Antigravity"), so the plain "Gemini" provider no longer works for this account. The error message points the user to "Gemini API".
- The studio `.env` wins over inherited Windows variables, and a `GEMINI_MODEL` that is not a model name is dropped. The Gemini key is sent in the `x-goog-api-key` header, never in the URL. `.env` is gitignored.
- A Gemini API request that waits the full 600 s fails at once instead of retrying; retries apply only to 429/500/503 and connection errors.
- No persistent Windows environment variables. Python 3.12 in the local `.venv`; reuse system Git/Node/FFmpeg/browser.
- All generated content is English. Edge voice default `en-US-AndrewMultilingualNeural`.
- Canvas + three.js in Chrome/Edge + FFmpeg, not Remotion. Video frames are JPEG; inspected stills/sheets stay PNG. Encoder probe: NVENC → QSV → AMF → CPU.
- Codex always stays sandboxed; the Full auto checkbox applies to Claude and Gemini only.
- License (user request 2026-11-11): GPL version 3, `LICENSE` at the root, for the studio's own code. The GrowKaz plugin and the niche-prompt PDF are third-party: they were untracked and gitignored on 2026-11-11 (user request) but stay on disk in both folders, where the installer and `install_local_skills` still need the plugin. They are still in the public git history; purging that needs a history rewrite and force-push, only on the user's explicit say-so. `app/skills/scriptforge/SKILL.md` is derived from that PDF and is still tracked.
- Workflow the user follows: each change goes on a branch and a PR; merge and sync the active folder only after they say so.

## 4. Failed approaches — do not repeat
- Replacing `ai_providers.py` with a Gemini-only module (different `run_agent`/`portable_prompt` signatures, lowercase provider names).
- `GEMINI_CLI_SYSTEM_SETTINGS_PATH` to force key sign-in: the CLI skips it ("parent directory is insecure").
- Whole-script Edge speech requests truncate or fail; use sentence-based passages with cache and retries.
- Bundled Playwright Chromium hung under antivirus; use installed Chrome/Edge. Python 3.15 broke faster-whisper/PyAV.
- Render errors left Chrome alive ~7 min (patch now exits). Deleting an output folder that is a shell cwd gives EPERM; empty it instead.
- Reusing an old slug overwrote earlier media. YouTube refresh with app-requested scopes gave `invalid_scope`; load the saved granted scopes.
- Codex `workspace-write` alone gave read-only sessions in the non-Git folder; explicit trust + Windows sandbox fixed it.
- Whisper/PyAV direct decoding failed with `metadata_errors`; decode PCM through FFmpeg first.
- Spawning `claude` with `--dangerously-skip-permissions` for a test is refused by the session's safety check; a test limited to `--allowedTools Write` in a temp folder is allowed.

## 5. Files that matter
- `app/studio_gui.py`: UI and pipeline. Search by name (lines drift): `ask_ai`, `ask_ollama`, `apply_offline`, `_offline_status`, `_on_engine`, `make_voice`, `upload`.
- `app/ai_providers.py`: providers (`load_env_file`, `gemini_api_text`, `gemini_key_home`, `run_agent`). Tests: `app/test_ai_providers.py`.
- `app/ollama_provider.py`: local AI (server start, model check, streamed text, model download, Claude-CLI environment). `app/piper_voice.py`: Piper voice to MP3. Tests for both in `app/test_ollama_provider.py` (fake Ollama server).
- `app/session_log.py`: the session log (tested). The GUI logs jobs, child-process output, dialogs and tracebacks through it.
- `app/host_render.py`: host rendering, visual QC checkpoints, final validation (has tests).
- `app/portable_paths.py`, `app/language_policy.py`: local paths/migration, English-only policy and the voice-engine default (both tested).
- `app/patch_kit.py`, `app/video_encoder.mjs`: idempotent kit patches and encoder selection.
- `Install-2D-Studio.cmd`: 8 steps; creates a `.env` template, installs `piper-tts`, pre-downloads the Whisper `small` model and the Piper voice, and offers Ollama + `gpt-oss:20b` (two Y/N prompts that default to N after 30 s). `Launch-2D-Studio.cmd` starts the GUI.
- `plugin/GrowKaz_Stickman.plugin` (local only, gitignored) holds the original kit and skills; the installer also looks in Downloads and stops with a clear message when it is missing.
- Local-only, gitignored: `plugin/`, the niche-prompt PDF, `.env`, `settings.json`, `youtube/`, `work/`, `growkaz-stickman-studio/`, `.claude/`, `.codex/`, `.runtime/`, `.cache/`, `.tools/`, `.venv/`.

## 6. Next steps
1. Wait for the user's next request; nothing is in progress.
2. The user is trying a full offline Auto run. If "returned no text" comes back, read the new detail in `studio.log`. Watch whether the model really calls tools during Animate.
3. Make one voiceover from the Voice page with Piper and listen to it (this overwrites the current project's voiceover, so only on the user's say-so).
4. Online path: Setup → "Gemini API" for both stages, Model `gemini-3.5-flash`; try Animate. Claude is the recommended provider for animation.
5. Run Auto on a long video (~500 s, four passes) and check host-rendered sheets, checkpoint resume and cross-pass style.
6. After code changes run `.venv/Scripts/python.exe -m unittest discover -s app -p "test_*.py"` and `node --test app/video_encoder.test.mjs`.

## 7. Open questions / gotchas
- Offline animation is NOT proven. Verified live: Ollama text through the GUI, Piper voice, Whisper loading offline, and the Claude CLI reaching Ollama. With the only chat model on this PC (`llama3.2`, 3B) the CLI got an answer but the model claimed it wrote a file without calling the tool. `gpt-oss:20b` is downloaded now (runs 100% on the GPU) but has not reached Animate yet.
- `gpt-oss` is a reasoning model: Ollama returns its reasoning in `message.thinking` and the answer in `message.content`; only the content is used.
- Ollama on this PC: `gpt-oss:20b`, `llama3.2`, `dolphin-mistral`, `wizard-vicuna-uncensored`, a deepseek-coder GGUF, and a leftover test copy `llama3.2-latest-studio32k` (remove with `ollama rm llama3.2-latest-studio32k`). A short text answer took 76 s on `llama3.2`.
- The active folder has `piper-tts` and the `en_US-ryan-high` voice, but no Whisper model in its `.cache`; it downloads on the first video made online, or by re-running that folder's installer. The source checkout has it.
- The source checkout's settings now select OpenAI (Codex) for scripts and Claude for animation, with "Always work offline" on. The active folder's settings may still select Gemini (CLI), which Google rejects.
- Gemini models on 2026-11-11: through the CLI with the key, `gemini-3.5-flash` answered but took ~115 s for one line; `gemini-flash-latest` (set in `.env`) did not answer within 200 s; `gemini-3.8-flash` (code default) returned 503; `gemini-2.5-flash` is retired (404). The Setup Model box overrides `.env`, which overrides the default.
- The Windows user variable `GEMINI_MODEL` has been deleted. `GEMINI_API_KEY` may still exist as a user variable; the studio does not depend on it.
- Run the installer non-interactively by full path with stdin redirected, through PowerShell (`cmd //c` fails from Git Bash); its last `choice` prompt then errors harmlessly.
- A Gemini API script request blocks until it returns (no streaming, no progress, Cancel does not interrupt it).
- Choosing a voice engine changes the setting in memory; it is written to `settings.json` by the next action that saves settings.
- GUI instances keep old code until restarted. Never print API keys, OAuth tokens or provider auth files, and never commit runtime data.
- Logs: start with `studio.log` (or Show logs). Agent detail: Codex `.codex/sessions/**/*.jsonl`, Claude `.claude/projects/`. Quiet logs can mean thinking or rendering.
- Untested: Intel/AMD encoders, a mid-render GPU failure, a real upload with the offline switch on.
- Exit code zero from an agent does not prove a video exists; verify the project output.
