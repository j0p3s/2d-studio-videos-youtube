# 2D Animation Studio (Windows)

An independent Android 15+ prototype is in [Adnroid-App](Adnroid-App/README.md): native 1080p/24 fps rendering, up to 10 minutes, free English Microsoft Neural narration through edge-tts (no Azure key), an exportable diagnostic/crash-log menu and Gemini/OpenAI/Claude APIs. See its README for credentials, device benchmarks and differences from the desktop pipeline.

A one-click setup and desktop app for making faceless, animated, stick-figure YouTube videos with Claude Code, OpenAI Codex or Gemini, then uploading them. It does the same thing as the Grow With Kaz tutorial without the copy-paste steps.

## Install
1. Double-click **`Install-2D-Studio.cmd`**. It installs whatever is missing:
   - Git, Node.js LTS, Python 3.12 and FFmpeg (through winget)
   - the Claude Code CLI
   - the **GrowKaz Stickman Studio**, taken from `plugin\GrowKaz_Stickman.plugin`, along with three.js, Playwright and a headless Chromium
   - Python packages: numpy, scipy, faster-whisper, edge-tts, customtkinter, Pillow and the YouTube API client
   - Claude Code skills: `make-2d-video`, `new-video`, `render-video`, `video-sound`, `video-styles` and **`scriptforge`** (the "2D Niche Prompt" PDF turned into a skill)
2. Everything owned by the studio lives beside `Install-2D-Studio.cmd` and `Launch-2D-Studio.cmd`: settings, YouTube credentials, projects, AI settings, skills, caches and the local Python environment. Keep this folder in a writable location.
3. In **Setup**, choose your providers for **Ideas & script** and **Animation & character designs** independently. Claude remains the default. Sign in to each provider you select.

## AI providers

| Provider | Setup | Integration |
|---|---|---|
| Claude | **Log in to Claude** | Existing Claude Code workflow and skills. |
| OpenAI (Codex) | **Install OpenAI (Codex)**, then **Sign in: OpenAI (Codex)** | Codex CLI with its saved ChatGPT/API authentication. |
| Gemini | **Install Gemini**, then **Sign in: Gemini** | Gemini CLI with its own Google/API authentication. |

Models are optional: leave the field blank to use the CLI default. Provider and model selections are saved for the next run; each active job keeps the selections it started with. Voiceover, GPU rendering and YouTube upload use the same pipeline for every provider. CLI authentication is managed by the vendor; the app does not copy credentials into its settings.

All generated video content is **English only**, regardless of the language used to give instructions: scripts, narration, metadata, subtitles and on-screen text. This applies to Claude, Codex and Gemini, including revisions and interactive animation prompts. Imported/edited scripts are normalized into English. Edited narration is translated before speech generation when needed; unchanged English narration is preserved.

Speech generation always uses **Microsoft Neural (Edge)** with an English voice; the default is `en-US-AndrewMultilingualNeural`, reading English narration. English US, UK and Australian voice options remain available. Saved Portuguese voices are replaced with the English default, and saved ElevenLabs engine selections reset to Microsoft. ElevenLabs is not offered in the voice-generation UI. Imported recordings are checked for English speech in the first 30 seconds using Whisper; uncertain or non-English recordings are rejected. Old unverified/non-English voice references are cleared from the current pipeline so Auto regenerates speech; the media files remain on disk. Restart the GUI after updating.

Codex and Gemini receive the GrowKaz skill and reference paths explicitly, so animation does not depend on Claude Code being installed. Text tasks request text-only operation in read-only/plan mode. Animation uses Codex workspace-write or Gemini auto-edit; commands requiring extra permission can fail in headless mode. **Full auto** applies only to Claude/Gemini. Codex keeps its sandbox while the app handles rendering. Gemini trusts the current working folder for that invocation. Final publishing still requires the app's Publish action.

The installer provisions the local GrowKaz skills under `.claude/skills` beside the launchers for all three providers. For manual updates, include `app/ai_providers.py` alongside `studio_gui.py`. Run adapter tests with `python -m unittest discover -s app -p test_ai_providers.py`. A missing login, unavailable model or exhausted quota is reported as an error; the app does not silently substitute another provider.

You can run the installer again at any time. It skips anything already installed and never touches your `projects\` folder.

For a manual app update, copy the changed files from `app` into `.\app`, including `video_encoder.mjs` alongside `patch_kit.py`. Run the installed patcher with the installed `growkaz-stickman-studio` directory as its argument. Restart the GUI after updating Python files. The installer performs the copy and patch steps automatically.

> Remotion, which the tutorial installs, isn't needed. The plugin draws every frame with canvas and three.js in headless Chromium and encodes with FFmpeg.

## Using the app
| Step | What it does |
|---|---|
| **① Script** | Pick a niche and a length (Shorts up to 12 min) to get 10 ideas from ScriptForge through your selected script provider. Pick one and you get the full script, alternative titles, tags, a description and thumbnail text. Type edit requests to revise it. |
| **② Voiceover** | Uses English Microsoft Neural voices, including Andrew, Guy, Aria and Jenny, for every AI provider. You can also import a recording verified as English. |
| **③ Animate** | Your selected animation agent runs the GrowKaz pipeline: Whisper timestamps, a shot plan, code-drawn 2D/3D scenes, music, sound effects and the final MP4. Long videos are built in several *parts*, one agent pass per section. **Suggest character styles** renders 4 character looks for you to choose from. **Open animation agent** lets you run it interactively instead. |
| **④ Upload** | Makes a thumbnail from a video frame with big text on it, fills in the title, description and tags from the script, and uploads to YouTube (private, unlisted, public or scheduled). |

## YouTube setup (once)
Go to **Upload → YouTube setup** and follow the steps there. You create a free Google Cloud project, enable the *YouTube Data API v3*, create an OAuth **Desktop app** client, and choose its `client_secret.json`. Then click **Connect**. Until Google verifies your app, YouTube may force uploads to private; you can make them public in YouTube Studio.

**Already have a `token.json`?** Put it in `.\youtube\token.json` and restart the app. It needs the `youtube.upload` scope and must contain `refresh_token`, `client_id`, `client_secret` and `token_uri`. If uploads fail, put your `client_secret.json` in the same folder, delete `token.json`, and click **Connect** again. Never commit either file (`.gitignore` already excludes them).

## Troubleshooting
- **Installer sits at "Downloading Chromium … 100%" and doesn't move.** Antivirus is blocking the unpack of `chrome.dll`. Press **Ctrl+C**, answer **N**, and let the installer finish. `app/patch_kit.py` (applied by the installer) makes the renderer use your installed **Chrome or Edge** instead, and the studio's doctor accepts that.
- **faster-whisper / `av` fails to install.** Very new Pythons (3.14+) have no packages for it yet. The installer prefers Python 3.12, 3.11, 3.13 or 3.10 (installing 3.12 if none is present), saves the choice in `python.txt`, and the launcher uses it.
- **Setup shows "GrowKaz studio kit: missing"** when the app is started from the repo folder: update to the latest version. Run the installer beside the launcher to provision the local studio kit.
- **"Log in to Claude" opens a window that says the program isn't recognized**: fixed in the latest version. Update `app\studio_gui.py`.
- **Claude says "Not logged in"**: use **Setup → Log in to Claude**, choose *Claude account with subscription*, and sign in in the browser.

## Notes
- Video encoding automatically tries NVIDIA NVENC, Intel Quick Sync, then AMD AMF using a real FFmpeg probe at the output resolution. If none works, it uses CPU x264. If a GPU fails during rendering (including concurrent encoder session limits), it retries all parts on CPU before joining them. Render logs show the selected encoder.
- Chrome uses its available graphics acceleration (and requests the high-performance GPU on Windows). Frame stepping, audio processing and scene logic remain on CPU; final assembly copies the encoded video without re-encoding. Video capture defaults to JPEG; still images remain PNG.
- To force CPU encoding, set `STUDIO_ENCODER=cpu` before launching the app. Renderer overrides: `--encoder auto|cpu|gpu|nvenc|qsv|amf`; `--gl swiftshader` forces software drawing. GPU quality settings approximate x264 quality and can produce different file sizes.
- **Full auto** uses Claude's `--dangerously-skip-permissions` or Gemini's `yolo` mode. Codex always remains sandboxed, including when that checkbox is selected.
- If the app won't open, check `.\gui_error.log`.

## Portable configuration
The launcher copies missing settings, YouTube credentials, work and the kit from the old `%USERPROFILE%\2D-Animation-Studio` installation on first use, rebasing saved project paths. Existing destination files win. The old installation is retained as a backup; use this folder's launcher going forward.

AI logins are scoped to this installation (`.claude`, `.codex`, `.runtime/home/.gemini`); sign in again from Setup. Existing personal AI configurations are not moved or overwritten. Cache and CLI path variables apply only to the studio's processes, with no `setx` or Windows environment changes. Shared prerequisite programs (Python, Node, Git, FFmpeg and installed browsers) may still be used; new Python dependencies and npm AI packages install locally. Secrets and generated content are gitignored.

Gemini installation explicitly permits only `@github/keytar` install scripts for that npm command (`--allow-scripts=@github/keytar`), without changing your Windows or user npm configuration. Its deprecation warning may still appear because it is an upstream dependency. A completed package installation with exit code zero is treated as success; use Setup to sign in afterwards.

If Microsoft speech returns no audio for a passage, other passages finish first. Failed passages then recover sequentially in smaller cached pieces using the same voice. Completed audio is preserved; if the service is still unavailable, Auto can resume later without repeating finished passages.

Codex animation on Windows uses the standalone CLI from Setup, an explicitly trusted studio workspace and a Windows sandbox (unelevated when no sandbox is configured; existing selections are preserved). Network access is enabled for the renderer's localhost server and model downloads while filesystem writes remain workspace-scoped. A pass reporting policy/permission failures stops the pipeline immediately rather than proceeding through all passes without producing a video.

For Codex video generation, the writable workspace is the current project. The app launches the installed renderer, renders real contact sheets for the agent to inspect, and performs the final render, mix and audio/video-duration checks. The agent cannot change the installed renderer or engine outside its project. A pass is checkpointed only after explicit visual approval; changed project files invalidate the checkpoint. This avoids Chromium spawn EPERM inside the Windows sandbox without granting the agent unrestricted access.
