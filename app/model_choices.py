"""Model names for the Setup dropdowns, read from each provider's own model list.

Nothing here is a hard-coded guess: a name is offered only when the provider's API or CLI reports it
right now. When a provider has no list the studio can read (a CLI signed in through the browser has
no key to ask with), the list is None: the dropdown then offers only the default, and a typed name is
saved as "not checked".
"""
import json
import urllib.request

import ollama_provider
import openart_provider
from ai_providers import GEMINI_API, gemini_api_key
from ollama_provider import OLLAMA
from openart_provider import OPENART

DEFAULT = "(default)"   # shown for an empty setting: the provider's or the studio's default model
TIMEOUT = 20
# Models on the Gemini list that answer generateContent but are not for writing text or running an agent.
GEMINI_NOT_TEXT = ("tts", "image", "banana", "lyria", "transcribe", "embedding", "aqa", "veo", "imagen")


def _get(url, headers):
    with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=TIMEOUT) as reply:
        return json.load(reply)


def gemini(env):
    data = _get("https://generativelanguage.googleapis.com/v1beta/models?pageSize=1000",
                {"x-goog-api-key": gemini_api_key(env)})   # the key travels in a header, never in the URL
    names = [m.get("name", "").split("/")[-1] for m in data.get("models", [])
             if "generateContent" in m.get("supportedGenerationMethods", [])]
    return [n for n in names if n and not any(word in n for word in GEMINI_NOT_TEXT)]


def anthropic(env):
    data = _get("https://api.anthropic.com/v1/models?limit=1000",
                {"x-api-key": env["ANTHROPIC_API_KEY"], "anthropic-version": "2023-06-01"})
    return [m["id"] for m in data.get("data", []) if m.get("id")]


def openai(env):
    data = _get("https://api.openai.com/v1/models", {"Authorization": "Bearer " + env["OPENAI_API_KEY"]})
    return sorted(m["id"] for m in data.get("data", []) if m.get("id", "").startswith(("gpt", "o", "codex")))


def openart(run, env, kind):
    """OpenArt models that can make this kind of output ("image" or "video")."""
    return [m["id"] for m in openart_provider.models(run, env)
            if isinstance(m, dict) and m.get("id") and kind in (m.get("modes") or {})]


def available(provider, env, *, openart_run=None, kind=None):
    """(names, note). names is None when the provider's list cannot be read; note says why."""
    try:
        if provider == OLLAMA:
            if not ollama_provider.is_running(env):
                return None, "Ollama is not running, so its models cannot be listed"
            return ollama_provider.models(env), ""
        if provider == OPENART:
            return openart(openart_run, env, kind), ""
        if provider in (GEMINI_API, "Gemini"):
            if not env.get("GEMINI_API_KEY"):
                return None, "no GEMINI_API_KEY in .env, so Gemini models cannot be listed"
            return gemini(env), ""
        key, fetch = {"Claude": ("ANTHROPIC_API_KEY", anthropic), "OpenAI (Codex)": ("OPENAI_API_KEY", openai)}[provider]
        if not env.get(key):
            return None, f"{provider} is signed in through its CLI, which has no model list to check against"
        return fetch(env), ""
    except Exception as error:
        return None, f"could not read the {provider} model list ({str(error)[:120]})"


def check(value, names):
    """(model to save, problem). An empty value or DEFAULT saves "" (the default model)."""
    value = (value or "").strip()
    if value in ("", DEFAULT):
        return "", ""
    if names is None or value in names:
        return value, ""
    if ":" not in value and value + ":latest" in names:     # Ollama's short form
        return value, ""
    return None, f'"{value}" is not on the provider\'s model list'
