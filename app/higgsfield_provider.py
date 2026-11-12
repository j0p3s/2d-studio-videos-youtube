"""Higgsfield (higgsfield.ai) image and video generation through its cloud API.

Higgsfield is an animation provider, not a script writer: the studio asks it for one still per
shot (the "Soul" text-to-image model) and, optionally, animates each still with the "DoP"
image-to-video model. The clips are then cut to the voiceover by FFmpeg (see higgsfield_video).

The API contract below is the one the official SDKs use (higgsfield-client on PyPI,
@higgsfield/client on npm): every generation is a POST to its endpoint that answers with a
request id, then GET /requests/<id>/status is polled until the status is terminal. The key
comes from the studio's .env file as HIGGSFIELD_API_KEY=key-id:key-secret (the SDK names
HF_KEY, or HF_API_KEY + HF_API_SECRET, are accepted too) and travels in a header, never in a URL.
"""
import json
import mimetypes
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

HIGGSFIELD = "Higgsfield (AI video)"
BASE_URL = "https://api.higgsfield.ai"
TEXT_TO_IMAGE = "/v1/text2image/soul"
IMAGE_TO_VIDEO = "/v1/image2video/dop"
MOTIONS = "/v1/motions"
UPLOAD_URL = "/files/generate-upload-url"
CONSOLE_URL = "https://cloud.higgsfield.ai"

VIDEO_MODELS = ("dop-turbo", "dop-lite", "dop-standard")   # turbo: fast, lite: cheapest, standard: best
DEFAULT_VIDEO_MODEL = "dop-turbo"
IMAGE_SIZES = {"16:9": "2048x1152", "9:16": "1152x2048", "1:1": "1536x1536"}
IMAGE_QUALITIES = ("1080p", "720p")
DONE = ("completed", "failed", "nsfw", "canceled")
RETRY_CODES = (408, 429, 500, 502, 503, 504)

REQUEST_TIMEOUT = 120     # one HTTP round trip; generation itself is polled
RETRY_DELAY = 2.0         # multiplied by the attempt number
POLL_SECONDS = 2.0
WAIT_LIMIT = 900          # a clip takes a few minutes at most; longer means something is stuck


def credentials(env=None):
    """'key-id:key-secret' from the studio's .env (loaded into env) or the SDK's variables."""
    env = os.environ if env is None else env
    key = env.get("HIGGSFIELD_API_KEY") or env.get("HF_KEY")
    if not key and env.get("HF_API_KEY") and env.get("HF_API_SECRET"):
        key = env["HF_API_KEY"] + ":" + env["HF_API_SECRET"]
    key = (key or "").strip()
    if not key:
        raise RuntimeError("Higgsfield API key not found. Create one at cloud.higgsfield.ai, put "
                           "HIGGSFIELD_API_KEY=key-id:key-secret in the .env file in the studio folder, "
                           "then restart the app.")
    if ":" not in key:
        raise RuntimeError("HIGGSFIELD_API_KEY must be the key id and secret joined with a colon: "
                           "HIGGSFIELD_API_KEY=key-id:key-secret")
    return key


def configured(env=None):
    try:
        credentials(env)
        return True
    except RuntimeError:
        return False


def base_url(env=None):
    env = os.environ if env is None else env
    return (env.get("HIGGSFIELD_BASE_URL") or BASE_URL).rstrip("/")


def _error_detail(body):
    try:
        data = json.loads(body)
    except ValueError:
        return body.strip()[:500]
    if isinstance(data, dict):
        for key in ("detail", "details", "message", "error"):
            if data.get(key):
                value = data[key]
                return value if isinstance(value, str) else json.dumps(value)[:500]
    return body.strip()[:500]


def _request(method, url, env, payload=None, *, auth=True, timeout=REQUEST_TIMEOUT, retries=3,
             raw=None, content_type=None):
    """One JSON call to the API with the SDK's retry policy (408/429/5xx, growing delay)."""
    if url.startswith("/"):
        url = base_url(env) + url
    headers = {"User-Agent": "2d-animation-studio"}
    if auth:
        headers["Authorization"] = "Key " + credentials(env)
    data = None
    if raw is not None:
        data, headers["Content-Type"] = raw, content_type or "application/octet-stream"
    elif payload is not None:
        data, headers["Content-Type"] = json.dumps(payload).encode("utf-8"), "application/json"
    for attempt in range(1, retries + 1):
        request = urllib.request.Request(url, data=data, headers=headers, method=method)
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                body = response.read().decode("utf-8", "replace")
            return json.loads(body) if body.strip() else {}
        except urllib.error.HTTPError as e:
            detail = _error_detail(e.read().decode("utf-8", "replace"))
            if e.code in RETRY_CODES and attempt < retries:
                time.sleep(RETRY_DELAY * attempt)
                continue
            if e.code in (401, 403):
                raise RuntimeError(f"Higgsfield rejected the API key ({e.code}): {detail or 'check '}"
                                   f"HIGGSFIELD_API_KEY in .env (key-id:key-secret from cloud.higgsfield.ai).")
            if e.code == 402:
                raise RuntimeError(f"Higgsfield has no credits left for this request (402): {detail}. "
                                   "Top up at cloud.higgsfield.ai, then press Auto or Make the video again: "
                                   "finished clips are kept.")
            raise RuntimeError(f"Higgsfield API failed ({e.code} on {method} {urllib.parse.urlsplit(url).path}): {detail}")
        except (TimeoutError, urllib.error.URLError) as e:
            if attempt < retries:
                time.sleep(RETRY_DELAY * attempt)
                continue
            raise RuntimeError(f"Higgsfield API could not be reached ({method} {urllib.parse.urlsplit(url).path}): "
                               f"{getattr(e, 'reason', e)}")
    raise RuntimeError("Higgsfield API request gave up")   # unreachable: the loop returns or raises


def submit(endpoint, arguments, env=None):
    """Queue one generation. Returns the API's receipt: request_id, status_url, cancel_url."""
    env = os.environ if env is None else env
    receipt = _request("POST", endpoint, env, arguments)
    if not isinstance(receipt, dict) or not receipt.get("request_id"):
        raise RuntimeError(f"Higgsfield did not queue the request ({endpoint}): {json.dumps(receipt)[:300]}")
    receipt.setdefault("status_url", f"{base_url(env)}/requests/{receipt['request_id']}/status")
    receipt.setdefault("cancel_url", f"{base_url(env)}/requests/{receipt['request_id']}/cancel")
    return receipt


def wait(receipt, env=None, on_status=None, check=None, poll=None, limit=WAIT_LIMIT):
    """Poll a receipt until it is done. check() may raise to stop (the request is then cancelled)."""
    env = os.environ if env is None else env
    poll = POLL_SECONDS if poll is None else poll
    t0 = time.time()
    last = None
    while True:
        if check:
            try:
                check()
            except BaseException:
                try:
                    _request("POST", receipt["cancel_url"], env, retries=1)
                except RuntimeError:
                    pass   # a running request cannot be cancelled; it is still billed
                raise
        body = _request("GET", receipt["status_url"], env)
        status = str(body.get("status", "")).lower()
        if status != last and on_status:
            on_status(status)
        last = status
        if status in DONE:
            break
        if time.time() - t0 > limit:
            raise RuntimeError(f"Higgsfield request {receipt.get('request_id')} is still {status or 'unknown'} "
                               f"after {int(limit)} s. Check cloud.higgsfield.ai and try again.")
        time.sleep(poll)
    if status == "completed":
        return body
    if status == "nsfw":
        raise RuntimeError("Higgsfield refused this prompt as unsafe (NSFW), the credits were refunded. "
                           "Soften the look notes or the script wording and try again.")
    if status == "canceled":
        raise RuntimeError("Higgsfield request was cancelled.")
    detail = body.get("error") or body.get("detail") or body.get("message") or ""
    raise RuntimeError("Higgsfield generation failed" + (f": {detail}" if detail else " (credits are refunded)."))


def generate(endpoint, arguments, env=None, on_status=None, check=None):
    return wait(submit(endpoint, arguments, env), env, on_status, check)


def first_url(body, kind):
    """The media URL in a completed status body: images[0].url or video.url."""
    if kind == "image":
        items = body.get("images") or []
        url = items[0].get("url") if items and isinstance(items[0], dict) else None
    else:
        video = body.get("video") or {}
        url = video.get("url") if isinstance(video, dict) else None
    if not url:
        raise RuntimeError(f"Higgsfield answered without a {kind} URL: {json.dumps(body)[:300]}")
    return url


def image_size(aspect):
    return IMAGE_SIZES.get(aspect, IMAGE_SIZES["16:9"])


def video_model(name):
    name = (name or "").strip().lower() or DEFAULT_VIDEO_MODEL
    if name not in VIDEO_MODELS:
        raise RuntimeError(f"Unknown Higgsfield video model '{name}'. Use one of: {', '.join(VIDEO_MODELS)} "
                           "(the Model box in Setup, blank = dop-turbo).")
    return name


def text_to_image(prompt, aspect="16:9", env=None, *, quality="1080p", seed=None, on_status=None, check=None):
    """One Soul still. Returns its URL."""
    arguments = {"prompt": prompt, "width_and_height": image_size(aspect),
                 "quality": quality if quality in IMAGE_QUALITIES else "1080p", "batch_size": 1,
                 "enhance_prompt": True}
    if seed is not None:
        arguments["seed"] = int(seed)
    return first_url(generate(TEXT_TO_IMAGE, arguments, env, on_status, check), "image")


def image_to_video(image_url, prompt, env=None, *, model="", seed=None, on_status=None, check=None):
    """Animate one still with DoP. Returns the clip URL (a few seconds of video)."""
    arguments = {"model": video_model(model), "prompt": prompt,
                 "input_images": [{"type": "image_url", "image_url": image_url}], "enhance_prompt": True}
    if seed is not None:
        arguments["seed"] = int(seed)
    return first_url(generate(IMAGE_TO_VIDEO, arguments, env, on_status, check), "video")


def upload_file(path, env=None):
    """Upload a local file (e.g. a reference still) and return its public URL."""
    env = os.environ if env is None else env
    path = Path(path)
    content_type = mimetypes.guess_type(str(path))[0] or "application/octet-stream"
    slot = _request("POST", UPLOAD_URL, env, {"content_type": content_type})
    headers = slot.get("upload_headers") or {"Content-Type": content_type}
    request = urllib.request.Request(slot["upload_url"], data=path.read_bytes(), headers=headers, method="PUT")
    try:
        with urllib.request.urlopen(request, timeout=REQUEST_TIMEOUT) as response:
            response.read()
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"Higgsfield upload failed ({e.code}): {_error_detail(e.read().decode('utf-8', 'replace'))}")
    return slot["public_url"]


def download(url, dest, env=None, retries=3):
    """Save a generated file. Result URLs are public links, so no API key is sent."""
    dest = Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    part = dest.with_suffix(dest.suffix + ".part")
    for attempt in range(1, retries + 1):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "2d-animation-studio"}),
                                        timeout=REQUEST_TIMEOUT) as response, open(part, "wb") as out:
                while True:
                    chunk = response.read(1 << 16)
                    if not chunk:
                        break
                    out.write(chunk)
            if part.stat().st_size == 0:
                raise RuntimeError("empty file")
            part.replace(dest)
            return dest
        except (OSError, RuntimeError) as e:
            part.unlink(missing_ok=True)
            if attempt == retries:
                raise RuntimeError(f"Could not download the Higgsfield result: {e}")
            time.sleep(RETRY_DELAY * attempt)


def motions(env=None):
    """The camera motions DoP offers (used by "Test key" in Setup to prove the key works)."""
    body = _request("GET", MOTIONS, env)
    items = body.get("items") if isinstance(body, dict) else body
    return [m for m in (items or []) if isinstance(m, dict)]
