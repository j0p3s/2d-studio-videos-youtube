"""Local coding-agent adapters, plus Google's Gemini API called directly with an API key.
OpenArt (openart_provider, the openart CLI) is listed here as an animation-only provider; see shots_video.

CLI authentication stays in each vendor's CLI. The Gemini API key is read from the
environment (GEMINI_API_KEY or GOOGLE_API_KEY), which the app fills from the studio's .env file.
"""
import json
import os
import re
import shutil
import time
import urllib.error
import urllib.request
from pathlib import Path

import ollama_provider
from ollama_provider import OLLAMA
from openart_provider import OPENART
from castworkshop_provider import CASTWORKSHOP

GEMINI_API = "Gemini API"
PROVIDERS = ("Claude", "OpenAI (Codex)", "Gemini", GEMINI_API, OLLAMA, OPENART, CASTWORKSHOP)
TEXT_PROVIDERS = tuple(p for p in PROVIDERS if p not in (OPENART, CASTWORKSHOP))
GEMINI_API_MODEL = "gemini-3.8-flash"
GEMINI_API_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
GEMINI_API_TIMEOUT = 600  # long scripts take minutes to generate


def load_env_file(path, env):
    """Add KEY=VALUE lines from the studio's .env file to env. The file wins over values
    inherited from Windows, so a stale user variable cannot break the studio."""
    try:
        lines = Path(path).read_text(encoding="utf-8-sig").splitlines()
    except OSError:
        return env
    for line in lines:
        key, sep, value = line.strip().partition("=")
        key = key.removeprefix("export ").strip()
        value = value.strip().strip("\"'")
        if sep and key and not key.startswith("#") and value:
            env[key] = value
    return drop_bad_model(env)


def drop_bad_model(env):
    """Remove a GEMINI_MODEL that cannot be a model name (e.g. a pasted "<placeholder>"):
    the Gemini CLI reads this variable itself and fails every request with HTTP 400."""
    if "GEMINI_MODEL" in env and not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._/-]*", env["GEMINI_MODEL"]):
        del env["GEMINI_MODEL"]
    return env


def gemini_api_key(env=None):
    env = os.environ if env is None else env
    key = env.get("GEMINI_API_KEY") or env.get("GOOGLE_API_KEY")
    if not key:
        raise RuntimeError("Gemini API key not found. Put GEMINI_API_KEY=your-key in the .env file "
                           "in the studio folder, then restart the app.")
    return key


def gemini_api_text(prompt, *, model="", env=None, retries=3):
    """One text answer from the Gemini API. The key travels in a header, never in the URL."""
    env = os.environ if env is None else env
    model = model or env.get("GEMINI_MODEL") or GEMINI_API_MODEL
    request = urllib.request.Request(
        GEMINI_API_URL.format(model=model),
        data=json.dumps({"contents": [{"role": "user", "parts": [{"text": prompt}]}]}).encode("utf-8"),
        headers={"Content-Type": "application/json", "x-goog-api-key": gemini_api_key(env)})
    for attempt in range(1, retries + 1):
        try:
            with urllib.request.urlopen(request, timeout=GEMINI_API_TIMEOUT) as response:
                body = json.loads(response.read().decode("utf-8"))
            break
        except urllib.error.HTTPError as e:
            detail = e.read().decode("utf-8", "replace")
            try:
                detail = json.loads(detail)["error"]["message"]
            except (ValueError, KeyError, TypeError):
                pass
            if e.code in (429, 500, 503) and attempt < retries:
                time.sleep(2 * attempt)
                continue
            raise RuntimeError(f"Gemini API failed ({e.code}, model {model}): {detail[:500]}")
        except (TimeoutError, urllib.error.URLError) as e:
            if isinstance(e, TimeoutError) or isinstance(getattr(e, "reason", None), TimeoutError):
                # Retrying a request that already waited the full timeout would stall the app for longer.
                raise RuntimeError(f"Gemini API did not answer within {GEMINI_API_TIMEOUT} s (model {model}). "
                                   "The model may be overloaded: try again later or pick another model in Setup.")
            if attempt < retries:
                time.sleep(2 * attempt)
                continue
            raise RuntimeError(f"Gemini API could not be reached (model {model}): {e}")
    try:
        parts = body["candidates"][0]["content"]["parts"]
        text = "".join(p.get("text", "") for p in parts if not p.get("thought"))
    except (KeyError, IndexError, TypeError):
        text = ""
    if not text.strip():
        reason = ((body.get("promptFeedback") or {}).get("blockReason")
                  or ((body.get("candidates") or [{}])[0]).get("finishReason") or "empty response")
        raise RuntimeError(f"Gemini API returned no text (model {model}): {reason}")
    return text


def cli_command(provider, env=None):
    env = env or os.environ
    name = {"Claude": "claude", "OpenAI (Codex)": "codex", "Gemini": "gemini", GEMINI_API: "gemini"}.get(provider)
    if not name:
        raise RuntimeError(f"{provider} has no command-line agent: the studio drives it directly.")
    exe = shutil.which(name, path=env.get("PATH"))
    if name == "codex" and exe and "/openai/codex/bin/" in str(exe).replace("\\", "/").lower():
        raise RuntimeError("The selected executable belongs to Codex Desktop. Install the standalone CLI for the studio. "
                           "Go to Setup → Install OpenAI (Codex), then sign in. "
                           "The standalone CLI installs inside this studio's .tools folder.")
    if not exe and name == "claude":
        candidate = Path.home() / ".local/bin/claude.exe"
        exe = str(candidate) if candidate.exists() else None
    if not exe:
        raise RuntimeError(f"{provider} CLI not found. Install it from Setup, then sign in.")
    # Execute npm's JS entry point directly: no cmd.exe quoting of prompts or paths.
    if Path(exe).suffix.lower() in (".cmd", ".ps1"):
        package = {"gemini": "@google/gemini-cli", "codex": "@openai/codex",
                   "claude": "@anthropic-ai/claude-code"}[name]
        root = Path(exe).parent / "node_modules" / package
        try:
            bins = json.loads((root / "package.json").read_text(encoding="utf-8"))["bin"]
            script = root / (bins if isinstance(bins, str) else bins[name])
        except (OSError, ValueError, KeyError):
            raise RuntimeError(f"Cannot resolve {provider} package entry point. Reinstall its CLI.")
        node = shutil.which("node", path=env.get("PATH"))
        if script.exists() and node:
            return [node, str(script)]
        raise RuntimeError(f"Cannot resolve {provider} npm launcher. Reinstall its CLI from Setup.")
    return [exe]


def agent_command(provider, *, animation=False, full_auto=False, model="", env=None, workspace=None):
    cmd = list(cli_command(provider, env))
    if provider == "OpenAI (Codex)":
        full_auto = False  # The app owns rendering; Codex always keeps its filesystem sandbox.
        if animation and not full_auto:
            # Rendering serves frames over localhost; timestamps may download a Whisper model.
            cmd += ["-c", "sandbox_workspace_write.network_access=true"]
        if os.name == "nt" and animation and not full_auto:
            cmd += ["--no-daemon"]
            # A portable, non-Git studio is otherwise treated as an untrusted read-only folder.
            if workspace:
                cmd += ["-c", "projects." + json.dumps(str(Path(workspace).resolve())) + '.trust_level="trusted"']
            config = Path((env or os.environ).get("CODEX_HOME", str(Path.home() / '.codex'))) / 'config.toml'
            if not config.exists():
                cmd += ["-c", 'windows.sandbox="unelevated"']
            else:
                # Preserve existing elevated/MXC selections; supply a sandbox only when unset.
                import tomllib
                configured = tomllib.loads(config.read_text(encoding='utf-8'))
                if not configured.get('windows', {}).get('sandbox'):
                    cmd += ["-c", 'windows.sandbox="unelevated"']
        cmd += ["exec", "--json", "--skip-git-repo-check", "--color", "never",
                "--sandbox", "workspace-write" if animation else "read-only"]
        if model:
            cmd += ["--model", model]
        cmd += ["-"]
    elif provider in ("Gemini", GEMINI_API):
        cmd += ["--output-format", "stream-json", "--skip-trust", "--approval-mode",
                "yolo" if animation and full_auto else "auto_edit" if animation else "plan",
                "--prompt", "Read the task from standard input and complete it."]
        if model:
            cmd += ["--model", model]
    else:
        raise ValueError("Claude uses its existing native adapter")
    return cmd


def portable_prompt(prompt, skill_dir, animation=False):
    if not animation:
        return "Text generation only. Do not edit files or run commands.\n\n" + prompt
    return (f"You are the animation agent for 2D Animation Studio. Read {Path(skill_dir) / 'SKILL.md'} "
            "and its referenced documentation as local files. The GrowKaz kit is already installed in "
            "the working directory; never copy or reinstall it. Relative references/ paths in the skill "
            f"are relative to {skill_dir}. You can read files, write scene code, execute the studio's "
            "Python/Node/FFmpeg tools and inspect rendered images using your own tools. "
            "Do not invoke Claude or another AI CLI. Do not upload or publish anything. "
            "Use the installed patched render.mjs and its default automatic GPU/CPU selection.\n\n" + prompt)


class EventStream:
    """Normalize vendor JSONL into text/tool notifications, preserving failures."""
    def __init__(self, provider):
        self.provider, self.text, self.error = provider, "", ""

    def feed(self, line):
        try:
            ev = json.loads(line)
        except ValueError:
            return [("log", line)] if line.strip() else []
        if not isinstance(ev, dict):
            return []
        t = ev.get("type")
        out = []
        if self.provider == "OpenAI (Codex)":
            item = ev.get("item", {})
            if t == "item.completed" and item.get("type") == "agent_message":
                self.text = item.get("text", "")
                out.append(("text", self.text))
            elif t == "item.started" and item.get("type") in ("command_execution", "mcp_tool_call", "file_change"):
                out.append(("tool", {"name": item.get("tool", item["type"]),
                                     "command": item.get("command", ""), "file_path": item.get("path", "")}))
            elif t in ("turn.failed", "error"):
                self.error = str(ev.get("error", {}).get("message", "") if isinstance(ev.get("error"), dict)
                                 else ev.get("message") or ev.get("error") or "Agent failed")
                out.append(("log", self.error))
        else:
            if t == "message" and ev.get("role") == "assistant":
                chunk = ev.get("content", "")
                self.text = self.text + chunk if ev.get("delta") else chunk
                out.append(("text", chunk))
            elif t == "tool_use":
                params = ev.get("parameters", {})
                out.append(("tool", {"name": ev.get("tool_name", "tool"), **params}))
            elif t == "error" or (t == "result" and ev.get("status") == "error"):
                self.error = str(ev.get("error") or ev.get("message") or "Gemini failed")
                out.append(("log", self.error))
        return out


GEMINI_KEY_HOME = "gemini-api-key"


def gemini_key_home(env):
    """A separate Gemini CLI config folder that signs in with GEMINI_API_KEY. The CLI's normal
    folder may hold a Google login chosen earlier, which it keeps using even when a key is set and
    which Google now rejects (IneligibleTierError). That folder is left untouched."""
    base = Path(env.get("GEMINI_CLI_HOME") or Path.home())
    home = base if base.name == GEMINI_KEY_HOME else base / GEMINI_KEY_HOME
    (home / ".gemini").mkdir(parents=True, exist_ok=True)
    (home / ".gemini" / "settings.json").write_text(
        json.dumps({"security": {"auth": {"selectedType": "gemini-api-key"}}}), encoding="utf-8")
    return home


def run_agent(provider, prompt, run_cmd, *, cwd, env=None, animation=False,
              full_auto=False, model="", skill_dir=None, on_event=None):
    if provider == OPENART:   # no agent and no animation kit: the studio builds the video itself
        if animation:
            raise RuntimeError("OpenArt animation is started by the studio, not by run_agent.")
        raise RuntimeError("OpenArt generates images and video, not text. In Setup choose it only for "
                           "\"Animation & character designs\" and keep a text AI for \"Ideas & script\".")
    if animation and (not skill_dir or not (Path(skill_dir) / 'SKILL.md').is_file()):
        raise RuntimeError("Animation skill missing. Re-run the studio installer from Setup.")
    if provider == OLLAMA:
        if animation:   # automatic scenes are app-managed; optional tool operations use the CLI bridge
            raise RuntimeError("Ollama animation is started by the studio, not by run_agent.")
        return ollama_provider.text(portable_prompt(prompt, skill_dir, False), model=model, env=env,
                                    on_text=(lambda piece: on_event("text", piece)) if on_event else None)
    if provider == GEMINI_API:
        env = os.environ if env is None else env
        if not animation:
            # Ideas and scripts are plain text: one direct API call, no CLI needed.
            text = gemini_api_text(portable_prompt(prompt, skill_dir, False), model=model, env=env)
            if on_event:
                on_event("text", text)
            return text
        # Animation needs an agent that writes files and runs the render kit, which a plain API
        # call cannot do. The Gemini CLI does it, signed in with the same API key.
        gemini_api_key(env)
        model = model or env.get("GEMINI_MODEL", "")
        env["GEMINI_CLI_HOME"] = str(gemini_key_home(env))
    elif provider == "Gemini" and env is not None and Path(env.get("GEMINI_CLI_HOME", "")).name == GEMINI_KEY_HOME:
        env["GEMINI_CLI_HOME"] = str(Path(env["GEMINI_CLI_HOME"]).parent)   # back to the Google login
    stream = EventStream(provider)
    diagnostics = []
    def receive(line):
        for kind, value in stream.feed(line):
            if kind == "log":
                diagnostics.append(value[:1000])
                del diagnostics[:-5]
            if on_event:
                on_event(kind, value)
    cmd = agent_command(provider, animation=animation, full_auto=full_auto, model=model, env=env, workspace=cwd)
    rc = run_cmd(cmd, cwd=str(cwd), stdin_text=portable_prompt(prompt, skill_dir, animation), on_line=receive)
    if rc or stream.error:
        detail = stream.error or '\n'.join(diagnostics) or 'Check the log and CLI login.'
        if 'IneligibleTierError' in detail:
            detail = ('Google no longer accepts the Google-account login in the Gemini CLI. '
                      'In Setup choose "Gemini API" instead (it uses the key in .env).\n' + detail)
        raise RuntimeError(f"{provider} failed (exit {rc}): {detail}")
    if not stream.text.strip():
        raise RuntimeError(f"{provider} returned no response. Check authentication and the selected model.")
    if animation and re.search(r"\b(blocked by policy|read.only (?:filesystem|permissions|access)|"
                               r"(?:pass|session|task).{0,35}(?:is blocked|blocked by)|"
                               r"(?:could not|couldn.t|cannot).{0,50}(?:write|render|read the skill))\b",
                               stream.text + '\n' + '\n'.join(diagnostics), re.I | re.S):
        raise RuntimeError(f"{provider} could not complete this animation pass:\n{stream.text}\n\n"
                           "Animation stopped before later passes. Check the standalone CLI installation "
                           "and its workspace permissions in Setup.")
    return stream.text
