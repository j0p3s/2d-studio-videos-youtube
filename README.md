# 2D Animation Studio (Windows)

A one-click setup and desktop app for making faceless, animated, stick-figure YouTube videos with Claude Code, then uploading them. It does the same thing as the Grow With Kaz tutorial without the copy-paste steps.

## Install
1. Double-click **`Install-2D-Studio.cmd`**. It installs whatever is missing:
   - Git, Node.js LTS, Python 3.12 and FFmpeg (through winget)
   - the Claude Code CLI
   - the **GrowKaz Stickman Studio**, taken from `plugin\GrowKaz_Stickman.plugin`, along with three.js, Playwright and a headless Chromium
   - Python packages: numpy, scipy, faster-whisper, edge-tts, customtkinter, Pillow and the YouTube API client
   - Claude Code skills: `make-2d-video`, `new-video`, `render-video`, `video-sound`, `video-styles` and **`scriptforge`** (the "2D Niche Prompt" PDF turned into a skill)
2. The app is installed to `%USERPROFILE%\2D-Animation-Studio`, and the installer adds a **"2D Animation Studio"** shortcut to your desktop.
3. The first time you open the app, go to **Setup → Log in to Claude** and sign in once.

You can run the installer again at any time. It skips anything already installed and never touches your `projects\` folder.

> Remotion, which the tutorial installs, isn't needed. The plugin draws every frame with canvas and three.js in headless Chromium and encodes with FFmpeg.

## Using the app
| Step | What it does |
|---|---|
| **① Script** | Pick a niche and a length (Shorts up to 12 min) to get 10 ideas from ScriptForge. Pick one and you get the full script, alternative titles, tags, a description and thumbnail text. Type edit requests to revise it. |
| **② Voiceover** | Uses free Microsoft Edge neural voices, ElevenLabs (paste your API key, then *Load voices*), or your own recording. |
| **③ Animate** | Claude Code runs the GrowKaz pipeline: Whisper timestamps, a shot plan, code-drawn 2D/3D scenes, music, sound effects and the final MP4. Long videos are built in several *parts*, one Claude pass per section. **Suggest character styles** renders 4 character looks for you to choose from. **Open in Claude Code** lets you run it interactively instead. |
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
- "Full auto" on the Animate page runs Claude Code with `--dangerously-skip-permissions`. Leave it off unless a run gets stuck on permissions.
- If the app won't open, check `%USERPROFILE%\2D-Animation-Studio\gui_error.log`.
