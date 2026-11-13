# 2D Animation Studio (Windows)

A Windows desktop app for narrated stick-figure videos with local Ollama or connected AI providers, optional OpenArt shots and YouTube upload. Offline animation uses an app-managed storyboard, scene generation, checks and export pipeline.

## Install
0. The animation kit is not part of this repository. Get `GrowKaz_Stickman.plugin` and put it in the `plugin\` folder beside the installer, or in your Downloads folder.
1. Double-click **`Install-2D-Studio.cmd`**. It installs whatever is missing:
   - Git, Node.js LTS, Python 3.12 and FFmpeg (through winget)
   - the Claude Code CLI
   - the **animation studio kit**, taken from `plugin\GrowKaz_Stickman.plugin`, with three.js and Playwright; rendering uses a complete bundled Chromium or installed Chrome/Edge
   - Python packages: numpy, scipy, faster-whisper, edge-tts, piper-tts, customtkinter, Pillow and the YouTube API client
   - Claude Code skills: `make-2d-video`, `new-video`, `render-video`, `video-sound`, `video-styles` and **`scriptforge`** (the "2D Niche Prompt" PDF turned into a skill)
2. Everything owned by the studio lives beside `Install-2D-Studio.cmd` and `Launch-2D-Studio.cmd`: settings, YouTube credentials, projects, AI settings, skills, caches and the local Python environment. Keep this folder in a writable location.
3. In **Setup**, choose providers for **Ideas & script** and **Animation & character designs** independently. Sign in for CLI providers, configure an API key for Gemini API, or install/download a local Ollama model for offline use.

## AI providers

| Provider | Setup | Integration |
|---|---|---|
| Claude | **Log in to Claude** | Existing Claude Code workflow and skills. |
| OpenAI (Codex) | **Install OpenAI (Codex)**, then **Sign in: OpenAI (Codex)** | Codex CLI with its saved ChatGPT/API authentication. |
| Gemini | **Install Gemini**, then **Sign in: Gemini** | Gemini CLI with its own Google/API authentication. |
| Gemini API | Configure `GEMINI_API_KEY` in the studio `.env` | Text uses the API directly; tool-based animation uses the Gemini CLI with that key. |
| Ollama (offline) | Install Ollama and download a model once | Local API for ideas/scripts and automatic animation; no Claude login or CLI agent needed for automatic animation. Optional tool-based design/agent operations retain the CLI bridge. |
| OpenArt (AI video) | **Install OpenArt**, then **Sign in: OpenArt** (browser login, no API key) | Animation only. The official `openart` CLI generates one AI still per shot and optionally a short clip from it; the studio cuts the shots to the narration with FFmpeg. No animation kit or agent involved. |

Provider/model selections are saved; each active job keeps its initial selection. A blank model uses the adapter default; API/Ollama requests require an available or installed model. Setup offers model lists when supported. Voice engines are selected separately. CLI authentication is managed by the vendor rather than copied into `settings.json`. YouTube upload needs a connection and the Publish action.

All generated video content is **English only**, regardless of the language used to give instructions: scripts, narration, metadata, subtitles and on-screen text. This applies to every provider, including revisions and interactive prompts. Imported/edited scripts are normalized into English. Edited narration is translated before speech generation when needed; unchanged English narration is preserved.

Voiceover supports **Piper (offline)**, **Qwen3 (calm, on this PC)** and **Free (Edge)**. Piper is the default, with `en_US-joe-medium`; download its voice once. Qwen3 is optional, runs in `.venv-qwen`, and can use an NVIDIA GPU; Setup installs its dependencies/model once. Edge needs internet and offers English Microsoft voices. Offline mode replaces Edge with Piper; selected Qwen3 remains local. ElevenLabs is not offered in the voice-generation UI. Imported recordings are checked for English speech in the first 30 seconds with Whisper; uncertain/non-English recordings are rejected. Clearing old unverified references does not delete their media.

Codex and Gemini receive skill/reference paths explicitly. Text tasks request text-only operation; agent animation uses Codex workspace-write or Gemini auto-edit. The **Full auto** permission setting controls agent CLIs: Codex remains sandboxed while the app renders. Automatic Ollama animation uses direct local requests and app-owned commands instead. Its text-only checks cannot provide visual approval. Final publishing still requires the app's Publish action.

The installer provisions animation skills under `.claude/skills` for agent-based operations. Automatic Ollama animation uses a focused API guide rather than loading the full agent skill into each request. Missing logins, unavailable models and exhausted quotas are reported instead of silently switching providers.

You can run the installer again at any time. It skips anything already installed and never touches your `projects\` folder.

Close the GUI before updating. Update the entire `app` folder and root launchers/documentation, not just `studio_gui.py`: the offline pipeline/checker has several modules. For a clean Git checkout, use `git pull --ff-only`; preserve local edits first. Reapply patches with `.\.venv\Scripts\python.exe app\patch_kit.py growkaz-stickman-studio`, then restart the studio. The installer applies patches when provisioning the kit. See [offline workflow and troubleshooting](docs/OFFLINE-WORKFLOW.md).

> Remotion, which the tutorial installs, isn't needed. The plugin draws every frame with canvas and three.js in headless Chromium and encodes with FFmpeg.

## Using the app
| Step | What it does |
|---|---|
| **① Script** | Pick a niche and a length (Shorts up to 12 min) to get 10 ideas through your selected script provider. Pick one and you get the full script, alternative titles, tags, a description and thumbnail text. Type edit requests to revise it. |
| **② Voiceover** | English speech with Piper, Qwen3 or Edge, or import a recording verified as English. |
| **③ Animate** | Automatic Ollama: alignment → whole-story direction → bounded 2D scene requests → all-frame runtime/motion checks → render/mix. Agent providers can create 2D/3D scenes in passes. Optional character-design/interactive tools use provider adapters. OpenArt instead generates images/clips and assembles them to narration. |
| **④ Upload** | Makes a thumbnail from a video frame with big text on it, fills in the title, description and tags from the script, and uploads to YouTube (private, unlisted, public or scheduled). |

## OpenArt (AI-generated shots)
**Smooth local assembly:** scene boundaries now use short cross-dissolves (~0.42 seconds), with extra overlap handles that preserve the narration timeline. Short AI clips use slow motion to fill a scene instead of freezing their last frame; stills use continuous camera motion instead of abrupt crop resets. Boundaries are processed two scenes at a time to avoid a large all-scenes filter graph. This adds local encoding work, not paid generation requests, when the source images/clips are already cached. To improve an existing completed video, use **Animate → Make the video** again; Auto reuses a completed final MP4 instead of rebuilding it. Pauses baked into an original source clip cannot be removed by this timing adjustment alone.

**Save OpenArt credits** is now enabled by default for new and existing installations, including Auto. For new projects it generates still images only, uses approximately 12 seconds per image for long videos or 6 seconds for Shorts, adds continuous local zoom/pan and short scene dissolves, and exports at 720p by default (choose a higher resolution with Save credits switched off). Parallel generation remains 3 scenes by default. An 8-minute video therefore needs about 40 images and no paid video clips instead of 80 images plus 80 clips at 6 seconds. Image costs still depend on the chosen model; no fixed monthly video count is promised. Local image movement is a different visual style from AI character animation.

The setting is saved in the studio's `settings.json` as `openart_save_credits`. Turn the switch off in Setup to use custom shot lengths and AI clips. Compatible in-progress OpenArt projects retain their original shot length/motion mode to reuse paid media; the saving defaults apply to new projects. Scripts and shot prompts now request immediate hooks, concrete narrative beats, truthful titles and a complete payoff. These are creative directions, not a guarantee of audience retention or virality. Other animation providers and publishing behavior are unchanged.

OpenArt is an alternative to the stick-figure pipeline for the **Animation** stage: photoreal or illustrated AI shots instead of code-drawn scenes. OpenArt has no public API key; its official programmatic route is the [OpenArt CLI](https://github.com/OpenArt-AI/cli), which signs in through your browser and spends your account's normal credits. Set it up once:

1. **Setup → Install OpenArt** downloads the release binary into the studio's `.tools` folder (nothing is added to your Windows PATH or profile). Then **Sign in: OpenArt** opens a console and your browser for the OAuth login; the credential is stored inside the studio (`.runtime\home\.openart`). **Check OpenArt account** shows your plan and credit balance.
2. In **Setup** choose **OpenArt (AI video)** for *Animation & character designs*. Keep a text AI (Claude, Codex, Gemini API or Ollama) for *Ideas & script*: it also writes the shot prompts. The *Image model* and *Video model* boxes take OpenArt model ids (defaults `nano-banana-2` and `kling-3-omni`; `openart model list` and `openart model cost` show what your account offers and what it charges). The stage's Model box is not used.
3. With **Save OpenArt credits** off, choose **Stills + AI video clips** or **Stills only (Ken Burns, cheaper)** and seconds per shot (custom default 6, range 3–20). Saving mode uses its longer still-only defaults described above. A 10-minute voiceover at 6 s is 100 shots; each generated shot can cost credits, so Make the video asks before it starts (Auto does not).
4. **OpenArt parallel shots** in Setup controls simultaneous scenes (default 3, range 1-4; 1 runs sequentially). Each scene generates its still before its clip. Local FFmpeg assembly stays sequential and preserves scene order. This reduces waiting when OpenArt accepts simultaneous requests; it does not reduce credits per scene. If the account limits concurrent requests, lower this setting. Changing it preserves the existing shot cache.

**Stop** terminates every active local OpenArt command and prevents new requests. OpenArt may still complete or charge for work already submitted on its servers. On a generation error, no new scenes are scheduled; other in-flight requests are allowed to finish and save their media for resume. Press Auto and choose Continue after resolving the error.

What happens: the voiceover is split into equal shots, the narration spoken in each one is estimated from its position in the script, and the script AI returns one JSON image prompt and one camera-motion prompt per shot. Each still is generated with `openart generate image` at the video's aspect ratio and, in the clips mode, brought to life with `openart generate video --image`; model-specific flags the CLI rejects (`--aspect-ratio`, `--resolution`, `--timeout`) are dropped automatically. Clips are trimmed or slowed to fit each scene (or generated as continuous zoom/pan from stills), blended with short dissolves, and mixed with the voiceover (and your own music track at low volume, if chosen). Everything is saved under `work\<project>\openart\`; a second run after a stop, a failure or an empty credit balance reuses the plan and the finished shots. Thumbnail and Upload work as usual. Not available: music by mood, burned-in captions, character styles from the kit (Suggest character styles makes 4 OpenArt stills instead), the interactive agent, and offline mode.

## YouTube setup (once)
Go to **Upload → YouTube setup** and follow the steps there. You create a free Google Cloud project, enable the *YouTube Data API v3*, create an OAuth **Desktop app** client, and choose its `client_secret.json`. Then click **Connect**. Until Google verifies your app, YouTube may force uploads to private; you can make them public in YouTube Studio.

**Already have a `token.json`?** Put it in `.\youtube\token.json` and restart the app. It needs the `youtube.upload` scope and must contain `refresh_token`, `client_id`, `client_secret` and `token_uri`. If uploads fail, put your `client_secret.json` in the same folder, delete `token.json`, and click **Connect** again. Never commit either file (`.gitignore` already excludes them).

## Troubleshooting
- **Qwen prints SoX or `flash-attn` warnings.** These are Python voice dependencies, not Ollama. Inspect the `QWEN device`/completion lines and exit status: an import warning alone does not establish failure or CPU fallback. Python `flash-attn` and Ollama Flash Attention are separate.
- **Scene audit still needs review.** Inspect `build/scene_audit/report.json` and its images. Rejected repairs are rolled back; unresolved generated-scene warnings stop export. Human review is still required.
- **Browser download stalls or a headless-shell executable is missing.** Reapply the kit patcher and use installed Chrome/Edge. The renderer launches the full bundled Chromium executable it checked, rather than assuming a separate headless-shell package. Download or antivirus failures can leave an incomplete browser cache.
- **faster-whisper / `av` fails to install.** Use the Python selected by the installer in `python.txt` and `.venv`, rather than an unrelated system Python. The project is verified with Python 3.12; dependency wheel availability varies by interpreter/platform.
- **Setup shows "Animation kit: missing"** when the app is started from the repo folder: update to the latest version. Run the installer beside the launcher to provision the local studio kit.
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

AI CLI logins are installation-scoped (`.claude`, `.codex`, `.runtime/home/.gemini`); sign in again from Setup. Existing personal AI configurations are not moved or overwritten. Studio cache/CLI path changes are process-local. Ollama uses its own installed service/model storage; optional Ollama server environment settings are separate and apply to that server globally. Shared Python, Node, Git, FFmpeg and installed browsers may be used; studio dependencies/caches remain local. Secrets and generated content are gitignored.

Gemini installation explicitly permits only `@github/keytar` install scripts for that npm command (`--allow-scripts=@github/keytar`), without changing your Windows or user npm configuration. Its deprecation warning may still appear because it is an upstream dependency. A completed package installation with exit code zero is treated as success; use Setup to sign in afterwards.

If Microsoft speech returns no audio for a passage, other passages finish first. Failed passages then recover sequentially in smaller cached pieces using the same voice. Completed audio is preserved; if the service is still unavailable, Auto can resume later without repeating finished passages.

Codex animation on Windows uses the standalone CLI from Setup, an explicitly trusted studio workspace and a Windows sandbox (unelevated when no sandbox is configured; existing selections are preserved). Network access is enabled for the renderer's localhost server and model downloads while filesystem writes remain workspace-scoped. A pass reporting policy/permission failures stops the pipeline immediately rather than proceeding through all passes without producing a video.

For Codex video generation, the writable workspace is the current project. The app launches the installed renderer, renders real contact sheets for the agent to inspect, and performs the final render, mix and audio/video-duration checks. The agent cannot change the installed renderer or engine outside its project. A pass is checkpointed only after explicit visual approval; changed project files invalidate the checkpoint. This avoids Chromium spawn EPERM inside the Windows sandbox without granting the agent unrestricted access.

Visual QC allows three repair rounds plus a separate verification render. Pending QC is saved after each repair, so Auto resumes visual inspection without rebuilding the current pass. Approval is accepted only when the agent did not change project files after the reviewed images were rendered.

## Faster offline animation

Automatic Ollama animation uses direct requests to the local API, one scene at a time,
instead of running a general-purpose CLI agent. The app creates the project, aligns the
voiceover, builds the beat sheet, saves scene modules, checks JavaScript syntax and scene
runtime errors, and runs the installed renderer and audio mixer. Claude Code is not
required for this automatic path. The interactive agent path is unchanged.

Requests use 16K context and GPT-OSS medium reasoning for animation and repairs; script
requests retain low reasoning. A whole-video storyboard is planned first and checked for
varied framing, concrete actions and different start/end states. Failed scenes get up to
three attempts. Character prompts use the existing 2D rig. Completed
scene hashes are saved in `build/local_animation.json`, so unchanged input and completed
code are reused after a stopped run. Changed narration, visual choices or code invalidate
the affected checkpoints. Contact sheets still need human visual review: the text-only
model cannot approve images. Runtime validation does not establish visual quality.

Approved/manual scenes are protected: changes to aspect ratio, style or look notes stop
reuse and preserve the previous config and source until the scenes are reviewed/reframed
(or a new project is used). Performance reports cover setup, alignment and storyboard
failures as well as generation/export, including status, stage and failure/cancellation.
Ollama streaming has a cancellation monitor that can interrupt stalled headers/token reads.

Optional `.env` settings: `OLLAMA_THINKING=low`, `OLLAMA_ANIMATION_THINKING=medium`,
`OLLAMA_REPAIR_THINKING=medium`, `OLLAMA_SCENE_CONTEXT=16384`.
`build/ollama_performance.json` records request token counts, load/generation durations,
and total elapsed time for the scene workflow. The selected model is unloaded before
rendering; the script model is unloaded before Qwen voice generation to free GPU memory.

For a 16 GB NVIDIA GPU, test user environment variables `OLLAMA_FLASH_ATTENTION=1`,
`OLLAMA_KV_CACHE_TYPE=q8_0`, and `OLLAMA_NUM_PARALLEL=1`. Quit and reopen Ollama after
setting them. These are Ollama server settings; placing them only in the studio's `.env`
does not reconfigure an already running server. Cache quantization reduces memory usage
and may affect output; compare a successful video before assuming a speed improvement.

## Check and improve offline scenes

Restart the studio after updating. Every automatic offline animation now runs the local
scene checker before final export. It draws every frame for runtime checks and captures up
to eight snapshots per shot for motion/detail checks, without counting captions. It aligns
frames for translation/zoom before measuring residual motion, reducing camera-only false passes.
Flagged scenes get one targeted local-model repair attempt, Node syntax checking and another
real browser audit. A replacement must clear all audit warnings, residual motion >=0.008 and
color spread >=9, not merely improve slightly. Rejected changes are rolled back. Remaining
warnings on generated scenes stop repair/export for review; approved/manual scenes stay protected
from quality-heuristic rewrites. Originals are saved under `build/scene_audit/backups/`.

For existing offline projects, double-click `Check-Offline-Animations.cmd`, or run:

```powershell
.\.venv\Scripts\python.exe app\check_offline_scenes.py --all --repair
.\.venv\Scripts\python.exe app\check_offline_scenes.py --project projects/my-video --repair --export
```

`--all` includes projects with a `build/local_animation.json` checkpoint; underscore-prefixed
test projects are excluded. Without `--repair` the command only audits. `--export` explicitly
rerenders and remixes the final video; repairs alone do not change an already exported MP4.
Use `--model` to override the project's recorded model. No cloud services are used.

Reports and up to eight preview images per shot are saved under `build/scene_audit/`. Scenes marked
`manual` in the checkpoint are checked but never automatically rewritten. This preserves
hand-directed and user-approved work. The checker cannot judge beauty, narrative relevance,
physical contact or animation quality as a human can; camera motion may pass its pixel test.
Reports always retain `visually_approved: false`. Inspect the images/video yourself.

## Validation

Run checks from the project root:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s app -p "test_*.py"
node --test app\video_encoder.test.mjs app\offline_motion.test.mjs
git diff --check
```

Latest validation: **115 Python tests and 6 Node tests pass**. A real approved-project audit checked 1,624 frames and 120 snapshots with no runtime failures or visual flags. Tests include stalled-stream cancellation, repair rollback/thresholds, approved-scene protection and early failure reporting. These checks do not guarantee visual quality for every new generation.

## License

Copyright (C) 2026 j0p3s

This project is free software: you can redistribute it and/or modify it under the terms of the GNU General Public License as published by the Free Software Foundation, version 3. It is distributed in the hope that it will be useful, but WITHOUT ANY WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See [LICENSE](LICENSE) for the full text.

The license covers the studio's own code (`app/` and the `.cmd` scripts). The animation kit (`GrowKaz_Stickman.plugin`) is third-party, is not included here and stays under its author's terms. Packages installed by the installer (for example edge-tts, piper-tts, faster-whisper) keep their own licenses.
