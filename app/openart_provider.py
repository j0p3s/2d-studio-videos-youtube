"""OpenArt (openart.ai) image and video generation through the official OpenArt CLI.

OpenArt has no public key-based API: its supported programmatic route is the `openart` CLI
(github.com/OpenArt-AI/cli). It signs in once through the browser (OAuth, no key to paste) and
spends the account's normal credits. The studio downloads the release binary into its own
.tools folder and the login lands in the studio's .runtime/home, so nothing touches the user's
Windows profile. Every call uses --json; results are downloaded by the CLI itself (-o).

The studio uses it as an animation provider: one still per shot (generate image) and,
optionally, that still brought to life (generate video --image), then shots_video cuts the
clips to the narration with FFmpeg.
"""
import json
import os
import platform
import re
import shutil
import stat
import tarfile
import time
import urllib.request
import zipfile
from pathlib import Path

OPENART = "OpenArt (AI video)"
RELEASES_API = "https://api.github.com/repos/OpenArt-AI/cli/releases/latest"
DEFAULT_IMAGE_MODEL = "nano-banana-2"
DEFAULT_VIDEO_MODEL = "kling-3-omni"
IMAGE_TIMEOUT, VIDEO_TIMEOUT = "5m", "20m"   # --timeout values; the CLI's default is 5 minutes
# Flags the README calls model-specific. If the installed CLI rejects one, the call is retried
# without it instead of failing the whole video.
OPTIONAL_FLAGS = ("--aspect-ratio", "--resolution", "--duration", "--timeout")
MEDIA = {"image": (".png", ".jpg", ".jpeg", ".webp"), "video": (".mp4", ".webm", ".mov")}


def executable(env=None):
    """The openart binary: the studio's .tools folder (on PATH) first, then the official
    installer's folder under the (studio-scoped) LOCALAPPDATA, then the rest of PATH."""
    env = os.environ if env is None else env
    exe = shutil.which("openart", path=env.get("PATH"))
    if exe:
        return exe
    for base in filter(None, (env.get("LOCALAPPDATA"), env.get("HOME"), env.get("USERPROFILE"))):
        for candidate in (Path(base) / "Programs" / "openart" / "bin" / "openart.exe",
                          Path(base) / ".local" / "bin" / "openart"):
            if candidate.is_file():
                return str(candidate)
    return None


def command(env, *args):
    exe = executable(env)
    if not exe:
        raise RuntimeError("OpenArt CLI not found. Go to Setup → Install OpenArt, then Sign in: OpenArt.")
    return [exe, *args]


def release_asset_name(system=None, machine=None):
    system = (system or platform.system()).lower()
    machine = (machine or platform.machine()).lower()
    arch = "arm64" if machine in ("arm64", "aarch64") else "amd64"
    os_name = {"windows": "windows", "darwin": "darwin", "linux": "linux"}.get(system)
    if not os_name:
        raise RuntimeError(f"No OpenArt CLI build for {system}.")
    return re.compile(rf"^openart_.*_{os_name}_{arch}\.(zip|tar\.gz)$")


def install(tools_dir, log=print, *, system=None, machine=None, fetch=None):
    """Download the latest release binary into tools_dir (the studio's .tools, which is on PATH).
    No installer script runs, so the user's PATH and profile stay untouched."""
    tools_dir = Path(tools_dir)
    tools_dir.mkdir(parents=True, exist_ok=True)
    fetch = fetch or _fetch
    release = json.loads(fetch(RELEASES_API).decode("utf-8"))
    pattern = release_asset_name(system, machine)
    asset = next((a for a in release.get("assets", []) if pattern.match(a.get("name", ""))), None)
    if not asset:
        raise RuntimeError(f"OpenArt release {release.get('tag_name', '?')} has no build for this computer.")
    log(f"> downloading OpenArt CLI {release.get('tag_name', '')} ({asset['name']})")
    archive = tools_dir / asset["name"]
    archive.write_bytes(fetch(asset["browser_download_url"]))
    exe_name = "openart.exe" if asset["name"].endswith(".zip") and "windows" in asset["name"] else "openart"
    target = tools_dir / exe_name
    try:
        if asset["name"].endswith(".zip"):
            with zipfile.ZipFile(archive) as z:
                member = next(m for m in z.namelist() if m.rsplit("/", 1)[-1] == exe_name)
                target.write_bytes(z.read(member))
        else:
            with tarfile.open(archive) as t:
                member = next(m for m in t.getmembers() if m.name.rsplit("/", 1)[-1] == exe_name)
                target.write_bytes(t.extractfile(member).read())
    except StopIteration:
        raise RuntimeError(f"{asset['name']} does not contain {exe_name}.")
    finally:
        archive.unlink(missing_ok=True)
    if os.name != "nt":
        target.chmod(target.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    log(f"OpenArt CLI installed: {target}")
    return target


def _fetch(url):
    with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "2d-animation-studio"}),
                                timeout=120) as response:
        return response.read()


def json_output(text):
    """The JSON object or array in a command's output (progress lines may surround it)."""
    text = text or ""
    starts = [i for i in (text.find("{"), text.find("[")) if i >= 0]
    if not starts:
        raise ValueError("no JSON in the OpenArt CLI output")
    a = min(starts)
    closer = "}" if text[a] == "{" else "]"
    b = text.rfind(closer)
    if b <= a:
        raise ValueError("no JSON in the OpenArt CLI output")
    return json.loads(text[a:b + 1])


def failure(output, what):
    tail = (output or "").strip()[-700:]
    low = tail.lower()
    if "login" in low or "unauthorized" in low or "not authenticated" in low or "credential" in low:
        return RuntimeError(f"OpenArt is not signed in ({what}). Go to Setup → Sign in: OpenArt.\n{tail}")
    if "credit" in low and ("insufficient" in low or "not enough" in low or "balance" in low):
        return RuntimeError(f"OpenArt has no credits left ({what}). Top up at openart.ai, then press Auto or "
                            f"Make the video again: finished shots are kept.\n{tail}")
    return RuntimeError(f"OpenArt CLI failed ({what}):\n{tail}")


def account(run, env):
    """Who is signed in, the plan and the credit balance (openart account --json)."""
    rc, output = run(command(env, "account", "--json"))
    if rc:
        raise failure(output, "account")
    try:
        return json_output(output)
    except ValueError:
        return {"raw": output.strip()[-300:]}


def models(run, env):
    rc, output = run(command(env, "model", "list", "--json"))
    if rc:
        raise failure(output, "model list")
    data = json_output(output)
    return data if isinstance(data, list) else data.get("items") or data.get("data") or data.get("models") or []


def generate(run, env, kind, prompt, out_dir, *, model, image=None, aspect=None, resolution=None,
             duration=None, timeout=None):
    """One image or video, downloaded by the CLI into out_dir. Returns the file."""
    if kind not in MEDIA:
        raise ValueError(kind)
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    model = (model or "").strip() or (DEFAULT_IMAGE_MODEL if kind == "image" else DEFAULT_VIDEO_MODEL)
    # Kling Omni uses quality tiers rather than pixel heights. Keep the project's
    # output resolution unchanged; shots_video still scales the final frames.
    if kind == "video" and model == "kling-3-omni":
        resolution = {"720p": "std", "1080p": "pro", "2160p": "4k"}.get(resolution, resolution)
    base = command(env, "generate", kind, prompt, "--model", model, "--json", "-o", str(out_dir))
    if image:
        base += ["--image", str(image)]
    optional = []
    for flag, value in (("--aspect-ratio", aspect), ("--resolution", resolution), ("--duration", duration),
                        ("--timeout", timeout or (IMAGE_TIMEOUT if kind == "image" else VIDEO_TIMEOUT))):
        if value not in (None, ""):
            optional.append((flag, str(value)))
    t0 = time.time()
    while True:
        cmd = base + [part for pair in optional for part in pair]
        rc, output = run(cmd)
        if not rc:
            break
        rejected = next((flag for flag, _ in optional if _rejected_flag(output, flag)), None)
        if rejected is None:
            raise failure(output, f"generate {kind}, model {model}")
        optional = [pair for pair in optional if pair[0] != rejected]   # this CLI/model has no such flag
    files = [p for p in out_dir.iterdir() if p.is_file() and p.stat().st_mtime >= t0 - 1
             and p.suffix.lower() in MEDIA[kind]]
    if files:
        return max(files, key=lambda p: p.stat().st_mtime)
    url = result_url(output)
    if not url:
        raise RuntimeError(f"OpenArt finished but no {kind} file or URL was returned:\n{(output or '')[-500:]}")
    return download(url, out_dir / ("result" + Path(url.split("?")[0]).suffix))


def _rejected_flag(output, flag):
    low = (output or "").lower()
    # Model schema errors name the field without the leading dashes.
    if re.search(rf"\b{re.escape(flag.removeprefix('--'))}:\s*invalid option\b", low):
        return True
    return flag in low and any(word in low for word in ("unknown flag", "unknown shorthand", "not defined",
                                                        "unrecognized", "unsupported", "does not accept",
                                                        "not supported", "invalid argument"))


def result_url(output):
    try:
        data = json_output(output)
    except ValueError:
        m = re.search(r"https?://\S+\.(?:png|jpe?g|webp|mp4|webm)\b\S*", output or "")
        return m.group(0) if m else None
    found = []

    def walk(node):
        if isinstance(node, dict):
            for key, value in node.items():
                if key in ("url", "video_url", "image_url", "output_url") and isinstance(value, str):
                    found.append(value)
                else:
                    walk(value)
        elif isinstance(node, list):
            for item in node:
                walk(item)
    walk(data)
    return next((u for u in found if u.startswith("http")), None)


def download(url, dest):
    dest = Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(_fetch(url))
    return dest
