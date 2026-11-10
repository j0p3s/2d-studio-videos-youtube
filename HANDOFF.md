# HANDOFF — 2D Animation Studio

## 1. Goal
A one-click Windows installer plus a desktop GUI for faceless YouTube videos. ScriptForge (from the PDF prompt) writes the script, there's a voiceover step, the GrowKaz Stickman plugin animates it through Claude Code, then a thumbnail and a YouTube upload. Repo: github.com/j0p3s/2d-studio-videos-youtube (private, `main`).

## 2. Current status
- **Done and pushed:** the installer, launcher and GUI (Setup / Script / Voiceover / Animate / Upload), ElevenLabs as an option, multi-pass "parts", a character-style picker, a real progress bar (stage, %, elapsed, ETA), passage-based voiceover with 3 at a time, and the **⚡ Auto** button (ideas → script → voice → animation → thumbnail, then waits for **Publish**).
- **Installed copy:** `%USERPROFILE%\2D-Animation-Studio`, updated by copying `app/*.py` over by hand after each change. The user is logged in to the Claude CLI, and script generation works.
- **Verified:** voiceover on a real 1,479-word script (8m53s, 10 s with 3 at a time). Self-test render through Chrome: 14/14 stills. `verify_kit` 29/29, doctor all OK.
- **Never run for real:** a full Animate run (Claude building and rendering a whole video), a YouTube upload, and Auto end to end. Auto was only simulated with fake steps.

## 3. Key decisions (don't re-debate)
- **Claude stays required** for scripts and animation. The user rejected offline mode (Ollama, templates, Piper).
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

## 5. Files that matter
- `Install-2D-Studio.cmd` — winget tools, Claude CLI, copies the kit and skills to `~/.claude/skills`, runs patch_kit, npm, pip, shortcut.
- `Launch-2D-Studio.cmd` — starts the GUI with the Python in `python.txt`.
- `app/studio_gui.py` — the whole app. Key spots:
  - `_find_home` L26
  - `prog` / `run_job` L331 / L371
  - `ask_claude` L446 (stream-json, partial messages)
  - `auto_run` / `_auto_step` L552 / L600
  - `_speech_chunks` / `_make_voice_edge` L1141 / L1160
  - `_video_prompt` / `_part_prompts` L1375 / L1416
  - `make_video` L1524
  - `_pipeline_state` L1604 (Animate progress from project files)
  - `_yt_service` / `upload` L1923 / L1943
- `app/patch_kit.py` — patches the installed kit: render.mjs browser fallback + `build/render_progress.json`, doctor.py, verify_kit hashes. Safe to run again.
- `app/skills/scriptforge/SKILL.md` — the PDF prompt as a skill; the GUI reads it as its prompt.
- `plugin/GrowKaz_Stickman.plugin` — a zip; the kit is in `skills/make-2d-video/kit`.
- Runtime, outside the repo: `~/2D-Animation-Studio/{growkaz-stickman-studio, work/<slug>, youtube/token.json, settings.json}`.

## 6. Next steps
1. Run **⚡ Auto** on a short video (Shorts or 2 min, 720p) and watch the Animate log and progress. This is the first real end-to-end test.
2. Fix whatever breaks there. Likely suspects: the `--allowedTools` list is too narrow (else use "Full auto"), and the `FINAL_VIDEO` line isn't found.
3. Test Publish with `youtube/token.json` (scope `youtube.upload`); the thumbnail needs a verified channel.
4. Check whether the multi-pass "parts" prompts keep the style consistent on a 6–10 minute video.
5. Possibly design the channel branding: the user is leaning towards renaming @AmITheVillainTV to "The Thought Lab" (handle e.g. `@ThoughtLabTV`).

## 7. Open questions / gotchas
- Line numbers above will drift; search by function name.
- After editing the repo, copy `app/*.py` to `~/2D-Animation-Studio/app/`, and run `patch_kit.py` again if it changed.
- `settings.json` holds the ElevenLabs key in plain text (it's gitignored). Never commit `token.json` or `client_secret.json`.
- Animate's ETA before the render stage is a pace estimate; during the render it's exact.
- The GrowKaz plugin and the PDF are third-party. The repo is private; check the licence before making it public.
