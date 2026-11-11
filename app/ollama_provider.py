"""Local AI through Ollama: works with no internet and no provider credits.

Ideas and scripts are one streamed chat request to the local Ollama server. Animation needs an
agent that writes files and runs the render kit, so the Claude Code CLI is pointed at Ollama's
Anthropic-compatible endpoint instead of Anthropic's servers (see claude_env).
"""
import json
import os
import re
import shutil
import subprocess
import time
import urllib.error
import urllib.request
from pathlib import Path

OLLAMA = "Ollama (offline)"
DEFAULT_MODEL = "gpt-oss:20b"     # fits a 16 GB GPU and can call tools; change it in Setup
TEXT_CONTEXT = 16384              # tokens: enough for a full script prompt and its answer
EMPTY_RETRIES = 2                 # extra tries when a model answers with no text
AGENT_CONTEXT = 65536             # the animation agent's instructions alone are tens of thousands of tokens
NO_WINDOW = 0x08000000 if os.name == "nt" else 0


def base_url(env=None):
    host = ((os.environ if env is None else env).get("OLLAMA_HOST") or "127.0.0.1:11434").strip().rstrip("/")
    if "://" not in host:
        host = "http://" + host
    return host.replace("://0.0.0.0", "://127.0.0.1")


def _open(path, payload=None, env=None, timeout=10):
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(base_url(env) + path, data=data, headers={"Content-Type": "application/json"})
    return urllib.request.urlopen(request, timeout=timeout)


def _error_text(exc):
    if isinstance(exc, urllib.error.HTTPError):
        body = exc.read().decode("utf-8", "replace")
        try:
            return json.loads(body).get("error") or body
        except ValueError:
            return body or str(exc)
    return str(getattr(exc, "reason", exc))


def is_running(env=None):
    try:
        with _open("/api/version", env=env, timeout=3):
            return True
    except (OSError, ValueError):
        return False


def executable():
    """ollama.exe from PATH or its default per-user install folder (None when not installed)."""
    found = shutil.which("ollama")
    if found:
        return found
    for root in (os.environ.get("LOCALAPPDATA"), os.environ.get("ProgramFiles")):
        if root:
            for candidate in (Path(root) / "Programs" / "Ollama" / "ollama.exe", Path(root) / "Ollama" / "ollama.exe"):
                if candidate.is_file():
                    return str(candidate)
    return None


def ensure_running(env=None, wait=40):
    """Start the local Ollama server when it is not answering yet."""
    if is_running(env):
        return
    exe = executable()
    if not exe:
        raise RuntimeError("Ollama is not installed. Go to Setup and press \"Install Ollama\".")
    # The user's own environment, not the studio's: Ollama keeps its models in the real user profile.
    subprocess.Popen([exe, "serve"], env=dict(os.environ), stdin=subprocess.DEVNULL,
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, creationflags=NO_WINDOW)
    deadline = time.time() + wait
    while time.time() < deadline:
        if is_running(env):
            return
        time.sleep(1)
    raise RuntimeError("Ollama did not start. Open the Ollama app once, then try again.")


def models(env=None):
    with _open("/api/tags", env=env) as reply:
        return [m.get("name", "") for m in json.load(reply).get("models", [])]


def _installed(name, names):
    return name in names or (":" not in name and name + ":latest" in names)


def pick_model(model="", env=None):
    """The model to use: the given one, OLLAMA_MODEL from .env, or the default. It must be downloaded."""
    name = (model or (os.environ if env is None else env).get("OLLAMA_MODEL") or DEFAULT_MODEL).strip()
    if not _installed(name, models(env)):
        raise RuntimeError(f"The Ollama model \"{name}\" is not downloaded yet. Go to Setup and press "
                           "\"Download offline model\" (needs internet once), or type the name of a model "
                           "you already have in the offline model box.")
    return name


def pull(model, env=None, on_progress=None):
    """Download a model (needs internet). on_progress(fraction 0..1, status text)."""
    try:
        with _open("/api/pull", {"model": model, "stream": True}, env, timeout=120) as reply:
            for raw in reply:
                event = json.loads(raw or b"{}")
                if event.get("error"):
                    raise RuntimeError(f"Ollama could not download {model}: {event['error']}")
                if on_progress:
                    total, done = event.get("total") or 0, event.get("completed") or 0
                    on_progress(done / total if total else None, event.get("status", ""))
    except (urllib.error.URLError, OSError) as exc:
        raise RuntimeError(f"Ollama could not download {model}: {_error_text(exc)}") from exc


def text(prompt, *, model="", env=None, on_text=None, context=TEXT_CONTEXT):
    """One chat answer from the local model, streamed to on_text piece by piece."""
    ensure_running(env)
    name = pick_model(model, env)
    payload = {"model": name, "stream": True, "messages": [{"role": "user", "content": prompt}],
               "options": {"num_ctx": context}}
    # Reasoning models (gpt-oss, qwen3, ...) sometimes spend the whole reply on reasoning and stop
    # with an empty answer, so an empty reply is asked again before it counts as a failure.
    for attempt in range(EMPTY_RETRIES + 1):
        pieces, reasoning, reason = [], 0, ""
        try:
            with _open("/api/chat", payload, env, timeout=900) as reply:   # the first token can take minutes on a CPU
                for raw in reply:
                    event = json.loads(raw or b"{}")
                    if event.get("error"):
                        raise RuntimeError(f"Ollama failed: {event['error']}")
                    message = event.get("message") or {}
                    reasoning += len(message.get("thinking") or "")
                    reason = event.get("done_reason") or reason
                    piece = message.get("content") or ""
                    if piece:
                        pieces.append(piece)
                        if on_text:
                            on_text(piece)
        except (urllib.error.URLError, OSError) as exc:
            raise RuntimeError(f"Ollama failed: {_error_text(exc)}") from exc
        answer = re.sub(r"<think>.*?</think>", "", "".join(pieces), flags=re.S).strip()
        if answer:
            return answer
    detail = (f"it wrote {reasoning} characters of reasoning but no answer" if reasoning else "the reply was empty")
    if reason == "length":
        detail += "; it ran out of room, so try a shorter video length"
    raise RuntimeError(f"Ollama ({name}) returned no text in {EMPTY_RETRIES + 1} tries: {detail}. "
                       "Press Auto again or try another model in Setup.")


def agent_model(model="", env=None, context=AGENT_CONTEXT):
    """A copy of the model with a large context window. Ollama's default window is far too small
    for the animation agent, and the Anthropic-compatible endpoint cannot set it per request."""
    ensure_running(env)
    name = pick_model(model, env)
    context = int((os.environ if env is None else env).get("OLLAMA_NUM_CTX") or context)
    copy = re.sub(r"[^a-z0-9._-]+", "-", name.lower()) + f"-studio{context // 1024}k"
    if not _installed(copy, models(env)):
        try:
            with _open("/api/create", {"model": copy, "from": name, "parameters": {"num_ctx": context},
                                       "stream": False}, env, timeout=300) as reply:
                reply.read()
        except (urllib.error.URLError, OSError) as exc:
            raise RuntimeError(f"Ollama could not prepare {name} for animation: {_error_text(exc)}") from exc
    return copy


def claude_env(env, model):
    """Environment that makes the Claude Code CLI talk to the local Ollama server only."""
    env = dict(env)
    env.update({
        "ANTHROPIC_BASE_URL": base_url(env), "ANTHROPIC_AUTH_TOKEN": "ollama", "ANTHROPIC_API_KEY": "",
        "ANTHROPIC_MODEL": model, "ANTHROPIC_SMALL_FAST_MODEL": model,
        "ANTHROPIC_DEFAULT_OPUS_MODEL": model, "ANTHROPIC_DEFAULT_SONNET_MODEL": model,
        "ANTHROPIC_DEFAULT_HAIKU_MODEL": model, "CLAUDE_CODE_SUBAGENT_MODEL": model,
        "CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC": "1", "DISABLE_AUTOUPDATER": "1",
        "DISABLE_TELEMETRY": "1", "DISABLE_ERROR_REPORTING": "1",
        "API_TIMEOUT_MS": "3600000",   # a local model can take many minutes per turn
    })
    return env
