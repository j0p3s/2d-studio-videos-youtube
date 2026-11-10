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

## Notes
- Rendering is CPU-heavy. A 1080p video renders at roughly 0.5–2× real time on a modern PC, and 4K is much slower.
- "Full auto" on the Animate page runs Claude Code with `--dangerously-skip-permissions`. Leave it off unless a run gets stuck on permissions.
- If the app won't open, check `%USERPROFILE%\2D-Animation-Studio\gui_error.log`.
