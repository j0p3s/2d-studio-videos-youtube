"""Local coding-agent adapters. Authentication stays in each vendor's CLI."""
import json
import os
import re
import shutil
from pathlib import Path

PROVIDERS = ("Claude", "OpenAI (Codex)", "Gemini")


def cli_command(provider, env=None):
    env = env or os.environ
    name = {"Claude": "claude", "OpenAI (Codex)": "codex", "Gemini": "gemini"}[provider]
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
    elif provider == "Gemini":
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


def run_agent(provider, prompt, run_cmd, *, cwd, env=None, animation=False,
              full_auto=False, model="", skill_dir=None, on_event=None):
    if animation and (not skill_dir or not (Path(skill_dir) / 'SKILL.md').is_file()):
        raise RuntimeError("GrowKaz skill missing. Re-run the studio installer from Setup.")
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
