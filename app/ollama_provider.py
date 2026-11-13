"""Local AI through Ollama: works with no internet and no provider credits.

Ideas/scripts and automatic animation use cancellable local API streams. The automatic
pipeline in local_animation owns scene files, rendering and export. Optional tool-based
agent operations retain the Claude Code/Ollama bridge (see claude_env).
"""
import json
import http.client
import os
import queue
import re
import shutil
import subprocess
import socket
import threading
import time
import urllib.error
import urllib.request
import urllib.parse
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


def release_model(model='', env=None):
    """Release only the studio's selected model before another GPU-heavy stage."""
    name = model or (os.environ if env is None else env).get('OLLAMA_MODEL') or DEFAULT_MODEL
    if is_running(env):
        with _open('/api/generate', {'model': name, 'keep_alive': 0}, env, timeout=60) as reply:
            reply.read()


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


def _chat_events(payload, env, check_cancel, idle_callback=None):
    """Keep cancellation responsive even while connecting or awaiting headers/tokens."""
    url = urllib.parse.urlsplit(base_url(env) + '/api/chat')
    connection_type = http.client.HTTPSConnection if url.scheme == 'https' else http.client.HTTPConnection
    connection = connection_type(url.hostname, url.port, timeout=900)
    events, stopped = queue.Queue(maxsize=16), threading.Event()
    stream_socket = [None]

    def publish(kind, value):
        while not stopped.is_set():
            try:
                events.put((kind, value), timeout=.1)
                return
            except queue.Full:
                pass

    def read():
        try:
            if stopped.is_set():
                return
            connection.request('POST', url.path + ('?' + url.query if url.query else ''),
                               body=json.dumps(payload).encode('utf-8'),
                               headers={'Content-Type': 'application/json'})
            stream_socket[0] = connection.sock
            if stopped.is_set():
                return
            reply = connection.getresponse()
            if reply.status >= 400:
                body = reply.read().decode('utf-8', 'replace')
                try:
                    detail = json.loads(body).get('error') or body
                except ValueError:
                    detail = body or reply.reason
                raise RuntimeError('Ollama failed: ' + str(detail))
            for raw in reply:
                if stopped.is_set():
                    return
                publish('event', json.loads(raw or b'{}'))
            publish('end', None)
        except Exception as exc:
            publish('error', exc)
        finally:
            connection.close()

    reader = threading.Thread(target=read, name='ollama-stream', daemon=True)
    reader.start()
    try:
        while True:
            if check_cancel:
                check_cancel()
            try:
                kind, value = events.get(timeout=.1)
            except queue.Empty:
                if idle_callback:
                    idle_callback('')
                continue
            if kind == 'end':
                break
            if kind == 'error':
                raise value
            yield value
    finally:
        stopped.set()
        # shutdown interrupts getresponse()/readline(), including a server that
        # has sent no headers yet. Do not wait for a blocking response.close().
        active_socket = connection.sock or stream_socket[0]
        if active_socket is not None:
            try:
                active_socket.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
        reader.join(timeout=.2)


def text(prompt, *, model="", env=None, on_text=None, context=TEXT_CONTEXT,
         thinking=None, response_format=None, on_metrics=None, check_cancel=None, on_retry=None):
    """One chat answer from the local model, streamed to on_text piece by piece."""
    ensure_running(env)
    name = pick_model(model, env)
    payload = {"model": name, "stream": True, "messages": [{"role": "user", "content": prompt}],
               "options": {"num_ctx": context}, "keep_alive": "15m"}
    settings = os.environ if env is None else env
    effort = thinking or settings.get('OLLAMA_THINKING', 'low')
    if name.lower().startswith('gpt-oss'):
        if effort not in ('low', 'medium', 'high'):
            raise ValueError('OLLAMA_THINKING must be low, medium or high')
        payload['think'] = effort
    if response_format is not None:
        payload['format'] = response_format
    # Reasoning models (gpt-oss, qwen3, ...) sometimes spend the whole reply on reasoning and stop
    # with an empty answer, so an empty reply is asked again before it counts as a failure.
    for attempt in range(EMPTY_RETRIES + 1):
        if check_cancel:
            check_cancel()
        pieces, reasoning, reason = [], 0, ""
        try:
            events = _chat_events(payload, env, check_cancel, on_text if check_cancel is None else None)
            try:
                for event in events:
                    if event.get("error"):
                        raise RuntimeError(f"Ollama failed: {event['error']}")
                    if event.get('done') and on_metrics:
                        on_metrics({k: event[k] for k in ('total_duration', 'load_duration',
                                    'prompt_eval_count', 'prompt_eval_duration', 'eval_count',
                                    'eval_duration') if k in event})
                    message = event.get("message") or {}
                    reasoning += len(message.get("thinking") or "")
                    if message.get('thinking') and on_text:
                        on_text('')  # Give the caller a cancellation checkpoint during reasoning.
                    reason = event.get("done_reason") or reason
                    piece = message.get("content") or ""
                    if piece:
                        pieces.append(piece)
                        if on_text:
                            on_text(piece)
            finally:
                events.close()
        except RuntimeError as exc:
            if 'token repeat limit reached' not in str(exc).lower():
                raise
            # Never return a partial answer from an aborted stream or replay its
            # looping output in the next prompt. Keep retries local and bounded.
            if attempt == EMPTY_RETRIES:
                raise RuntimeError(
                    f'Ollama ({name}) kept repeating tokens after {attempt + 1} tries. '
                    'This is a local generation loop, not a credit or usage quota. '
                    'No complete answer was accepted. Try Auto again or choose another local model.'
                ) from exc
            if check_cancel:
                check_cancel()
            payload['options'].update(temperature=.7 + .1 * attempt,
                                      repeat_penalty=1.1, repeat_last_n=128, seed=attempt + 1)
            if name.lower().startswith('gpt-oss'):
                payload['think'] = 'low'
            if on_retry:
                on_retry(f'Ollama hit a local repetition loop (not a usage quota); '
                         f'discarding the partial answer and retrying locally ({attempt + 2}/{EMPTY_RETRIES + 1}).')
            continue
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
