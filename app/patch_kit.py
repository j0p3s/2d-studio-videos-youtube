"""patch_kit.py - make the GrowKaz studio work without Playwright's bundled Chromium.

On some PCs antivirus freezes `npx playwright install chromium` while it unpacks chrome.dll.
This patch (safe to run many times) makes:
  - render.mjs fall back to installed Google Chrome or Microsoft Edge when the bundled
    Chromium is missing (override with env PW_CHANNEL=chrome|msedge),
  - tools/doctor.py count Chrome/Edge as a valid browser, so its --install step does
    not retry the download that freezes.

Usage:  python patch_kit.py <path to growkaz-stickman-studio>
"""
import sys
from pathlib import Path

MARK = "/* 2d-studio: browser fallback */"
studio = Path(sys.argv[1] if len(sys.argv) > 1 else ".")

render = studio / "render.mjs"
src = render.read_text(encoding="utf-8")
if MARK not in src:
    old = "const LAUNCH = { args: ["
    if old not in src:
        sys.exit("render.mjs: launch line not found - plugin changed, patch not applied")
    new = (MARK + " const _bundledOk = (() => { try { return fs.existsSync(chromium.executablePath()); } catch { return false; } })();\n"
           "const _channel = process.env.PW_CHANNEL || (_bundledOk ? null : "
           "(fs.existsSync('C:/Program Files/Google/Chrome/Application/chrome.exe') || "
           "fs.existsSync('C:/Program Files (x86)/Google/Chrome/Application/chrome.exe') ? 'chrome' : 'msedge'));\n"
           "const LAUNCH = { ...(_channel ? { channel: _channel } : {}), args: [")
    render.write_text(src.replace(old, new, 1), encoding="utf-8")
    print("patched render.mjs")
else:
    print("render.mjs already patched")

# frame progress file for the GUI's progress bar (build/render_progress.json)
PMARK = "/* 2d-studio: progress file */"
src = render.read_text(encoding="utf-8")
if PMARK not in src:
    old = "ff.stdin.once('drain', r)); done++;"
    if old not in src:
        print("render.mjs: frame loop not found - progress file not added")
    else:
        new = (old + " " + PMARK + " if (done % 12 === 0 || done === f1 - f0) { try { fs.writeFileSync("
               "path.join(BUILD, 'render_progress.json'), JSON.stringify({ done, total: f1 - f0, "
               "full: !(args.from || args.to), t0, t: Date.now() })); } catch {} }")
        render.write_text(src.replace(old, new, 1), encoding="utf-8")
        print("patched render.mjs (progress file)")
else:
    print("render.mjs progress file already patched")

# Windows: a failed render left Chrome running, so node never exited and sat there until an
# outer `timeout` killed it (7 minutes lost per failure). Exit as soon as the error is printed.
EMARK = "/* 2d-studio: exit on failure */"
src = render.read_text(encoding="utf-8")
if EMARK not in src:
    old = "process.exitCode = 1; }"
    if old not in src:
        print("render.mjs: failure handler not found - exit patch not applied")
    else:
        render.write_text(src.replace(old, "process.exitCode = 1; " + EMARK + " process.exit(1); }", 1),
                          encoding="utf-8")
        print("patched render.mjs (exit on failure)")
else:
    print("render.mjs exit-on-failure already patched")

# Windows: deleting build/stills (or sheets, parts) fails with EPERM when any shell has that
# folder as its working directory. Empty the folder instead of removing it.
CMARK = "/* 2d-studio: empty dirs */"
src = render.read_text(encoding="utf-8")
if CMARK not in src:
    import re
    pat = re.compile(r"fs\.rmSync\((\w+), \{ recursive: true, force: true \}\); fs\.mkdirSync\(\1, \{ recursive: true \}\);")
    if not pat.search(src):
        print("render.mjs: folder reset not found - empty-dirs patch not applied")
    else:
        src = pat.sub(r"_emptyDir(\1);", src)
        helper = (CMARK + " const _emptyDir = d => { fs.mkdirSync(d, { recursive: true }); "
                  "for (const f of fs.readdirSync(d)) fs.rmSync(path.join(d, f), { recursive: true, force: true }); };\n")
        i = src.index("if (!args.project)")
        render.write_text(src[:i] + helper + src[i:], encoding="utf-8")
        print("patched render.mjs (empty dirs)")
else:
    print("render.mjs empty-dirs already patched")

# GPU where it helps, CPU where it belongs:
#  - encoding: NVIDIA NVENC (h264_nvenc) when a one-frame probe works and the parallel encodes fit
#    the GeForce limit of 8 sessions; otherwise libx264 on the CPU exactly as before.
#    Override with --encoder cpu|gpu or env STUDIO_ENCODER=cpu|gpu.
#  - drawing: on Windows ask Chrome for the high-performance GPU, so laptops don't drop to the
#    integrated one. --gl swiftshader still forces CPU drawing.
#  - capture: video frames come out of Chrome as JPEG instead of PNG (see below).
#  Frame stepping, scene logic and the parallel workers stay on the CPU.
#  Measured at 1080p, 480 frames: PNG + x264 ~72 s -> JPEG + NVENC 15.6 s (4.6x).
GMARK = "/* 2d-studio: gpu encode */"
src = render.read_text(encoding="utf-8")
if GMARK not in src:
    reps = [
        ("import { spawn } from 'node:child_process';",
         "import { spawn, spawnSync } from 'node:child_process';"),
        ("async function renderVideo() {",
         GMARK + " const _encPref = String(args.encoder || process.env.STUDIO_ENCODER || 'auto');\n"
         "const _nvencOk = _encPref !== 'cpu' && (() => { try { return spawnSync('ffmpeg', ['-v', 'error', '-f', 'lavfi', "
         "'-i', 'color=c=black:s=256x256:d=0.1', '-frames:v', '1', '-c:v', 'h264_nvenc', '-f', 'null', '-'], "
         "{ timeout: 20000, windowsHide: true }).status === 0; } catch { return false; } })();\n"
         "const _useGpuEnc = W => _nvencOk && (W <= 8 || _encPref === 'gpu');\n"
         "const _encArgs = W => _useGpuEnc(W)\n"
         "  ? ['-c:v', 'h264_nvenc', '-preset', 'p5', '-tune', 'hq', '-rc', 'vbr', '-cq', String(args.crf ? +args.crf + 1 : 19), '-b:v', '0']\n"
         "  : ['-c:v', 'libx264', '-preset', args.preset || 'medium', '-crf', String(args.crf || 18)];\n"
         "async function renderVideo() {"),
        ("'-c:v', 'libx264', '-preset', args.preset || 'medium', '-crf', String(args.crf || 18),",
         "..._encArgs(W),"),
        ("with ${W} worker(s)…`",
         "with ${W} worker(s), encoder ${_useGpuEnc(W) ? 'GPU (NVENC)' : 'CPU (x264)'}…`"),
        # Video frames are captured as JPEG (quality 94) instead of PNG: PNG compression in Chrome was
        # the real bottleneck (4.4x slower at 1080p) and the result is visually identical
        # (SSIM 0.993, PSNR 49 dB). Stills, contact sheets and style grids stay PNG; --format still overrides.
        ("const FORMAT = args.format === 'jpeg' ? 'jpeg' : 'png';",
         "const FORMAT = args.format ? (args.format === 'jpeg' ? 'jpeg' : 'png') : "
         "(args.sheet || args.stills || args.styles ? 'png' : 'jpeg');"),
        ("...(gl === 'gpu' ? ['--enable-gpu', '--use-angle=default'] : [])",
         "...(gl === 'gpu' ? ['--enable-gpu', '--use-angle=default'] : []), "
         "...(gl !== 'swiftshader' && process.platform === 'win32' ? ['--force_high_performance_gpu'] : [])"),
    ]
    missing = [o for o, _ in reps if src.count(o) != 1]
    if missing:
        print("render.mjs: GPU patch not applied, not found:", ", ".join(m[:40] for m in missing))
    else:
        for o, n in reps:
            src = src.replace(o, n, 1)
        render.write_text(src, encoding="utf-8")
        print("patched render.mjs (GPU encode, high-performance GPU, JPEG frame capture)")
else:
    print("render.mjs GPU patch already applied")

doctor = studio / "tools" / "doctor.py"
src = doctor.read_text(encoding="utf-8")
if "2d-studio: browser fallback" not in src:
    old = 'ok("Chromium for Playwright", chrom,'
    if old not in src:
        sys.exit("doctor.py: chromium check not found - patch not applied")
    new = ('# 2d-studio: browser fallback - installed Chrome/Edge also works\n'
           'if not chrom:\n'
           '    _sys = [r"C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe",\n'
           '            r"C:\\Program Files (x86)\\Google\\Chrome\\Application\\chrome.exe",\n'
           '            r"C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe",\n'
           '            r"C:\\Program Files\\Microsoft\\Edge\\Application\\msedge.exe"]\n'
           '    chrom = any(os.path.exists(p) for p in _sys)\n'
           + old)
    doctor.write_text(src.replace(old, new, 1), encoding="utf-8")
    print("patched tools/doctor.py")
else:
    print("doctor.py already patched")

# keep tools/verify_kit.py happy: refresh the expected hashes of the two patched files
import hashlib, re
vk = studio / "tools" / "verify_kit.py"
vsrc = vk.read_text(encoding="utf-8")
for rel in ["render.mjs", "tools/doctor.py"]:
    data = (studio / rel).read_bytes().replace(b"\r\n", b"\n").strip()
    h = hashlib.sha256(data).hexdigest()[:16]
    vsrc, n = re.subn(r'("%s":\s*")[0-9a-f]{16}(")' % re.escape(rel), r"\g<1>%s\g<2>" % h, vsrc)
    if not n:
        print(f"verify_kit.py: no entry for {rel}")
vk.write_text(vsrc, encoding="utf-8")
print("verify_kit.py hashes updated")
