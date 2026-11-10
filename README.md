# 2D Animation Studio (Windows)

A one-click setup and desktop app for making faceless, animated, stick-figure YouTube videos with Claude Code, OpenAI Codex or Gemini, then uploading them. It does the same thing as the Grow With Kaz tutorial without the copy-paste steps.

## Install
1. Double-click **`Install-2D-Studio.cmd`**. It installs whatever is missing:
   - Git, Node.js LTS, Python 3.12 and FFmpeg (through winget)
   - the Claude Code CLI
   - the **GrowKaz Stickman Studio**, taken from `plugin\GrowKaz_Stickman.plugin`, along with three.js, Playwright and a headless Chromium
   - Python packages: numpy, scipy, faster-whisper, edge-tts, customtkinter, Pillow and the YouTube API client
   - Claude Code skills: `make-2d-video`, `new-video`, `render-video`, `video-sound`, `video-styles` and **`scriptforge`** (the "2D Niche Prompt" PDF turned into a skill)
2. The app is installed to `%USERPROFILE%\2D-Animation-Studio`, and the installer adds a **"2D Animation Studio"** shortcut to your desktop.
3. In **Setup**, choose your providers for **Ideas & script** and **Animation & character designs** independently. Claude remains the default. Sign in to each provider you select.

## AI providers

| Provider | Setup | Integration |
|---|---|---|
| Claude | **Log in to Claude** | Existing Claude Code workflow and skills. |
| OpenAI (Codex) | **Install OpenAI (Codex)**, then **Sign in: OpenAI (Codex)** | Codex CLI with its saved ChatGPT/API authentication. |
| Gemini | **Install Gemini**, then **Sign in: Gemini** | Gemini CLI with its own Google/API authentication. |

Models are optional: leave the field blank to use the CLI default. Provider and model selections are saved for the next run; each active job keeps the selections it started with. Voiceover, GPU rendering and YouTube upload use the same pipeline for every provider. CLI authentication is managed by the vendor; the app does not copy credentials into its settings.

Codex and Gemini receive the GrowKaz skill and reference paths explicitly, so animation does not depend on Claude Code being installed. Text tasks request text-only operation in read-only/plan mode. Animation uses Codex workspace-write or Gemini auto-edit; commands requiring extra permission can fail in headless mode. **Full auto** enables the selected agent's unrestricted mode for unattended local rendering. Gemini trusts the current working folder for that invocation. Final publishing still requires the app's Publish action.

The installer provisions the shared GrowKaz skills under `~/.claude/skills` for all three providers. For manual updates, include `app/ai_providers.py` alongside `studio_gui.py`. Run adapter tests with `python -m unittest discover -s app -p test_ai_providers.py`. A missing login, unavailable model or exhausted quota is reported as an error; the app does not silently substitute another provider.

You can run the installer again at any time. It skips anything already installed and never touches your `projects\` folder.

For a manual app update, copy the changed files from `app` into `%USERPROFILE%\2D-Animation-Studio\app`, including `video_encoder.mjs` alongside `patch_kit.py`. Run the installed patcher with the installed `growkaz-stickman-studio` directory as its argument. Restart the GUI after updating Python files. The installer performs the copy and patch steps automatically.

> Remotion, which the tutorial installs, isn't needed. The plugin draws every frame with canvas and three.js in headless Chromium and encodes with FFmpeg.

## Using the app
| Step | What it does |
|---|---|
| **① Script** | Pick a niche and a length (Shorts up to 12 min) to get 10 ideas from ScriptForge through your selected script provider. Pick one and you get the full script, alternative titles, tags, a description and thumbnail text. Type edit requests to revise it. |
| **② Voiceover** | Uses free Microsoft Edge neural voices, ElevenLabs (paste your API key, then *Load voices*), or your own recording. |
| **③ Animate** | Your selected animation agent runs the GrowKaz pipeline: Whisper timestamps, a shot plan, code-drawn 2D/3D scenes, music, sound effects and the final MP4. Long videos are built in several *parts*, one agent pass per section. **Suggest character styles** renders 4 character looks for you to choose from. **Open animation agent** lets you run it interactively instead. |
| **④ Upload** | Makes a thumbnail from a video frame with big text on it, fills in the title, description and tags from the script, and uploads to YouTube (private, unlisted, public or scheduled). |

## YouTube setup (once)
Go to **Upload → YouTube setup** and follow the steps there. You create a free Google Cloud project, enable the *YouTube Data API v3*, create an OAuth **Desktop app** client, and choose its `client_secret.json`. Then click **Connect**. Until Google verifies your app, YouTube may force uploads to private; you can make them public in YouTube Studio.

**Already have a `token.json`?** Put it in `%USERPROFILE%\2D-Animation-Studio\youtube\token.json` and restart the app. It needs the `youtube.upload` scope and must contain `refresh_token`, `client_id`, `client_secret` and `token_uri`. If uploads fail, put your `client_secret.json` in the same folder, delete `token.json`, and click **Connect** again. Never commit either file (`.gitignore` already excludes them).

## Troubleshooting
- **Installer sits at "Downloading Chromium … 100%" and doesn't move.** Antivirus is blocking the unpack of `chrome.dll`. Press **Ctrl+C**, answer **N**, and let the installer finish. `app/patch_kit.py` (applied by the installer) makes the renderer use your installed **Chrome or Edge** instead, and the studio's doctor accepts that.
- **faster-whisper / `av` fails to install.** Very new Pythons (3.14+) have no packages for it yet. The installer prefers Python 3.12, 3.11, 3.13 or 3.10 (installing 3.12 if none is present), saves the choice in `python.txt`, and the launcher uses it.
- **Setup shows "GrowKaz studio kit: missing"** when the app is started from the repo folder: update to the latest version. The app now falls back to the installed studio in `%USERPROFILE%\2D-Animation-Studio`.
- **"Log in to Claude" opens a window that says the program isn't recognized**: fixed in the latest version. Update `app\studio_gui.py`.
- **Claude says "Not logged in"**: use **Setup → Log in to Claude**, choose *Claude account with subscription*, and sign in in the browser.

## Notes
- Video encoding automatically tries NVIDIA NVENC, Intel Quick Sync, then AMD AMF using a real FFmpeg probe at the output resolution. If none works, it uses CPU x264. If a GPU fails during rendering (including concurrent encoder session limits), it retries all parts on CPU before joining them. Render logs show the selected encoder.
- Chrome uses its available graphics acceleration (and requests the high-performance GPU on Windows). Frame stepping, audio processing and scene logic remain on CPU; final assembly copies the encoded video without re-encoding. Video capture defaults to JPEG; still images remain PNG.
- To force CPU encoding, set `STUDIO_ENCODER=cpu` before launching the app. Renderer overrides: `--encoder auto|cpu|gpu|nvenc|qsv|amf`; `--gl swiftshader` forces software drawing. GPU quality settings approximate x264 quality and can produce different file sizes.
- **Full auto** uses Claude's `--dangerously-skip-permissions`, Codex's `--dangerously-bypass-approvals-and-sandbox`, or Gemini's `yolo` approval mode, according to the selected animation provider.
- If the app won't open, check `%USERPROFILE%\2D-Animation-Studio\gui_error.log`.
