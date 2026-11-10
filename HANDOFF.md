# HANDOFF — 2D Animation Studio

## 1. Goal
A one-click Windows installer plus a desktop GUI for faceless YouTube videos. ScriptForge (from the PDF prompt) writes the script through the selected provider, there's a voiceover step, the GrowKaz Stickman plugin animates it through Claude Code, OpenAI Codex or Gemini CLI, then a thumbnail and a YouTube upload. Repo: github.com/j0p3s/2d-studio-videos-youtube (private, `main`).

## 2. Current status
- **English/Microsoft policy:** user requires all video content in English, irrespective of Portuguese chat instructions. `language_policy.py` wraps all AI requests (including revisions and interactive prompts); English-only voice options default to Microsoft `en-US-AndrewMultilingualNeural`. Voice generation uses Edge for every provider, including Codex/Gemini; old ElevenLabs selections reset to Edge. Imported/edited scripts normalize to English; modified narration normalizes before TTS. Existing English narration hashes avoid repeated AI translation. Imported audio is checked by Whisper on its first 30 seconds and must be confidently English. Unverified/non-English saved audio references are cleared from the current pipeline, keeping old files on disk. New narration/voice invalidates downstream media references. The earlier Portuguese quality video remains a historical test, not the language policy for future videos.
- **English-policy validation:** 13 Python tests (provider + language pipeline) pass; GUI smoke test verifies saved Portuguese/ElevenLabs settings migrate to English Microsoft Neural. Include `language_policy.py` alongside `studio_gui.py` and `ai_providers.py` in manual updates. Shared ScriptForge skill also states the English requirement. Live Microsoft Andrew Multilingual and Guy English speech generation succeeded; the plain Andrew variant returned NoAudioReceived despite being listed, so it is not offered. No atempo processing is applied to normal generated voiceovers.
- **Done and pushed:** the installer, launcher and GUI (Setup / Script / Voiceover / Animate / Upload), ElevenLabs as an option, multi-pass "parts", a character-style picker, a real progress bar (stage, %, elapsed, ETA), passage-based voiceover with 3 at a time, and the **⚡ Auto** button (ideas → script → voice → animation → thumbnail, then waits for **Publish**).
- **Installed copy:** `%USERPROFILE%\2D-Animation-Studio`, updated by copying the changed app files (including `app/video_encoder.mjs`) and rerunning `patch_kit.py`. The user is logged in to the Claude CLI, and script generation works.
- **Adaptive GPU encoding (2026-11-10):** probes NVIDIA NVENC, Intel Quick Sync, then AMD AMF at the actual output resolution; falls back to CPU x264. A failed GPU render waits for workers to finish and retries every part on CPU, avoiding mixed encoder output. Chrome requests the high-performance GPU on Windows; frame capture defaults to JPEG for video, PNG for stills. Audio processing and scene logic stay on CPU; concatenation and final mux copy the video stream.
- **GPU validation:** three encoder-selection tests pass; fresh-kit patching, repeat patching and Node syntax checks pass. On this PC, NVENC produced a 1920×1080 H.264 preview with two workers; a forced CPU preview also succeeded. The selected test project had missing scene files, so these verify encoding rather than complete scene output. Intel/AMD hardware and an actual mid-render GPU failure have not been tested on hardware. No new full-video speed benchmark was taken.
- **Codex quality test (2026-11-10):** script and full animation generated through the new Codex adapter, using saved ChatGPT authentication. Project `projects/codex-two-minute-rule-quality-20261110`, title "O truque dos dois minutos", pt-PT Edge Duarte narration, 22 shots, 16:9 1920×1080, 24 fps, exactly 60.000 s / 1,440 frames, H.264 + AAC. Generated low-volume music and 13 SFX cues. Full frame render used NVENC at about 47 fps / 31 s (excludes model work and audio mix). The final MP4 decodes without errors. Contact sheet and final frame reviewed: consistent blue-clothed character and legible overlays, but several compositions reuse the desk set. Original narration was slowed with atempo=0.81 and padded to 60 s; SRT timings were scaled to match. Original narration TXT is retained in the project. Video not uploaded. This supersedes the earlier missing-scene preview limitation for NVIDIA full-video validation, but does not establish a CPU/GPU speed comparison.
- **Provider validation:** eight adapter tests pass; GUI construction and Python compilation pass on installed Python 3.12. Updated GUI and adapter are copied into the installed app; restart any existing GUI to load them. Gemini live call correctly reports missing authentication (exit 41); user must sign in from Setup before real Gemini quality testing.
- **Verified:** voiceover on a real 1,479-word script (8m53s, 10 s with 3 at a time). Self-test render through Chrome: 14/14 stills. `verify_kit` 29/29, doctor all OK.
- **First real end-to-end run (2026-11-10):** ⚡ Auto on a Shorts video (9:16, 720p, Edge voice) went ideas → script → voiceover → animation → thumbnail with no input, in about 30 min. Result: "Why Motivation Is Lying to You", a 54 s MP4 with audio. Most of the time went into Claude writing and checking 28 shots; the full 1,299-frame render took 87 s. Published as **private** to the channel "The Thought Lab" (https://youtu.be/ZzwRZC0lCG4): processed, with tags and a custom thumbnail (the channel is verified).
- **Fixed after that run (PRs #2 and #3, merged):** render.mjs hanging ~7 min per failed render, EPERM on `build/stills`, PowerShell and context-mode tools denied in the headless Animate run, and Publish failing with `invalid_scope` (see §4).
- **Not yet run for real:** a long video built in several passes ("parts"), 6–10 min.

## 3. Key decisions (don't re-debate)
- English voice validation also passed with real audio: Microsoft Andrew Multilingual sample was transcribed exactly in English; the earlier Portuguese test narration was rejected by the import checker. `verify_english_recording` decodes the first 30 seconds through FFmpeg to float32 PCM before Whisper. Direct PyAV decoding failed on this PC with `metadata_errors` incompatibility, so do not replace this path with `decode_audio` without resolving that dependency mismatch.
- **Provider choice supersedes the earlier Claude-only decision:** the user requested OpenAI/Codex and Gemini alternatives. Scripts and animation now have independent provider/model choices in Setup; Claude is the compatibility default. Offline generation remains out of scope.
- **No Remotion.** The plugin renders with canvas + three.js in headless Chromium + ffmpeg.
- **Python 3.12, not `py -3`.** The PC's default is Python 3.15, and faster-whisper's `av` can't build there. The installer picks 3.12/3.11/3.13/3.10 and writes `python.txt`; the launcher uses it.
- **Chrome/Edge fallback** instead of Playwright's Chromium, because antivirus freezes its unpack. Done by `app/patch_kit.py`.
- **Voice method copied from j0p3s/reddit-video-generator `narration.py`:** ~1,400-character passages ending on sentences, 180 s timeout, 3 retries, cache, ffmpeg join.
- **Auto never publishes.** The user must press Publish, which also asks for confirmation.
- Commits use the GitHub no-reply email in local git config, because the account's email privacy blocks pushes with the real address.

## 4. Tried and failed
- **One edge-tts request for the whole script:** the service stops at about 1.5 min (`NoAudioReceived`). Fixed by using passages.
- **`npx playwright install chromium`:** freezes after `chrome.dll`, twice at the same spot. Don't retry; rely on the patch.
- **pip on Python 3.15:** `av` fails to build.
- **`cmd /k "echo … & \"claude.exe\""` from Python:** quotes get escaped to `\"`. Pass the exe as its own list argument (`claude_login`, ~L730).
- **Killing processes / `rm -rf` folders:** blocked by Claude's auto-mode permissions, so ask the user to do it.
- **render.mjs on failure** set `process.exitCode` but never exited. Chrome kept Node alive until an outer `timeout` killed it, costing ~7 min per failure. Now patched by `patch_kit.py` to exit at once.
- **Deleting `build/stills` on Windows** fails with EPERM if any shell has that folder as its working directory (Claude's shell stays in a folder after `cd`). Now patched to empty the folder instead of deleting it.
- **Animate's `--allowedTools` without `PowerShell`:** Claude Code on Windows reaches for PowerShell first, so every call was denied. The context-mode plugin's hook clips long output and points at its own MCP tools, which were also denied. Both are now in the list.
- **YouTube token loaded with the app's `SCOPES`:** the refresh asked for `youtube.readonly`, which the token never had (it has the broader `youtube` scope), so Google answered `invalid_scope`. Now it loads the scopes the token was actually granted (`_scopes_ok`).

## 5. Files that matter
- `Install-2D-Studio.cmd` — winget tools, Claude CLI, copies the kit and skills to `~/.claude/skills`, runs patch_kit, npm, pip, shortcut.
- `Launch-2D-Studio.cmd` — starts the GUI with the Python in `python.txt`.
- `app/studio_gui.py` — the whole app. Key spots:
  - `_find_home` (resolve installed kit)
  - `prog` / `run_job` (progress, worker lifecycle and provider snapshot)
  - `ask_ai` / `ask_claude` (provider routing / native Claude stream-json)
  - `auto_run` / `_auto_step` (automatic pipeline)
  - `_speech_chunks` / `_make_voice_edge` (passage voiceover)
  - `_video_prompt` / `_part_prompts` (animation prompts)
  - `make_video` (animation passes)
  - `_pipeline_state` (Animate progress from project files)
  - `_scopes_ok` / `_yt_service` / `upload`
- `app/patch_kit.py` — patches the installed kit: render.mjs browser fallback, `build/render_progress.json`, exit on failure, empty-instead-of-delete output folders; doctor.py; verify_kit hashes. Each patch is marked, safe to run again, and prints "not found" instead of breaking if the plugin changes.
- `app/video_encoder.mjs` — runtime FFmpeg hardware probes and encoder settings, copied into the kit by `patch_kit.py`. Required alongside the patcher. `app/video_encoder.test.mjs` tests selection, unsupported drivers and CPU overrides with `node --test app/video_encoder.test.mjs`.
- `app/ai_providers.py` — Codex/Gemini CLI discovery (including the bundled Codex executable), npm launcher resolution from package metadata, command permissions, portable GrowKaz instructions and JSONL events. GUI `ask_ai` routes script vs animation calls; existing Claude parsing stays in `ask_claude`. Per-stage settings: `script_provider`, `animation_provider`, `script_model`, `animation_model`. Active jobs snapshot these values.
- Provider checks: `python -m unittest discover -s app -p test_ai_providers.py`; Python 3.12 GUI construction smoke test. Codex is authenticated through ChatGPT on this PC. Gemini CLI is installed but requires user authentication; no successful Gemini model call has been verified. Text-only modes are Codex read-only / Gemini plan. Animation defaults are workspace-write / auto-edit; Full auto explicitly enables broader execution. Gemini trusts the working directory only for the invocation.
- `app/skills/scriptforge/SKILL.md` — the PDF prompt as a skill; the GUI reads it as its prompt.
- `plugin/GrowKaz_Stickman.plugin` — a zip; the kit is in `skills/make-2d-video/kit`.
- Runtime, outside the repo: `~/2D-Animation-Studio/{growkaz-stickman-studio, work/<slug>, youtube/token.json, settings.json}`.

## 6. Next steps
1. Run a 6–10 minute video (Parts: Auto → about 3–4 passes) and check that the style stays consistent across passes. This is the one part of the pipeline not yet run for real.
2. The user should watch the private test Short (https://youtu.be/ZzwRZC0lCG4) in YouTube Studio and decide whether to delete it or make it public. Claude couldn't view its frames because of the context-mode image block.
3. Possibly design the channel branding. The channel is already named "The Thought Lab"; check whether the handle (e.g. `@ThoughtLabTV`), banner and avatar still need doing.
4. Verify a populated full video with adaptive GPU encoding and compare output quality and elapsed render time against CPU. Test Intel/AMD and real GPU failure recovery when suitable hardware is available.

## 7. Open questions / gotchas
- Line numbers above will drift; search by function name.
- After editing the repo, copy changed app files to `~/2D-Animation-Studio/app/`, including `video_encoder.mjs` when updating the patcher or encoder. Run `python app/patch_kit.py <installed-kit-path>` from the installed app's parent folder. The installer already copies the entire app directory.
- Encoder override: `STUDIO_ENCODER=auto|cpu|gpu|nvenc|qsv|amf`, or renderer `--encoder` with the same values. Explicit GPU choices still fall back to CPU if unavailable. `--gl swiftshader` controls software drawing separately from video encoding. GPU quality settings approximate x264 and file sizes may differ.
- `settings.json` holds the ElevenLabs key in plain text (it's gitignored). Never commit `token.json` or `client_secret.json`.
- Animate's ETA before the render stage is a pace estimate; during the render it's exact.
- To see what a headless Animate run is doing (or why it went quiet), read its session log: `~/.claude/projects/C--Users-Joao-2D-Animation-Studio-growkaz-stickman-studio/*.jsonl`, newest file. The log only updates when a step finishes, so a quiet log can mean Claude is thinking. Check for live `node render.mjs` / Chrome processes before calling it stuck.
- That session-log path applies to Claude only. For Codex/Gemini, use the GUI animation log and their own CLI session facilities; all providers report tool activity through the app and use the same filesystem-based render progress.
- The user's context-mode plugin also runs inside headless Animate runs and blocks reading images and large files directly.
- The running GUI keeps the code it started with. After copying `app/*.py`, restart the app to pick up the change.
- Include `ai_providers.py` when deploying GUI changes. Install/sign-in buttons for Codex/Gemini are on Setup. CLI credentials remain in vendor-managed storage; never copy them into the repo. There is no automatic cross-provider fallback, so quality tests identify the provider actually used.
- Driving the GUI with computer use: the window belongs to `pythonw.exe`, which Windows lists as "IDLE (Python 3.12 64-bit)". `open_application` on that name opens a real IDLE shell too, so close it.
- The GrowKaz plugin and the PDF are third-party. The repo is private; check the licence before making it public.
