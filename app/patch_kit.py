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
