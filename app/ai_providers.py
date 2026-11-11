"""
AI Providers bridge for 2D Studio.
Compatible with studio_gui callbacks, Antigravity/Gemini Direct API,
and extended timeouts for complex video animation plans.
"""

import json
import os
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

PROVIDER_GEMINI = "gemini"
PROVIDER_CLAUDE = "claude"

PROVIDERS = {
    PROVIDER_GEMINI: {
        "name": "Gemini / Antigravity API",
        "description": "Google Direct API Runner (Headless)",
    },
    PROVIDER_CLAUDE: {
        "name": "Claude",
        "description": "Anthropic Claude Code CLI",
    },
}


def resolve_claude_bin():
    return shutil.which("claude.cmd") or shutil.which("claude.exe") or shutil.which("claude")


def cli_command(provider_name="gemini", *args, **kwargs):
    p_name = (provider_name or "").lower().strip() if isinstance(provider_name, str) else ""
    if p_name in [PROVIDER_CLAUDE, "anthropic"]:
        c_bin = resolve_claude_bin()
        return [c_bin] if c_bin else ["claude"]
    return [sys.executable]


def _to_text(val):
    if val is None:
        return ""
    if callable(val):
        return ""
    return str(val)


def portable_prompt(prompt_text, system_instruction=""):
    p = _to_text(prompt_text).strip()
    s = _to_text(system_instruction).strip()
    if s:
        return f"{s}\n\n{p}"
    return p


def _call_gemini_rest(prompt, system_instruction="", cwd=None):
    api_key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY nao encontrada nas variaveis de ambiente.")

    # Modelo rapido e suportado pela API
    model = "gemini-3.8-flash"
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"

    full_text = portable_prompt(prompt, system_instruction)

    payload = {
        "contents": [
            {
                "role": "user",
                "parts": [{"text": full_text}],
            }
        ],
        "generationConfig": {
            "temperature": 0.7,
        },
    }

    req_data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=req_data, headers={"Content-Type": "application/json"})

    # Timeout alargado para 600 segundos (10 minutos) para dar tempo de gerar cenas completas
    max_retries = 3
    timeout_seconds = 600

    for attempt in range(1, max_retries + 1):
        try:
            with urllib.request.urlopen(req, timeout=timeout_seconds) as response:
                res_body = json.loads(response.read().decode("utf-8"))
                candidates = res_body.get("candidates", [])
                if not candidates:
                    raise RuntimeError(f"A API nao retornou candidatos: {res_body}")
                return candidates[0]["content"]["parts"][0]["text"]
        except urllib.error.HTTPError as e:
            err_msg = e.read().decode("utf-8")
            raise RuntimeError(f"Gemini API Error ({e.code}): {err_msg}")
        except (TimeoutError, urllib.error.URLError) as e:
            if attempt < max_retries:
                time.sleep(2)
                continue
            raise RuntimeError(f"A operacao excedeu o tempo limite ({timeout_seconds}s): {e}")


def run_agent(prompt, provider="gemini", system_instruction="", cwd=None, interactive=False, *args, **kwargs):
    clean_prompt = _to_text(prompt)
    clean_sys = _to_text(system_instruction)

    p_name = provider if isinstance(provider, str) else PROVIDER_GEMINI
    p_name = p_name.lower().strip()

    target_cwd = str(cwd or Path.cwd())

    if p_name in [PROVIDER_CLAUDE, "anthropic"]:
        c_bin = resolve_claude_bin()
        full_p = portable_prompt(clean_prompt, clean_sys)
        if interactive:
            return subprocess.Popen([c_bin or "claude", full_p], cwd=target_cwd, shell=True)
        proc = subprocess.run(
            [c_bin or "claude", "--print", full_p],
            cwd=target_cwd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            shell=True,
            check=True,
        )
        return proc.stdout.strip()

    return _call_gemini_rest(clean_prompt, system_instruction=clean_sys, cwd=target_cwd)