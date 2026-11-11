"""One plain-text log per app launch: what the studio did and every error it hit.

The file is started fresh each time the app opens, so it only ever holds the current session.
Secrets (API keys, OAuth tokens) are masked before anything is written.
"""
import re
import threading
import traceback
from datetime import datetime

_lock = threading.Lock()
_file = None
_secrets = []
_last = None
# Google API keys, OpenAI/Anthropic keys, Google OAuth access and refresh tokens.
_SECRET_SHAPES = re.compile(r"AIza[0-9A-Za-z_-]{20,}|sk-[0-9A-Za-z_-]{20,}|ya29\.[0-9A-Za-z._-]+|1//[0-9A-Za-z_-]{20,}")
_SECRET_NAMES = ("KEY", "TOKEN", "SECRET", "PASSWORD")


def start(path, env=None):
    """Begin a new log at path, replacing the previous session's file."""
    global _file, _secrets, _last
    with _lock:
        if _file:
            _file.close()
        _secrets = sorted({v for k, v in (env or {}).items()
                           if len(v) >= 8 and any(n in k.upper() for n in _SECRET_NAMES)}, key=len, reverse=True)
        _last = None
        try:
            _file = open(path, "w", encoding="utf-8", errors="replace", buffering=1)
        except OSError:
            _file = None
    return path


def mask(text):
    text = str(text)
    for secret in _secrets:
        text = text.replace(secret, "***")
    return _SECRET_SHAPES.sub("***", text)


def write(kind, text):
    """Append one entry. kind is a short tag such as INFO, STEP, OUT or ERROR."""
    global _last
    text = mask(text).rstrip()
    if not text:
        return
    with _lock:
        if not _file or (kind, text) == _last:   # the same line often arrives from two places
            return
        _last = (kind, text)
        stamp = datetime.now().strftime("%H:%M:%S")
        try:
            for line in text.splitlines():
                _file.write(f"{stamp} {kind:<5} {line}\n")
        except (OSError, ValueError):
            pass


def error(context, exc=None, tb=None):
    """Record an error with its traceback (the active exception when exc is not given)."""
    if exc is None:
        detail = traceback.format_exc()
    else:
        detail = "".join(traceback.format_exception(type(exc), exc, tb if tb is not None else exc.__traceback__))
    write("ERROR", f"{context}\n{detail}")
