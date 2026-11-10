"""2D Animation Studio - Windows GUI.

Pipeline:  ScriptForge (ideas + script, via Claude Code)  ->  voiceover (edge-tts or your file)
           ->  GrowKaz Stickman Studio animation (Claude Code runs the make-2d-video skill)
           ->  thumbnail  ->  YouTube upload (YouTube Data API v3).
"""
import hashlib
import json
import os
import queue
import re
import shutil
import subprocess
import sys
import threading
import time
import traceback
import webbrowser
from datetime import datetime, timezone
from pathlib import Path

APP_DIR = Path(__file__).resolve().parent
INSTALLED_HOME = Path.home() / "2D-Animation-Studio"


def _find_home():
    """The folder that holds growkaz-stickman-studio. Running from the setup/repo folder
    (e.g. Desktop\\2D-Animation-Studio-Setup) still uses the installed studio."""
    here = APP_DIR.parent
    if (here / "growkaz-stickman-studio" / "render.mjs").exists():
        return here
    if (INSTALLED_HOME / "growkaz-stickman-studio" / "render.mjs").exists():
        return INSTALLED_HOME
    return here


HOME = _find_home()
STUDIO = HOME / "growkaz-stickman-studio"
WORK = HOME / "work"
YT_DIR = HOME / "youtube"
SETTINGS_FILE = HOME / "settings.json"
PROMPT_FILE = APP_DIR / "skills" / "scriptforge" / "SKILL.md"
SKILLS_DIR = Path.home() / ".claude" / "skills"
ERR_LOG = HOME / "gui_error.log"
NO_WINDOW = 0x08000000 if os.name == "nt" else 0


def _log_crash(exc_type, exc, tb):
    try:
        ERR_LOG.write_text("".join(traceback.format_exception(exc_type, exc, tb)), encoding="utf-8")
    except Exception:
        pass
    sys.__excepthook__(exc_type, exc, tb)


sys.excepthook = _log_crash

try:
    import customtkinter as ctk
except ImportError:
    import tkinter.messagebox as mb
    mb.showerror("2D Animation Studio", "customtkinter is not installed.\nRun Install-2D-Studio.cmd first.")
    sys.exit(1)
from tkinter import filedialog, messagebox

# ----------------------------------------------------------------------------- data
NICHES = {
    "1. SELF-IMPROVEMENT": ["1.1 Discipline & Habits", "1.2 Productivity & Focus", "1.3 Confidence & Mindset",
                            "1.4 Stoicism & Life Philosophy", "1.5 Money & Success Habits"],
    "2. PSYCHOLOGY": ["2.1 Dark Psychology & Manipulation Tactics (awareness/defense)",
                      "2.2 Human Behavior & Social Dynamics", "2.3 Cognitive Biases & Mind Tricks",
                      "2.4 Relationships & Attraction", "2.5 Mental Health & Emotions"],
    "3. WHAT IF": ["3.1 What If - Earth & Nature", "3.2 What If - Space & the Universe",
                   "3.3 What If - The Human Body", "3.4 What If - History Went Differently",
                   "3.5 What If - Future & Technology"],
    "4. SCIENCE": ["4.1 Space & Astronomy", "4.2 The Human Body & Biology", "4.3 Physics Made Simple",
                   "4.4 Earth, Oceans & Extreme Nature", "4.5 Future Tech & AI"],
    "5. HISTORY": ["5.1 Ancient Civilizations", "5.2 Wars & Battles", "5.3 Mysteries & Unsolved Events",
                   "5.4 Empires, Rulers & Dynasties", "5.5 Forgotten & Strange History"],
}
CUSTOM = "Custom sub-niche..."
VOICES = ["en-US-AndrewNeural", "en-US-GuyNeural", "en-US-ChristopherNeural", "en-US-BrianNeural",
          "en-US-EricNeural", "en-US-AriaNeural", "en-US-JennyNeural", "en-US-EmmaNeural",
          "en-GB-RyanNeural", "en-GB-SoniaNeural", "en-AU-WilliamNeural",
          "pt-BR-AntonioNeural", "pt-BR-FranciscaNeural", "pt-PT-DuarteNeural", "pt-PT-RaquelNeural",
          "es-ES-AlvaroNeural", "fr-FR-HenriNeural", "de-DE-ConradNeural"]
STYLES = {"Emerald (GrowKaz)": "emerald", "Ember Forge": "ember", "Arctic Glass": "arctic",
          "Sakura Bloom": "sakura", "Retro Print": "retro", "Let Claude choose": "auto"}
CATEGORIES = {"Education": "27", "Science & Technology": "28", "Entertainment": "24",
              "People & Blogs": "22", "Film & Animation": "1", "Howto & Style": "26"}
ACCENT, ACCENT_HOVER = "#10b981", "#059669"
SIDEBAR_BG, CARD_BG = "#0f1115", "#171a21"


# ----------------------------------------------------------------------------- helpers
def fresh_env():
    """PATH from the registry (tools installed after this process started) + our extras."""
    env = os.environ.copy()
    parts = []
    try:
        import winreg
        for root, key in [(winreg.HKEY_LOCAL_MACHINE, r"SYSTEM\CurrentControlSet\Control\Session Manager\Environment"),
                          (winreg.HKEY_CURRENT_USER, "Environment")]:
            try:
                with winreg.OpenKey(root, key) as k:
                    parts.append(os.path.expandvars(winreg.QueryValueEx(k, "Path")[0]))
            except OSError:
                pass
    except ImportError:
        pass
    py_dir = Path(sys.executable).parent
    parts += [str(Path.home() / ".local" / "bin"), str(py_dir), str(py_dir / "Scripts"), env.get("PATH", "")]
    env["PATH"] = ";".join(p for p in parts if p)
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONUTF8"] = "1"
    return env


ENV = fresh_env()


def which(name):
    return shutil.which(name, path=ENV["PATH"])


PY = Path(sys.executable)
if PY.name.lower() == "pythonw.exe":
    PY = PY.with_name("python.exe")
PY = str(PY)


def claude_exe():
    c = which("claude")
    if not c:
        p = Path.home() / ".local" / "bin" / "claude.exe"
        c = str(p) if p.exists() else None
    return c


def slugify(text, n=40):
    s = re.sub(r"[^a-zA-Z0-9]+", "-", text).strip("-").lower()
    return (s[:n].strip("-") or "video")


def load_settings():
    try:
        return json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def save_settings(d):
    try:
        SETTINGS_FILE.write_text(json.dumps(d, indent=2), encoding="utf-8")
    except Exception:
        pass


def scriptforge_prompt():
    t = PROMPT_FILE.read_text(encoding="utf-8")
    if t.startswith("---"):
        t = t.split("---", 2)[2]
    return t.strip()


def extract_json(text, opener="["):
    closer = "]" if opener == "[" else "}"
    a, b = text.find(opener), text.rfind(closer)
    if a < 0 or b <= a:
        raise ValueError("Claude did not return JSON:\n" + text[:500])
    return json.loads(text[a:b + 1])


def open_path(p):
    try:
        os.startfile(str(p))
    except Exception as e:
        messagebox.showerror("Open", str(e))


# ----------------------------------------------------------------------------- app
class Studio(ctk.CTk):
    def __init__(self):
        super().__init__()
        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("green")
        self.title("2D Animation Studio")
        self.geometry("1240x800")
        self.minsize(1050, 680)
        self.configure(fg_color="#0b0d10")

        self.q = queue.Queue()
        self.proc = None
        self.busy = False
        self.settings = load_settings()
        self.s = self.settings.get("current", {})   # current video state
        self.ideas = []

        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)
        self._build_sidebar()
        self.pages = {}
        container = ctk.CTkFrame(self, fg_color="transparent")
        container.grid(row=0, column=1, sticky="nsew", padx=18, pady=(18, 6))
        container.grid_columnconfigure(0, weight=1)
        container.grid_rowconfigure(0, weight=1)
        for name, builder in [("setup", self._page_setup), ("script", self._page_script),
                              ("voice", self._page_voice), ("animate", self._page_animate),
                              ("upload", self._page_upload)]:
            f = ctk.CTkFrame(container, fg_color="transparent")
            f.grid(row=0, column=0, sticky="nsew")
            builder(f)
            self.pages[name] = f
        self._build_statusbar()
        self.show("setup" if not self.s else "script")
        self.after(100, self._pump)
        self.after(300, self.check_setup)
        self.protocol("WM_DELETE_WINDOW", self._on_close)

    # ------------------------------------------------------------------ layout
    def _build_sidebar(self):
        sb = ctk.CTkFrame(self, width=230, corner_radius=0, fg_color=SIDEBAR_BG)
        sb.grid(row=0, column=0, rowspan=2, sticky="nsw")
        sb.grid_propagate(False)
        ctk.CTkLabel(sb, text="✦ 2D Animation\n    Studio", font=ctk.CTkFont(size=24, weight="bold"),
                     justify="left", text_color=ACCENT).pack(anchor="w", padx=22, pady=(26, 4))
        ctk.CTkLabel(sb, text="ScriptForge × GrowKaz Stickman", text_color="#7c8594",
                     font=ctk.CTkFont(size=12)).pack(anchor="w", padx=24, pady=(0, 22))
        self.nav = {}
        for key, label in [("setup", "⚙   Setup & Tools"), ("script", "①   Script"), ("voice", "②   Voiceover"),
                           ("animate", "③   Animate"), ("upload", "④   Thumbnail & Upload")]:
            b = ctk.CTkButton(sb, text=label, anchor="w", height=44, corner_radius=10,
                              fg_color="transparent", hover_color="#1d222b", text_color="#d6dbe3",
                              font=ctk.CTkFont(size=15), command=lambda k=key: self.show(k))
            b.pack(fill="x", padx=12, pady=3)
            self.nav[key] = b
        ctk.CTkFrame(sb, height=1, fg_color="#232833").pack(fill="x", padx=18, pady=18)
        ctk.CTkLabel(sb, text="Current video", text_color="#7c8594", font=ctk.CTkFont(size=12)).pack(anchor="w", padx=24)
        self.lbl_current = ctk.CTkLabel(sb, text="—", wraplength=190, justify="left",
                                        font=ctk.CTkFont(size=13, weight="bold"))
        self.lbl_current.pack(anchor="w", padx=24, pady=(2, 8))
        ctk.CTkButton(sb, text="＋ New video", height=34, fg_color="#1d222b", hover_color="#272d38",
                      command=self.new_video).pack(fill="x", padx=18, pady=4)
        ctk.CTkButton(sb, text="📁 Open studio folder", height=34, fg_color="#1d222b", hover_color="#272d38",
                      command=lambda: open_path(HOME)).pack(fill="x", padx=18, pady=4)
        self._refresh_current()

    def _build_statusbar(self):
        bar = ctk.CTkFrame(self, height=46, fg_color=SIDEBAR_BG, corner_radius=0)
        bar.grid(row=1, column=1, sticky="ew")
        bar.grid_columnconfigure(1, weight=1)
        self.lbl_status = ctk.CTkLabel(bar, text="Ready", anchor="w", text_color="#aab2bf")
        self.lbl_status.grid(row=0, column=0, padx=16, pady=10, sticky="w")
        self.progress = ctk.CTkProgressBar(bar, height=10, progress_color=ACCENT)
        self.progress.grid(row=0, column=1, padx=10, sticky="ew")
        self.progress.set(0)
        self.lbl_pct = ctk.CTkLabel(bar, text="", width=230, anchor="e", text_color="#d6dbe3",
                                    font=ctk.CTkFont(family="Consolas", size=12))
        self.lbl_pct.grid(row=0, column=2, padx=(0, 6))
        self.btn_stop = ctk.CTkButton(bar, text="■ Stop", width=80, fg_color="#7f1d1d", hover_color="#991b1b",
                                      state="disabled", command=self.stop_job)
        self.btn_stop.grid(row=0, column=3, padx=12)
        self._job = None
        self._cancel = False

    def show(self, key):
        self.pages[key].tkraise()
        for k, b in self.nav.items():
            b.configure(fg_color=("#1f6f53" if k == key else "transparent"))
        if key == "voice":
            self._sync_voice_page()
        elif key == "animate":
            self._sync_animate_page()
        elif key == "upload":
            self._sync_upload_page()

    @staticmethod
    def header(parent, title, subtitle):
        ctk.CTkLabel(parent, text=title, font=ctk.CTkFont(size=26, weight="bold")).pack(anchor="w")
        ctk.CTkLabel(parent, text=subtitle, text_color="#8b94a3", font=ctk.CTkFont(size=13),
                     wraplength=900, justify="left").pack(anchor="w", pady=(2, 14))

    @staticmethod
    def card(parent, **pack):
        c = ctk.CTkFrame(parent, fg_color=CARD_BG, corner_radius=14)
        c.pack(**({"fill": "x", "pady": 6} | pack))
        return c

    def logbox(self, parent, height=160):
        t = ctk.CTkTextbox(parent, height=height, fg_color="#0d0f13", text_color="#9fe7c6",
                           font=ctk.CTkFont(family="Consolas", size=12), wrap="word")
        return t

    # ------------------------------------------------------------------ thread plumbing
    def ui(self, fn, *a):
        self.q.put((fn, a))

    def _pump(self):
        try:
            while True:
                fn, a = self.q.get_nowait()
                try:
                    fn(*a)
                except Exception:
                    traceback.print_exc()
        except queue.Empty:
            pass
        self.after(80, self._pump)

    def log(self, box, text):
        def _w():
            box.insert("end", text.rstrip() + "\n")
            box.see("end")
        self.ui(_w)

    def status(self, text):
        self.ui(lambda: self.lbl_status.configure(text=text))

    # ------------------------------------------------------------------ progress
    @staticmethod
    def _fmt_t(s):
        s = int(max(0, s))
        return f"{s // 3600}h{s % 3600 // 60:02d}m" if s >= 3600 else f"{s // 60}m{s % 60:02d}s"

    def prog(self, frac=None, text=None, eta=None, reset=False):
        """Thread-safe progress update. frac 0..1 only moves forward (unless reset); text = current stage;
        eta = seconds left when the step knows it (e.g. the renderer), otherwise estimated from the pace."""
        j = self._job
        if not j:
            return
        if frac is not None:
            frac = max(0.0, min(1.0, float(frac)))
            j["frac"] = frac if reset else max(j["frac"], frac)
        if text is not None:
            j["text"] = text
        j["eta"] = eta
        self.ui(self._paint_progress)

    def _paint_progress(self):
        j = self._job
        if not j:
            return
        el = time.time() - j["t0"]
        self.lbl_status.configure(text=f"{j['label']} — {j['text']}" if j["text"] else j["label"] + " …")
        if j["indet"]:
            self.lbl_pct.configure(text=f"{self._fmt_t(el)} elapsed")
            return
        f = j["frac"]
        self.progress.set(f)
        eta = j.get("eta")
        if eta is None and f >= 0.03 and el > 8:
            eta = el * (1 - f) / f
        self.lbl_pct.configure(text=f"{f * 100:4.0f}%  ·  {self._fmt_t(el)}"
                               + (f"  ·  ~{self._fmt_t(eta)} left" if eta is not None and f < 1 else ""))

    def _tick(self):
        if self._job and self.busy:
            self._paint_progress()
            self.after(1000, self._tick)

    def check_cancel(self):
        if self._cancel:
            raise RuntimeError("Stopped.")

    def run_job(self, label, fn, done=None, indeterminate=False):
        if self.busy:
            messagebox.showinfo("Busy", "Another task is running. Wait for it or press Stop.")
            return
        self.busy = True
        self._cancel = False
        self._job = {"label": label, "t0": time.time(), "frac": 0.0, "text": "", "eta": None, "indet": indeterminate}
        self.progress.configure(mode="indeterminate" if indeterminate else "determinate")
        if indeterminate:
            self.progress.start()
        else:
            self.progress.set(0)
        self.btn_stop.configure(state="normal")
        self._paint_progress()
        self.after(1000, self._tick)

        def worker():
            err, res = None, None
            try:
                res = fn()
            except Exception as e:
                err = e
                traceback.print_exc()

            def finish():
                el = time.time() - self._job["t0"] if self._job else 0
                self.busy = False
                self.proc = None
                self._job = None
                self.progress.stop()
                self.progress.configure(mode="determinate")
                self.btn_stop.configure(state="disabled")
                if err:
                    self.lbl_status.configure(text=f"{label}: {'stopped' if self._cancel else 'failed'}")
                    self.lbl_pct.configure(text=f"after {self._fmt_t(el)}")
                    if not self._cancel:
                        messagebox.showerror(label, str(err)[:1500])
                else:
                    self.progress.set(1)
                    self.lbl_status.configure(text=f"{label}: done")
                    self.lbl_pct.configure(text=f"100%  ·  took {self._fmt_t(el)}")
                    if done:
                        done(res)
            self.ui(finish)
        threading.Thread(target=worker, daemon=True).start()

    def stop_job(self):
        self._cancel = True
        if self.proc and self.proc.poll() is None:
            subprocess.run(["taskkill", "/PID", str(self.proc.pid), "/T", "/F"], capture_output=True,
                           creationflags=NO_WINDOW)
        self.status("Stopping…")

    def run_cmd(self, cmd, cwd=None, stdin_text=None, on_line=None):
        self.proc = subprocess.Popen(
            cmd, cwd=cwd, env=ENV, stdin=subprocess.PIPE if stdin_text is not None else subprocess.DEVNULL,
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding="utf-8", errors="replace",
            creationflags=NO_WINDOW)
        if stdin_text is not None:
            self.proc.stdin.write(stdin_text)
            self.proc.stdin.close()
        for line in self.proc.stdout:
            if on_line:
                on_line(line.rstrip("\n"))
        return self.proc.wait()

    def ask_claude(self, prompt, box=None, tools=None, full_auto=False, cwd=None, expect_chars=None, on_tool=None):
        """Run `claude -p` headless, stream progress into box, return the final result text.
        expect_chars: roughly how long the answer is, so the bar can follow the text as it is written.
        on_tool(name, input): called for every tool Claude uses (the Animate page uses it for stages)."""
        exe = claude_exe()
        if not exe:
            raise RuntimeError("Claude Code CLI not found. Go to Setup and install / log in.")
        cmd = [exe, "-p", "--output-format", "stream-json", "--verbose"]
        if expect_chars:
            cmd.append("--include-partial-messages")
        if full_auto:
            cmd.append("--dangerously-skip-permissions")
        elif tools:
            cmd += ["--allowedTools", ",".join(tools)]
        result = {"text": "", "error": False}
        written = {"n": 0}
        if expect_chars:
            self.prog(0.02, "starting Claude")

        def on_line(line):
            if not line.strip():
                return
            try:
                ev = json.loads(line)
            except ValueError:
                if box is not None:
                    self.log(box, line)
                return
            t = ev.get("type")
            if t == "stream_event" and expect_chars:
                e = ev.get("event", {})
                d = e.get("delta", {}) if e.get("type") == "content_block_delta" else {}
                if d.get("type") == "text_delta":
                    written["n"] += len(d.get("text", ""))
                    n = written["n"]
                    self.prog(min(0.97, 0.06 + 0.91 * n / expect_chars), f"writing… {n // 6:,} words")
                elif d.get("type") == "thinking_delta":
                    self.prog(0.05, "thinking…")
                return
            if t == "assistant" and on_tool:
                for c in ev.get("message", {}).get("content", []):
                    if c.get("type") == "tool_use":
                        on_tool(c.get("name", ""), c.get("input", {}))
            if t == "assistant" and box is not None:
                for c in ev.get("message", {}).get("content", []):
                    if c.get("type") == "text" and c.get("text", "").strip():
                        self.log(box, "💬 " + c["text"].strip())
                    elif c.get("type") == "tool_use":
                        inp = c.get("input", {})
                        detail = inp.get("command") or inp.get("file_path") or inp.get("skill") or inp.get("pattern") or ""
                        self.log(box, f"🔧 {c.get('name')}: {str(detail)[:160]}")
            elif t == "result":
                result["text"] = ev.get("result", "") or ""
                result["error"] = bool(ev.get("is_error"))
                if box is not None:
                    cost = ev.get("total_cost_usd")
                    self.log(box, f"✔ finished in {ev.get('num_turns', '?')} turns"
                             + (f", ${cost:.2f}" if isinstance(cost, (int, float)) else ""))
        if cwd is None:
            cwd = STUDIO if STUDIO.exists() else HOME
        rc = self.run_cmd(cmd, cwd=str(cwd), stdin_text=prompt, on_line=on_line)
        if rc != 0 and not result["text"]:
            raise RuntimeError(f"Claude exited with code {rc}. If you are not logged in, use Setup → Log in to Claude.")
        if result["error"]:
            msg = result["text"] or "Claude reported an error."
            if "login" in msg.lower() or "logged in" in msg.lower():
                msg += "\n\nGo to ⚙ Setup → “Log in to Claude”, sign in once, then try again."
            raise RuntimeError(msg)
        return result["text"]

    # ------------------------------------------------------------------ state
    def save_state(self):
        self.settings["current"] = self.s
        save_settings(self.settings)
        if self.s.get("slug"):
            d = WORK / self.s["slug"]
            d.mkdir(parents=True, exist_ok=True)
            (d / "project.json").write_text(json.dumps(self.s, indent=2), encoding="utf-8")
        self._refresh_current()

    def _refresh_current(self):
        if hasattr(self, "lbl_current"):
            self.lbl_current.configure(text=self.s.get("title") or "—")

    def new_video(self):
        if self.s and not messagebox.askyesno("New video", "Start a new video? (The current one stays saved in work\\)"):
            return
        self.s = {}
        self.ideas = []
        self.save_state()
        self.txt_script.delete("1.0", "end")
        self._render_ideas()
        self.show("script")

    # ================================================================== SETUP PAGE
    def _page_setup(self, p):
        self.header(p, "Setup & Tools", "Everything the pipeline needs. Green = ready. "
                    "Use Auto-fix if something is missing, then log in to Claude once.")
        c = self.card(p)
        self.checks_frame = ctk.CTkFrame(c, fg_color="transparent")
        self.checks_frame.pack(fill="x", padx=16, pady=14)
        row = ctk.CTkFrame(p, fg_color="transparent")
        row.pack(fill="x", pady=8)
        for txt, cmd in [("↻ Re-check", self.check_setup), ("🛠 Auto-fix (doctor --install)", self.doctor_fix),
                         ("🔑 Log in to Claude", self.claude_login), ("🧪 Self-test render", self.self_test),
                         ("📦 Re-run installer", self.rerun_installer)]:
            ctk.CTkButton(row, text=txt, height=38, command=cmd).pack(side="left", padx=(0, 8))
        self.setup_log = self.logbox(p, 300)
        self.setup_log.pack(fill="both", expand=True, pady=(8, 0))

    def check_setup(self):
        n_checks = {"i": 0}

        def probe(cmd):
            n_checks["i"] += 1
            self.prog(n_checks["i"] / 6, f"checking {Path(cmd[0]).stem}")
            try:
                r = subprocess.run(cmd, capture_output=True, text=True, timeout=20, env=ENV, creationflags=NO_WINDOW)
                return (r.stdout or r.stderr).strip().splitlines()[0] if r.returncode == 0 else None
            except Exception:
                return None

        def work():
            items = [
                ("Node.js", probe(["node", "--version"]) if which("node") else None),
                ("Python", sys.version.split()[0]),
                ("FFmpeg", "found" if which("ffmpeg") and which("ffprobe") else None),
                ("Git", probe(["git", "--version"]) if which("git") else None),
                ("Claude Code CLI", probe([claude_exe(), "--version"]) if claude_exe() else None),
                ("GrowKaz studio kit", str(STUDIO) if (STUDIO / "render.mjs").exists() else None),
                ("three.js + Playwright", "installed" if (STUDIO / "node_modules" / "three").exists()
                 and (STUDIO / "node_modules" / "playwright").exists() else None),
                ("Claude skills (make-2d-video, scriptforge)", "installed" if (SKILLS_DIR / "make-2d-video" / "SKILL.md").exists()
                 and (SKILLS_DIR / "scriptforge" / "SKILL.md").exists() else None),
            ]
            for mod, label in [("faster_whisper", "faster-whisper"), ("edge_tts", "edge-tts (voices)"),
                               ("googleapiclient", "YouTube API client"), ("PIL", "Pillow (thumbnails)")]:
                try:
                    __import__(mod)
                    items.append((label, "installed"))
                except Exception:
                    items.append((label, None))
            items.append(("YouTube connected", "yes" if (YT_DIR / "token.json").exists() else
                          ("client_secret.json added" if (YT_DIR / "client_secret.json").exists() else None)))
            return items

        def show(items):
            for w in self.checks_frame.winfo_children():
                w.destroy()
            for i, (name, val) in enumerate(items):
                r, col = divmod(i, 2)
                good = bool(val)
                ctk.CTkLabel(self.checks_frame, text=("●" if good else "○"), width=20,
                             text_color=(ACCENT if good else "#ef4444"),
                             font=ctk.CTkFont(size=16)).grid(row=r, column=col * 3, sticky="w", pady=3)
                ctk.CTkLabel(self.checks_frame, text=name, font=ctk.CTkFont(size=14, weight="bold"),
                             anchor="w", width=260).grid(row=r, column=col * 3 + 1, sticky="w")
                ctk.CTkLabel(self.checks_frame, text=(val or "missing")[:40], text_color="#8b94a3",
                             anchor="w", width=220).grid(row=r, column=col * 3 + 2, sticky="w")
        self.run_job("Checking tools", work, show)

    def doctor_fix(self):
        def work():
            self.log(self.setup_log, "> pip install (app libraries)")
            seen = {"n": 0}

            def pip_line(l):   # ~60 packages get resolved in total; each one is a step
                self.log(self.setup_log, l)
                if l.startswith(("Collecting", "Requirement already satisfied")):
                    seen["n"] += 1
                    self.prog(min(0.55, 0.55 * seen["n"] / 60), f"Python packages ({seen['n']} checked)")
                elif l.startswith("Installing collected"):
                    self.prog(0.58, "installing Python packages")
            self.run_cmd([PY, "-m", "pip", "install", "--upgrade", "numpy", "scipy", "faster-whisper", "edge-tts",
                          "customtkinter", "pillow", "google-api-python-client", "google-auth-oauthlib",
                          "google-auth-httplib2"], on_line=pip_line)
            self.check_cancel()
            if STUDIO.exists():
                self.prog(0.62, "applying the browser/progress patch")
                self.run_cmd([PY, str(APP_DIR / "patch_kit.py"), str(STUDIO)], on_line=lambda l: self.log(self.setup_log, l))
                self.prog(0.7, "studio doctor (npm, browser, Whisper)")
                self.log(self.setup_log, "> python tools/doctor.py --install")
                self.run_cmd([PY, "tools/doctor.py", "--install"], cwd=str(STUDIO),
                             on_line=lambda l: (self.log(self.setup_log, l),
                                                l.startswith(">>>") and self.prog(0.8, l[4:60])))
            else:
                self.log(self.setup_log, "Studio kit missing — run the installer (Re-run installer).")
        self.run_job("Auto-fix", work, lambda _: self.check_setup())

    def claude_login(self):
        exe = claude_exe()
        if not exe:
            if messagebox.askyesno("Claude Code", "Claude Code is not installed. Install it now (official installer)?"):
                subprocess.Popen(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-NoExit", "-Command",
                                  "irm https://claude.ai/install.ps1 | iex; Write-Host 'Now type: claude'"],
                                 creationflags=subprocess.CREATE_NEW_CONSOLE)
            return
        messagebox.showinfo("Log in to Claude", "A Claude Code window will open.\n\n"
                            "Sign in when asked (or type /login), then type /exit and close that window.")
        # pass the exe as its own argument: embedding quotes made Python escape them as \" and cmd failed
        subprocess.Popen(["cmd", "/k", exe], cwd=str(STUDIO if STUDIO.exists() else HOME), env=ENV,
                         creationflags=subprocess.CREATE_NEW_CONSOLE)

    def self_test(self):
        if not STUDIO.exists():
            messagebox.showerror("Self-test", "Studio kit not installed.")
            return

        def work():
            sheets = STUDIO / "examples" / "reaction-time" / "build" / "sheets"
            shutil.rmtree(sheets, ignore_errors=True)
            try:   # the example has 14 shots; count the stills as they appear
                total = len(json.loads((STUDIO / "examples/reaction-time/story/shots.json").read_text(encoding="utf-8"))["shots"])
            except Exception:
                total = 14
            stop = threading.Event()

            def watch():
                self.prog(0.03, "starting the browser")
                while not stop.wait(0.5):
                    n = len(list(sheets.glob("s[0-9]*.png"))) if sheets.is_dir() else 0
                    if n:
                        self.prog(0.05 + 0.85 * n / total, f"rendering still {n}/{total}")
            threading.Thread(target=watch, daemon=True).start()
            try:
                self.run_cmd(["node", "render.mjs", "--project", "examples/reaction-time", "--sheet", "--scale", "0.3"],
                             cwd=str(STUDIO), on_line=lambda l: self.log(self.setup_log, l))
            finally:
                stop.set()
            self.prog(0.97, "contact sheet")
            sheet = sheets / "sheet_01.png"
            if not sheet.exists():
                raise RuntimeError("No contact sheet was produced — see the log.")
            return sheet
        self.run_job("Self-test render", work, open_path)

    def rerun_installer(self):
        inst = HOME / "Install-2D-Studio.cmd"
        if inst.exists():
            subprocess.Popen(["cmd", "/c", "start", "", str(inst)], cwd=str(HOME))
        else:
            messagebox.showinfo("Installer", f"Installer not found in {HOME}")

    # ================================================================== SCRIPT PAGE
    def _page_script(self, p):
        self.header(p, "① Script — ScriptForge", "Pick a niche, get 10 ideas from Claude, choose one, "
                    "and get a full narrated script with titles, tags and thumbnail text.")
        top = self.card(p)
        top.grid_columnconfigure(5, weight=1)
        ctk.CTkLabel(top, text="Niche").grid(row=0, column=0, padx=(16, 6), pady=14)
        self.opt_main = ctk.CTkOptionMenu(top, values=list(NICHES), width=210, command=self._on_main)
        self.opt_main.grid(row=0, column=1, pady=14)
        self.opt_sub = ctk.CTkOptionMenu(top, values=NICHES["1. SELF-IMPROVEMENT"] + [CUSTOM], width=330,
                                         command=self._on_sub)
        self.opt_sub.grid(row=0, column=2, padx=8)
        self.ent_custom = ctk.CTkEntry(top, placeholder_text="Type your own sub-niche", width=230)
        self.opt_len = ctk.CTkOptionMenu(top, values=["Shorts 60s", "2 min", "3-4 min", "5 min", "6 min",
                                                      "8 min", "10 min", "12 min"], width=110)
        self.opt_len.set("3-4 min")
        self.opt_len.grid(row=0, column=4, padx=8)
        ctk.CTkButton(top, text="✨ Get 10 ideas", height=36, command=self.get_ideas).grid(row=0, column=6, padx=16)

        body = ctk.CTkFrame(p, fg_color="transparent")
        body.pack(fill="both", expand=True, pady=(6, 0))
        body.grid_columnconfigure(0, weight=2)
        body.grid_columnconfigure(1, weight=3)
        body.grid_rowconfigure(0, weight=1)
        left = ctk.CTkFrame(body, fg_color=CARD_BG, corner_radius=14)
        left.grid(row=0, column=0, sticky="nsew", padx=(0, 8))
        ctk.CTkLabel(left, text="Ideas", font=ctk.CTkFont(size=16, weight="bold")).pack(anchor="w", padx=14, pady=(12, 4))
        self.ideas_frame = ctk.CTkScrollableFrame(left, fg_color="transparent")
        self.ideas_frame.pack(fill="both", expand=True, padx=6, pady=(0, 6))
        ctk.CTkButton(left, text="↻ 10 more ideas", fg_color="#1d222b", hover_color="#272d38",
                      command=lambda: self.get_ideas(more=True)).pack(fill="x", padx=12, pady=(0, 12))

        right = ctk.CTkFrame(body, fg_color=CARD_BG, corner_radius=14)
        right.grid(row=0, column=1, sticky="nsew")
        hdr = ctk.CTkFrame(right, fg_color="transparent")
        hdr.pack(fill="x", padx=14, pady=(12, 4))
        ctk.CTkLabel(hdr, text="Script (editable)", font=ctk.CTkFont(size=16, weight="bold")).pack(side="left")
        ctk.CTkButton(hdr, text="Next: Voiceover →", width=150, command=self.script_next).pack(side="right")
        ctk.CTkButton(hdr, text="📂 Load script…", width=120, fg_color="#1d222b", hover_color="#272d38",
                      command=self.load_script).pack(side="right", padx=6)
        self.txt_script = ctk.CTkTextbox(right, wrap="word", font=ctk.CTkFont(size=13), fg_color="#0d0f13")
        self.txt_script.pack(fill="both", expand=True, padx=12, pady=(0, 6))
        rev = ctk.CTkFrame(right, fg_color="transparent")
        rev.pack(fill="x", padx=12, pady=(0, 12))
        self.ent_revise = ctk.CTkEntry(rev, placeholder_text="Ask for edits: e.g. 'more dramatic hook', 'make a 60s Shorts version'")
        self.ent_revise.pack(side="left", fill="x", expand=True)
        ctk.CTkButton(rev, text="Revise", width=90, command=self.revise_script).pack(side="left", padx=(6, 0))
        if self.s.get("script"):
            self.txt_script.insert("1.0", self.s["script"])
        self.ideas = self.s.get("ideas", [])
        self._render_ideas()

    def _on_main(self, v):
        self.opt_sub.configure(values=NICHES[v] + [CUSTOM])
        self.opt_sub.set(NICHES[v][0])
        self._on_sub(NICHES[v][0])

    def _on_sub(self, v):
        if v == CUSTOM:
            self.ent_custom.grid(row=0, column=3, padx=4)
        else:
            self.ent_custom.grid_forget()

    def _niche(self):
        sub = self.opt_sub.get()
        if sub == CUSTOM:
            sub = self.ent_custom.get().strip() or "General"
        return self.opt_main.get(), sub

    def get_ideas(self, more=False):
        main, sub = self._niche()
        avoid = [i["title"] for i in self.ideas] if more else []
        prompt = (f"{scriptforge_prompt()}\n\n---\nYou are running inside a desktop app, not a chat: skip greetings, "
                  f"menus and questions. The user picked main niche {main}, sub-niche: {sub}. Do STEP 2 now.\n"
                  + (f"Do not repeat these titles: {json.dumps(avoid)}\n" if avoid else "")
                  + 'Return ONLY a JSON array of exactly 10 objects: [{"title": "...", "hook": "...", "format": "listicle|deep-dive|truth-about|countdown|story"}]. No other text.')

        def work():
            return extract_json(self.ask_claude(prompt, cwd=HOME, expect_chars=1900), "[")

        def done(ideas):
            self.ideas = ideas
            self.s.update({"niche_main": main, "niche_sub": sub, "ideas": ideas})
            self.save_state()
            self._render_ideas()
        self.run_job("Generating ideas", work, done)

    def _render_ideas(self):
        for w in self.ideas_frame.winfo_children():
            w.destroy()
        if not self.ideas:
            ctk.CTkLabel(self.ideas_frame, text="Pick a niche and press “Get 10 ideas”.", text_color="#7c8594").pack(pady=30)
        for i, idea in enumerate(self.ideas, 1):
            f = ctk.CTkFrame(self.ideas_frame, fg_color="#1d222b", corner_radius=10)
            f.pack(fill="x", pady=4, padx=4)
            ctk.CTkLabel(f, text=f"{i}. {idea.get('title', '')}", font=ctk.CTkFont(size=14, weight="bold"),
                         wraplength=360, justify="left", anchor="w").pack(anchor="w", padx=10, pady=(8, 0))
            ctk.CTkLabel(f, text=idea.get("hook", ""), text_color="#9aa3b2", wraplength=360, justify="left",
                         anchor="w").pack(anchor="w", padx=10)
            ctk.CTkButton(f, text="Write this script →", height=28, width=150,
                          command=lambda d=idea: self.write_script(d)).pack(anchor="e", padx=10, pady=8)

    SCRIPT_FORMAT = (
        "Output exactly three sections, each starting with its marker line:\n"
        "===SCRIPT===\n(the full formatted script exactly per the FORMAT rules, incl. timestamps, [NARRATION], [VISUAL] and tone notes)\n"
        "===NARRATION===\n(ONLY the words to be spoken, in order, as plain text paragraphs: no headers, timestamps, brackets, "
        "stage directions or (pause) notes. This is fed to a text-to-speech voice and used to align the animation, "
        "so it must match the [NARRATION] text word for word.)\n"
        "===META===\n(one JSON object: {\"title\": \"best final title\", \"alt_titles\": [3 strings], "
        "\"thumbnail_text\": \"2-4 words\", \"tags\": [5+ strings], \"description\": \"YouTube description: 2-3 short "
        "paragraphs, then 3-5 hashtags\", \"word_count\": number, \"runtime\": \"m:ss\"})\n"
        "Do not ask follow-up questions and add nothing after the JSON.")

    def write_script(self, idea):
        main, sub = self.s.get("niche_main") or self._niche()[0], self.s.get("niche_sub") or self._niche()[1]
        choice = self.opt_len.get()
        shorts = choice.startswith("Shorts")
        if shorts:
            length = ("This is a YouTube SHORTS version: 60 seconds, about 140-160 words, same structure compressed "
                      "(hook in the first 2 seconds).")
        elif choice == "3-4 min":
            length = "Standard 3-4 minute length (450-600 words)."
        else:
            mins = int(choice.split()[0])
            length = (f"LENGTH OVERRIDE: the user wants a {mins}-minute video, about {mins * 150} words at 150 wpm. "
                      f"Scale the SCRIPT STRUCTURE timestamps proportionally (hook still ~15 s, more main-body beats).")
        prompt = (f"{scriptforge_prompt()}\n\n---\nYou are running inside a desktop app, not a chat. The user picked main "
                  f"niche {main}, sub-niche {sub}, and chose this idea:\nTitle: {idea.get('title')}\nHook: {idea.get('hook')}\n"
                  f"Do STEP 3 now. {length}\n\n{self.SCRIPT_FORMAT}")
        words = 150 if shorts else 525 if choice == "3-4 min" else int(choice.split()[0]) * 150
        self._script_request(prompt, idea.get("title", "video"), shorts, words)

    def revise_script(self):
        req = self.ent_revise.get().strip()
        cur = self.txt_script.get("1.0", "end").strip()
        if not req or not cur:
            return
        shorts = "short" in req.lower() or self.s.get("shorts", False)
        prompt = (f"{scriptforge_prompt()}\n\n---\nYou are running inside a desktop app. Here is the current script:\n\n{cur}\n\n"
                  f"The user asks: {req}\nRewrite it accordingly, keeping the ScriptForge rules.\n\n{self.SCRIPT_FORMAT}")
        words = 150 if "short" in req.lower() else max(150, len(self.s.get("narration", cur).split()))
        self._script_request(prompt, self.s.get("title", "video"), shorts, words)

    def _script_request(self, prompt, fallback_title, shorts, words=525):
        # SCRIPT (narration + visual cues + headers) + NARRATION again + META JSON ≈ 2.4× the spoken text
        expect = int(words * 6 * 2.4 + 900)

        def work():
            return self.ask_claude(prompt, cwd=HOME, expect_chars=expect)

        def done(text):
            parts = re.split(r"^===(SCRIPT|NARRATION|META)===\s*$", text, flags=re.M)
            sec = {parts[i]: parts[i + 1].strip() for i in range(1, len(parts) - 1, 2)}
            script = sec.get("SCRIPT", text.strip())
            narration = sec.get("NARRATION") or self._narration_from_script(script)
            try:
                meta = extract_json(sec.get("META", "{}"), "{")
            except Exception:
                meta = {}
            title = meta.get("title") or fallback_title
            slug = self.s.get("slug") or (slugify(title) + datetime.now().strftime("-%m%d%H%M"))
            self.s.update({"script": script, "narration": narration, "meta": meta, "title": title,
                           "slug": slug, "shorts": shorts})
            self.txt_script.delete("1.0", "end")
            self.txt_script.insert("1.0", script + self._meta_block(meta))
            self.save_state()
        self.run_job("Writing script", work, done)

    @staticmethod
    def _meta_block(meta):
        if not meta:
            return ""
        return ("\n\n──────── extras ────────\n"
                f"Alt titles: {' | '.join(meta.get('alt_titles', []))}\n"
                f"Thumbnail text: {meta.get('thumbnail_text', '')}\n"
                f"Tags: {', '.join(meta.get('tags', []))}\n"
                f"Words / runtime: {meta.get('word_count', '?')} / {meta.get('runtime', '?')}\n")

    @staticmethod
    def _narration_from_script(script):
        out, take = [], False
        for line in script.splitlines():
            s = line.strip()
            if s.upper().startswith("[NARRATION]"):
                take, s = True, s[len("[NARRATION]"):].strip()
            elif s.startswith("[") or s.startswith("#") or s.startswith("──"):
                take = False
                continue
            if take and s:
                out.append(re.sub(r"\((?:pause|[^)]{0,40})\)", "", s).replace("*", "").strip())
        return "\n".join(x for x in out if x)

    def load_script(self):
        f = filedialog.askopenfilename(filetypes=[("Text", "*.txt *.md *.srt *.vtt"), ("All", "*.*")])
        if not f:
            return
        text = Path(f).read_text(encoding="utf-8", errors="replace")
        title = Path(f).stem
        self.s.update({"script": text, "narration": self._narration_from_script(text) or text, "title": title,
                       "slug": slugify(title) + datetime.now().strftime("-%m%d%H%M"), "meta": {}})
        self.txt_script.delete("1.0", "end")
        self.txt_script.insert("1.0", text)
        self.save_state()

    def script_next(self):
        text = self.txt_script.get("1.0", "end").strip()
        if not text:
            messagebox.showinfo("Script", "Write or load a script first.")
            return
        text = text.split("\n\n──────── extras ────────")[0]
        if text != self.s.get("script"):
            self.s["script"] = text
            self.s["narration"] = self._narration_from_script(text) or self.s.get("narration") or text
        if not self.s.get("slug"):
            self.s["title"] = self.s.get("title") or "My video"
            self.s["slug"] = slugify(self.s["title"]) + datetime.now().strftime("-%m%d%H%M")
        self.save_state()
        self.show("voice")

    # ================================================================== VOICE PAGE
    def _page_voice(self, p):
        self.header(p, "② Voiceover", "Generate a natural AI voice from the narration — free Microsoft Edge "
                    "neural voices or ElevenLabs (your API key) — or use your own recording.")
        eng = self.card(p)
        ctk.CTkLabel(eng, text="Voice engine").grid(row=0, column=0, padx=(16, 6), pady=12)
        self.opt_engine = ctk.CTkSegmentedButton(eng, values=["Free (Edge)", "ElevenLabs"], command=self._on_engine)
        self.opt_engine.grid(row=0, column=1, padx=(0, 16))
        self.el_frame = ctk.CTkFrame(eng, fg_color="transparent")
        ctk.CTkLabel(self.el_frame, text="API key").pack(side="left")
        self.ent_el_key = ctk.CTkEntry(self.el_frame, width=230, show="•", placeholder_text="paste your ElevenLabs key")
        self.ent_el_key.pack(side="left", padx=6)
        if self.settings.get("el_key"):
            self.ent_el_key.insert(0, self.settings["el_key"])
        ctk.CTkButton(self.el_frame, text="Load voices", width=100, command=self.el_load_voices).pack(side="left", padx=4)
        self.opt_el_voice = ctk.CTkOptionMenu(self.el_frame, values=self.settings.get("el_voices_names") or ["(load voices)"],
                                              width=220)
        self.opt_el_voice.set(self.settings.get("el_voice_name") or "(load voices)")
        self.opt_el_voice.pack(side="left", padx=4)
        ctk.CTkButton(self.el_frame, text="Get a key", width=80, fg_color="#1d222b", hover_color="#272d38",
                      command=lambda: webbrowser.open("https://elevenlabs.io/app/settings/api-keys")).pack(side="left", padx=4)
        self.el_voices = dict(zip(self.settings.get("el_voices_names", []), self.settings.get("el_voices_ids", [])))
        c = self.card(p)
        self.edge_label = ctk.CTkLabel(c, text="Edge voice")
        self.edge_label.grid(row=0, column=0, padx=(16, 6), pady=14)
        self.opt_voice = ctk.CTkOptionMenu(c, values=VOICES, width=240)
        self.opt_voice.set(self.settings.get("voice", VOICES[0]))
        self.opt_voice.grid(row=0, column=1)
        ctk.CTkLabel(c, text="Speed").grid(row=0, column=2, padx=(18, 6))
        self.sld_rate = ctk.CTkSlider(c, from_=-30, to=30, number_of_steps=12, width=160,
                                      command=lambda v: self.lbl_rate.configure(text=f"{int(v):+d}%"))
        self.sld_rate.set(self.settings.get("rate", -5))
        self.sld_rate.grid(row=0, column=3)
        self.lbl_rate = ctk.CTkLabel(c, text=f"{int(self.sld_rate.get()):+d}%", width=50)
        self.lbl_rate.grid(row=0, column=4)
        ctk.CTkButton(c, text="🎙 Generate voiceover", height=36, command=self.make_voice).grid(row=0, column=5, padx=12)
        ctk.CTkButton(c, text="📂 Use my recording…", height=36, fg_color="#1d222b", hover_color="#272d38",
                      command=self.pick_voice).grid(row=0, column=6, padx=(0, 16))

        ctk.CTkLabel(p, text="Narration text (exactly what is spoken — edit freely)",
                     font=ctk.CTkFont(size=15, weight="bold")).pack(anchor="w", pady=(10, 4))
        self.txt_narr = ctk.CTkTextbox(p, wrap="word", font=ctk.CTkFont(size=14), fg_color=CARD_BG, height=360)
        self.txt_narr.pack(fill="both", expand=True)
        bot = ctk.CTkFrame(p, fg_color="transparent")
        bot.pack(fill="x", pady=10)
        self.lbl_voice = ctk.CTkLabel(bot, text="No voiceover yet", text_color="#8b94a3")
        self.lbl_voice.pack(side="left")
        ctk.CTkButton(bot, text="Next: Animate →", width=150, command=lambda: self.show("animate")).pack(side="right")
        ctk.CTkButton(bot, text="▶ Play", width=90, fg_color="#1d222b", hover_color="#272d38",
                      command=lambda: self.s.get("voice") and open_path(self.s["voice"])).pack(side="right", padx=8)
        self.opt_engine.set(self.settings.get("engine", "Free (Edge)"))
        self._on_engine(self.opt_engine.get())

    def _on_engine(self, v):
        if v == "ElevenLabs":
            self.el_frame.grid(row=0, column=2, sticky="w", pady=8)
        else:
            self.el_frame.grid_forget()
        state = "disabled" if v == "ElevenLabs" else "normal"
        self.opt_voice.configure(state=state)
        self.settings["engine"] = v

    def _el_request(self, path, payload=None):
        import urllib.request
        key = self.ent_el_key.get().strip()
        if not key:
            raise RuntimeError("Paste your ElevenLabs API key first.")
        req = urllib.request.Request("https://api.elevenlabs.io" + path, method="POST" if payload else "GET",
                                     data=json.dumps(payload).encode() if payload else None,
                                     headers={"xi-api-key": key, "Content-Type": "application/json",
                                              "Accept": "audio/mpeg" if payload else "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=180) as r:
                return r.read()
        except Exception as e:
            body = getattr(e, "read", lambda: b"")()[:300].decode("utf-8", "replace")
            raise RuntimeError(f"ElevenLabs error: {e} {body}")

    def el_load_voices(self):
        def work():
            data = json.loads(self._el_request("/v1/voices"))
            return [(v["name"] + (f" · {v['labels'].get('accent', '')}" if v.get("labels") else ""), v["voice_id"])
                    for v in data.get("voices", [])]

        def done(voices):
            if not voices:
                messagebox.showinfo("ElevenLabs", "No voices found on this account.")
                return
            self.el_voices = dict(voices)
            names = list(self.el_voices)
            self.opt_el_voice.configure(values=names)
            self.opt_el_voice.set(names[0])
            self.settings.update({"el_key": self.ent_el_key.get().strip(), "el_voices_names": names,
                                  "el_voices_ids": [self.el_voices[n] for n in names]})
            save_settings(self.settings)
        self.run_job("Loading ElevenLabs voices", work, done, indeterminate=True)

    @staticmethod
    def _chunks(text, limit=4000):
        paras, out, cur = [p for p in re.split(r"\n\s*\n|\n", text) if p.strip()], [], ""
        for p in paras:
            if len(cur) + len(p) + 2 > limit and cur:
                out.append(cur)
                cur = p
            else:
                cur = (cur + "\n\n" + p).strip()
        if cur:
            out.append(cur)
        return out

    def _make_voice_elevenlabs(self, text, d, out):
        name = self.opt_el_voice.get()
        vid = self.el_voices.get(name)
        if not vid:
            raise RuntimeError("Load your ElevenLabs voices and pick one first.")
        self.settings.update({"el_key": self.ent_el_key.get().strip(), "el_voice_name": name})
        save_settings(self.settings)
        parts = self._chunks(text)
        cache = d / "voice_parts"
        cache.mkdir(exist_ok=True)
        files = []
        for i, chunk in enumerate(parts):
            self.check_cancel()
            self.prog(i / len(parts), f"ElevenLabs passage {i + 1}/{len(parts)}")
            f = cache / ("el_" + hashlib.sha256((vid + "\n" + chunk).encode()).hexdigest()[:24] + ".mp3")
            if not f.exists() or f.stat().st_size == 0:
                audio = self._el_request(f"/v1/text-to-speech/{vid}?output_format=mp3_44100_128",
                                         {"text": chunk, "model_id": "eleven_multilingual_v2",
                                          "voice_settings": {"stability": 0.5, "similarity_boost": 0.75}})
                f.write_bytes(audio)
            files.append(f)
        self.prog(0.97, "Joining passages")
        return self._join_mp3(files, out)

    @staticmethod
    def _speech_chunks(text, limit=1400):
        """Same splitting as reddit-video-generator's narration.py: ~1400-char passages that end on a
        sentence when possible. One long request gets cut off by the Edge voice service."""
        words = text.split()
        chunks, current = [], []
        for word in words:
            if current and len(" ".join(current + [word])) > limit:
                chunks.append(" ".join(current))
                current = []
            current.append(word)
            if len(" ".join(current)) > limit * .65 and word.endswith((".", "!", "?")):
                chunks.append(" ".join(current))
                current = []
        if current:
            chunks.append(" ".join(current))
        return chunks

    def _make_voice_edge(self, text, d, out, voice, rate):
        """Edge neural voice, passage by passage, cached, 3 tries each (as in reddit-video-generator)."""
        import asyncio
        import edge_tts
        rate_s = f"{rate:+d}%"
        parts = self._speech_chunks(text)
        if not parts:
            raise RuntimeError("The narration is empty.")
        cache = d / "voice_parts"
        cache.mkdir(exist_ok=True)
        files = []

        async def download(part, dest):
            await asyncio.wait_for(edge_tts.Communicate(part, voice=voice, rate=rate_s).save(str(dest)), timeout=180)
        for i, part in enumerate(parts):
            self.prog(i / len(parts), f"Voice passage {i + 1}/{len(parts)}")
            mp3 = cache / (hashlib.sha256((voice + "\n" + rate_s + "\n" + part).encode()).hexdigest()[:24] + ".mp3")
            for attempt in range(3):
                self.check_cancel()
                partial = mp3.with_suffix(".partial.mp3")
                try:
                    if not mp3.exists() or mp3.stat().st_size == 0:
                        asyncio.run(download(part, partial))
                        if not partial.is_file() or partial.stat().st_size == 0:
                            raise RuntimeError("no speech received")
                        os.replace(partial, mp3)
                    break
                except Exception as exc:
                    partial.unlink(missing_ok=True)
                    mp3.unlink(missing_ok=True)
                    if attempt == 2:
                        raise RuntimeError(f"The voice service failed on passage {i + 1} of {len(parts)} after 3 tries "
                                           f"({exc}).\n\nPassage starts: “{part[:140]}…”\n\nCheck your internet and try again "
                                           "— finished passages are cached, so it continues where it stopped.")
                    self.prog(i / len(parts), f"Voice passage {i + 1}/{len(parts)} — retry {attempt + 2}/3")
                    time.sleep(attempt + 1)
            files.append(mp3)
        self.prog(0.97, "Joining passages")
        return self._join_mp3(files, out)

    def _join_mp3(self, files, out):
        if len(files) == 1:
            shutil.copy2(files[0], out)
            return out
        lst = Path(out).with_name("voice_parts.txt")
        lst.write_text("".join(f"file '{Path(f).as_posix()}'\n" for f in files), encoding="utf-8")
        r = subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "concat", "-safe", "0", "-i", str(lst),
                            "-c:a", "libmp3lame", "-b:a", "192k", str(out)],
                           capture_output=True, text=True, env=ENV, creationflags=NO_WINDOW)
        lst.unlink(missing_ok=True)
        if r.returncode != 0:
            raise RuntimeError("ffmpeg could not join the voice passages:\n" + (r.stderr or "")[-400:])
        return out

    def _sync_voice_page(self):
        self.txt_narr.delete("1.0", "end")
        self.txt_narr.insert("1.0", self.s.get("narration", ""))
        v = self.s.get("voice")
        self.lbl_voice.configure(text=f"Voiceover: {v}" if v else "No voiceover yet",
                                 text_color=ACCENT if v else "#8b94a3")

    def _workdir(self):
        if not self.s.get("slug"):
            self.s["slug"] = "video" + datetime.now().strftime("-%m%d%H%M")
        d = WORK / self.s["slug"]
        d.mkdir(parents=True, exist_ok=True)
        return d

    def _save_narration(self):
        text = self.txt_narr.get("1.0", "end").strip()
        self.s["narration"] = text
        d = self._workdir()
        f = d / "script.txt"
        f.write_text(text + "\n", encoding="utf-8")
        self.s["script_file"] = str(f)
        return text, d

    def make_voice(self):
        text, d = self._save_narration()
        if not text:
            messagebox.showinfo("Voiceover", "The narration is empty.")
            return
        voice, rate = self.opt_voice.get(), int(self.sld_rate.get())
        self.settings.update({"voice": voice, "rate": rate})
        out = d / "voiceover.mp3"
        use_el = self.opt_engine.get() == "ElevenLabs"

        def work():
            (d / "voiceover.srt").unlink(missing_ok=True)   # leftover from the old single-request method
            if use_el:
                return self._make_voice_elevenlabs(text, d, out)
            return self._make_voice_edge(text, d, out, voice, rate)

        def done(o):
            self.s.update({"voice": str(o), "lang": "detect it from the script text" if use_el else voice.split("-")[0]})
            self.save_state()
            self._sync_voice_page()
        self.run_job("Generating voiceover", work, done)

    def pick_voice(self):
        f = filedialog.askopenfilename(filetypes=[("Audio", "*.mp3 *.wav *.m4a *.flac *.ogg *.aac"), ("All", "*.*")])
        if f:
            self._save_narration()
            self.s["voice"] = f
            self.save_state()
            self._sync_voice_page()

    # ================================================================== ANIMATE PAGE
    def _page_animate(self, p):
        self.header(p, "③ Animate — GrowKaz Stickman Studio", "Claude Code runs the make-2d-video skill end to end: "
                    "timestamps (Whisper), shot plan, code-drawn 2D/3D scenes, render, music, SFX and the final MP4. "
                    "Long videos can take a while — leave it running.")
        c = self.card(p)
        g = ctk.CTkFrame(c, fg_color="transparent")
        g.pack(fill="x", padx=16, pady=14)
        self.lbl_anim_src = ctk.CTkLabel(g, text="", anchor="w", text_color="#8b94a3", wraplength=950, justify="left")
        self.lbl_anim_src.grid(row=0, column=0, columnspan=8, sticky="w", pady=(0, 10))

        def lab(t, r, col):
            ctk.CTkLabel(g, text=t).grid(row=r, column=col, sticky="w", padx=(0, 6), pady=4)
        lab("Aspect", 1, 0)
        self.opt_aspect = ctk.CTkSegmentedButton(g, values=["16:9", "9:16"])
        self.opt_aspect.grid(row=1, column=1, sticky="w", padx=(0, 18))
        lab("Resolution", 1, 2)
        self.opt_res = ctk.CTkOptionMenu(g, values=["720p", "1080p", "1440p", "2160p"], width=110)
        self.opt_res.set("1080p")
        self.opt_res.grid(row=1, column=3, sticky="w", padx=(0, 18))
        lab("Style", 1, 4)
        self.opt_style = ctk.CTkOptionMenu(g, values=list(STYLES), width=170)
        self.opt_style.grid(row=1, column=5, sticky="w", padx=(0, 18))
        lab("Music", 2, 0)
        self.opt_music = ctk.CTkOptionMenu(g, values=["Generated by mood", "My own track…", "None"], width=170,
                                           command=self._on_music)
        self.opt_music.grid(row=2, column=1, sticky="w")
        self.chk_sfx = ctk.CTkCheckBox(g, text="Sound effects")
        self.chk_sfx.select()
        self.chk_sfx.grid(row=2, column=2, columnspan=2, sticky="w")
        self.chk_capt = ctk.CTkCheckBox(g, text="Burned-in captions")
        self.chk_capt.grid(row=2, column=4, sticky="w")
        self.chk_auto = ctk.CTkCheckBox(g, text="Full auto (skip all permission checks)")
        self.chk_auto.grid(row=2, column=5, columnspan=3, sticky="w")
        lab("Parts", 3, 0)
        self.opt_parts = ctk.CTkOptionMenu(g, values=["Auto", "1", "2", "3", "4", "5", "6"], width=90)
        self.opt_parts.set("Auto")
        self.opt_parts.grid(row=3, column=1, sticky="w")
        lab("Look notes", 3, 2)
        self.ent_look = ctk.CTkEntry(g, width=420, placeholder_text="optional: e.g. 'detailed human characters, warm colours'")
        self.ent_look.grid(row=3, column=3, columnspan=3, sticky="w")
        ctk.CTkButton(g, text="🎨 Suggest character styles", width=190, fg_color="#1d222b", hover_color="#272d38",
                      command=self.suggest_characters).grid(row=3, column=6, padx=(10, 0), sticky="w")
        ctk.CTkLabel(g, text="Parts: long videos are built in several Claude passes (Auto = one part per ~2.5 min), "
                             "like splitting the script in the tutorial — then rendered as one final MP4.",
                     text_color="#7c8594", font=ctk.CTkFont(size=11)).grid(row=4, column=0, columnspan=8, sticky="w", pady=(4, 0))
        self.opt_aspect.configure(command=lambda v: self.chk_capt.select() if v == "9:16" else self.chk_capt.deselect())
        self.music_file = None

        row = ctk.CTkFrame(p, fg_color="transparent")
        row.pack(fill="x", pady=8)
        ctk.CTkButton(row, text="🎬 Make the video (automatic)", height=42, font=ctk.CTkFont(size=15, weight="bold"),
                      command=self.make_video).pack(side="left")
        ctk.CTkButton(row, text="💻 Open in Claude Code (interactive)", height=42, fg_color="#1d222b",
                      hover_color="#272d38", command=self.interactive_video).pack(side="left", padx=8)
        ctk.CTkButton(row, text="📁 Project folder", height=42, fg_color="#1d222b", hover_color="#272d38",
                      command=self.open_project).pack(side="left")
        ctk.CTkButton(row, text="Next: Upload →", height=42, width=140,
                      command=lambda: self.show("upload")).pack(side="right")
        self.anim_log = self.logbox(p, 300)
        self.anim_log.pack(fill="both", expand=True)

    def _on_music(self, v):
        if v.startswith("My own"):
            f = filedialog.askopenfilename(filetypes=[("Audio", "*.mp3 *.wav *.m4a *.flac *.ogg")])
            if f:
                self.music_file = f
                self.opt_music.set("Track: " + Path(f).name[:20])
            else:
                self.opt_music.set("Generated by mood")

    def _sync_animate_page(self):
        shorts = self.s.get("shorts")
        if not self.opt_aspect.get():
            self.opt_aspect.set("9:16" if shorts else "16:9")
            (self.chk_capt.select if shorts else self.chk_capt.deselect)()
        if not self.opt_style.get() or self.opt_style.get() not in STYLES:
            self.opt_style.set("Emerald (GrowKaz)")
        if not self.ent_look.get() and self.s.get("look"):
            self._set(self.ent_look, self.s["look"])
        self.lbl_anim_src.configure(
            text=f"Title: {self.s.get('title', '—')}\nVoiceover: {self.s.get('voice', 'not set — go to ② Voiceover')}\n"
                 f"Script: {self.s.get('script_file', 'not saved yet')}")

    def _video_prompt(self):
        if not self.s.get("voice"):
            raise RuntimeError("No voiceover yet. Go to ② Voiceover first.")
        if not self.s.get("script_file"):
            self._save_narration()
        style = STYLES[self.opt_style.get()]
        music = ("none" if self.opt_music.get() == "None" else
                 f"use my own track: {self.music_file}" if self.music_file and self.opt_music.get().startswith("Track")
                 else "generated by mood")
        slug = self.s["slug"]
        look = self.ent_look.get().strip()
        self.s.update({"aspect": self.opt_aspect.get(), "resolution": self.opt_res.get(), "style": style, "look": look})
        self.save_state()
        return f"""Use the make-2d-video skill (GrowKaz Stickman Studio) to make this complete video end to end.

All intake choices are already made. I am away: do NOT ask me anything. At every checkpoint take the defaults,
state your assumption in one line, and continue until the final MP4 exists.

{self._facts(style, music, slug, look)}
"""

    def _facts(self, style, music, slug, look):
        return f"""- Studio: already installed at {STUDIO} (do not copy the kit again). Work only inside it.
  If tools/doctor.py reports anything missing, run "{PY}" tools/doctor.py --install, then continue.
- Python command: "{PY}"
- Voiceover file: {self.s['voice']}
- Script (plain text, the exact narration): {self.s['script_file']}
- Narration language: {self.s.get('lang', 'en')}
- Title: {self.s.get('title', slug)}
- Project slug: {slug}
- Aspect: {self.opt_aspect.get()}   Resolution: {self.opt_res.get()}   FPS: 24
- Captions: {'on' if self.chk_capt.get() else 'off'}
- Music: {music}   SFX: {'on' if self.chk_sfx.get() else 'off'}
- Style: {'render the style grid and pick the best one yourself' if style == 'auto' else style + ' (skip the style-grid checkpoint, set it in config.json)'}
- Character / look notes from me: {look or 'none - use the style bible defaults'}

Follow every golden rule and the style bible. Check the contact sheets yourself before the final render.
Run long renders in the background and poll the log, so no single command runs longer than 10 minutes.
When out/<title>.mp4 is muxed and QC'd, finish with one final line exactly like:
FINAL_VIDEO: <absolute path to the mp4>"""

    def _part_prompts(self, n, dur):
        """Split the build into n Claude passes; files on disk carry state between passes."""
        base = self._video_prompt().split("\n\n", 2)[2]   # facts block only
        slug = self.s["slug"]
        bounds = [round(dur * i / n, 2) for i in range(n + 1)]
        head = ("Use the make-2d-video skill (GrowKaz Stickman Studio). I am away: never ask me anything; take the "
                "defaults at checkpoints. Files are the truth: read what earlier passes wrote before changing anything.\n\n")
        prompts = [head + base.replace("FINAL_VIDEO", "(final pass only) FINAL_VIDEO") +
                   f"\n\nTHIS IS PASS 1 OF {n + 1}. Do stages 1-5 for the WHOLE video (project projects/{slug}, timeline, "
                   f"story/bible.md, scenes/cast.js, the complete story/shots.json, style). Then do stage 6 ONLY for shots "
                   f"that start between {bounds[0]}s and {bounds[1]}s: write their sets/shot files and check their contact "
                   f"sheets. Do NOT do the final render. End with: PASS_DONE"]
        for i in range(1, n):
            prompts.append(head + base.replace("FINAL_VIDEO", "(final pass only) FINAL_VIDEO") +
                           f"\n\nTHIS IS PASS {i + 1} OF {n + 1}. Project projects/{slug} already exists with its bible, cast, "
                           f"shots.json and earlier shots. Read them and the existing scenes so the style stays consistent. "
                           f"Do stage 6 ONLY for shots that start between {bounds[i]}s and {bounds[i + 1]}s. Reuse existing "
                           f"sets. Check their contact sheets. Do NOT do the final render. End with: PASS_DONE")
        prompts.append(head + base +
                       f"\n\nTHIS IS THE FINAL PASS ({n + 1} OF {n + 1}). Project projects/{slug} has every shot built. "
                       f"Render a full contact sheet and fix any MISSING or broken shot first. Then do stage 7 (sound) and "
                       f"stage 8 (preview check, final render, mix, QC) and deliver the MP4.")
        return prompts

    def _voice_duration(self):
        try:
            r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0",
                                self.s["voice"]], capture_output=True, text=True, env=ENV, creationflags=NO_WINDOW)
            return float(r.stdout.strip())
        except Exception:
            return 0.0

    def suggest_characters(self):
        if not self.s.get("voice"):
            messagebox.showinfo("Character styles", "Make the voiceover first (② Voiceover).")
            return
        if not STUDIO.exists():
            messagebox.showerror("Character styles", "Studio kit missing — run the installer from Setup.")
            return
        facts = self._video_prompt().split("\n\n", 2)[2].split("Follow every golden rule")[0]
        slug = self.s["slug"]
        prompt = f"""Use the make-2d-video skill (GrowKaz Stickman Studio). I am away: do not ask me anything.

{facts}
TASK: suggest character designs, do NOT make the video yet.
1. If projects/{slug} does not exist, create it and do stage 3 (timeline) only.
2. Read references/style-bible.md, references/engine-api.md and the narration.
3. Design 4 clearly different character looks that fit this video and the engine (for example: the classic
   rim-lit stick figure, a more detailed human with clothes and hair, a rounded chibi look, and one idea of your own).
4. For each, build a small temporary test project projects/{slug}-charlook-<n> (or a temporary test shot) and render
   one still at --scale 0.5 into projects/{slug}/build/char_styles/<n>.png. Open the PNGs to check them.
5. Do not change the real cast or shots. Finish with one line per option, exactly:
CHAR_STYLE: <n> | <short name> | <one-line description> | <absolute png path>"""
        self.anim_log.delete("1.0", "end")
        self.log(self.anim_log, "🎨 Asking Claude for 4 character designs…")
        tools = ["Bash", "Read", "Write", "Edit", "MultiEdit", "Glob", "Grep", "Skill", "TodoWrite"]

        def work():
            out_dir = STUDIO / "projects" / slug / "build" / "char_styles"
            stop = threading.Event()
            self._anim_hint, t0 = "Claude is reading the skill", time.time()

            def watch():   # 4 stills to make; each one that appears is a quarter of the work
                while not stop.wait(1.5):
                    n = len([p for p in out_dir.glob("*.png") if p.stat().st_mtime >= t0 - 1]) if out_dir.is_dir() else 0
                    self.prog(0.1 + 0.85 * min(n, 4) / 4, f"{n}/4 designs rendered · {self._anim_hint}")
            threading.Thread(target=watch, daemon=True).start()
            try:
                res = self.ask_claude(prompt, box=self.anim_log, tools=tools, full_auto=bool(self.chk_auto.get()),
                                      cwd=STUDIO, on_tool=self._anim_tool_hint)
            finally:
                stop.set()
            opts = []
            for m in re.finditer(r"CHAR_STYLE:\s*(\d+)\s*\|\s*([^|]+)\|\s*([^|]+)\|\s*(.+)", res):
                opts.append((m.group(1), m.group(2).strip(), m.group(3).strip(), m.group(4).strip().strip("`\"")))
            if not opts:
                raise RuntimeError("Claude did not return character options — see the log.")
            return opts
        self.run_job("Designing characters", work, self._pick_character)

    def _pick_character(self, opts):
        win = ctk.CTkToplevel(self)
        win.title("Pick a character style")
        win.geometry("980x640")
        win.transient(self)
        frame = ctk.CTkScrollableFrame(win, fg_color="transparent")
        frame.pack(fill="both", expand=True, padx=10, pady=10)
        win._imgs = []
        for i, (n, name, desc, png) in enumerate(opts):
            card = ctk.CTkFrame(frame, fg_color=CARD_BG, corner_radius=12)
            card.grid(row=i // 2, column=i % 2, padx=8, pady=8, sticky="nsew")
            try:
                from PIL import Image
                im = Image.open(png)
                im.thumbnail((440, 250))
                ci = ctk.CTkImage(light_image=im, dark_image=im, size=im.size)
                win._imgs.append(ci)
                ctk.CTkLabel(card, image=ci, text="").pack(padx=8, pady=8)
            except Exception:
                ctk.CTkLabel(card, text="(no preview)", height=120).pack(padx=8, pady=8)
            ctk.CTkLabel(card, text=f"{n}. {name}", font=ctk.CTkFont(size=15, weight="bold")).pack(anchor="w", padx=12)
            ctk.CTkLabel(card, text=desc, wraplength=420, justify="left", text_color="#9aa3b2").pack(anchor="w", padx=12)

            def choose(n=n, name=name, desc=desc, png=png):
                self._set(self.ent_look, f"Use character design option {n} '{name}': {desc} (reference still: {png})")
                win.destroy()
            ctk.CTkButton(card, text="Use this style", command=choose).pack(anchor="e", padx=12, pady=10)

    def make_video(self):
        try:
            prompt = self._video_prompt()
        except RuntimeError as e:
            messagebox.showinfo("Animate", str(e))
            return
        if not STUDIO.exists():
            messagebox.showerror("Animate", "Studio kit missing — run the installer from Setup.")
            return
        full = bool(self.chk_auto.get())
        tools = ["Bash", "Read", "Write", "Edit", "MultiEdit", "Glob", "Grep", "Skill", "TodoWrite",
                 "BashOutput", "KillShell", "KillBash", "Monitor", "TaskOutput", "TaskStop"]
        dur = self._voice_duration()
        sel = self.opt_parts.get()
        n = max(1, min(6, round(dur / 150))) if sel == "Auto" else int(sel)
        prompts = [prompt] if n == 1 else self._part_prompts(n, dur or 60)
        self.anim_log.delete("1.0", "end")
        self.log(self.anim_log, f"▶ Starting Claude Code in {STUDIO}  —  voiceover {dur:.0f}s, "
                                f"{len(prompts)} pass{'es' if len(prompts) > 1 else ''}")

        def work():
            res = ""
            t0 = time.time()
            stop = threading.Event()
            self._anim_hint = "Claude is reading the skill"
            threading.Thread(target=self._watch_pipeline, args=(self.s["slug"], t0, stop), daemon=True).start()
            try:
                for i, pr in enumerate(prompts, 1):
                    self.check_cancel()
                    if len(prompts) > 1:
                        self.log(self.anim_log, f"\n━━━━━━━━ Pass {i} of {len(prompts)} ━━━━━━━━")
                    self._anim_pass = f"pass {i}/{len(prompts)} · " if len(prompts) > 1 else ""
                    res = self.ask_claude(pr, box=self.anim_log, tools=tools, full_auto=full, cwd=STUDIO,
                                          on_tool=self._anim_tool_hint)
            finally:
                stop.set()
            m = re.search(r"FINAL_VIDEO:\s*(.+\.mp4)", res)
            path = m.group(1).strip().strip('"`') if m else None
            if not path or not Path(path).exists():
                path = self._latest_mp4()
            return path

        def done(path):
            if path:
                self.s["video"] = str(path)
                self.save_state()
                self.log(self.anim_log, f"🎉 Video ready: {path}")
                if messagebox.askyesno("Video ready", f"{path}\n\nOpen it now?"):
                    open_path(path)
            else:
                messagebox.showwarning("Animate", "Claude finished but no MP4 was found. Read the log, "
                                                  "or continue in the interactive Claude Code window.")
        self.run_job("Making the video", work, done)

    # ---- Animate progress: read the pipeline's own files (files are the truth in the GrowKaz skill)
    _anim_hint, _anim_pass = "", ""
    HINTS = [("transcribe.py", "timestamps (Whisper)"), ("parse_script.py", "reading timestamps"),
             ("new_project.py", "creating the project"), ("beats.py", "beat sheet"),
             ("doctor.py", "checking tools"), ("verify_kit.py", "checking the kit"),
             ("--styles", "style samples"), ("--sheet", "checking contact sheets"), ("--stills", "checking stills"),
             ("--from", "preview clip"), ("mix.py", "music, SFX & final mix"), ("render.mjs", "rendering")]

    def _anim_tool_hint(self, name, inp):
        cmd = str(inp.get("command") or "")
        hint = next((h for k, h in self.HINTS if k in cmd), None)
        if not hint:
            f = str(inp.get("file_path") or "").replace("\\", "/")
            if name in ("Write", "Edit", "MultiEdit") and "/scenes/" in f:
                hint = "writing " + f.rsplit("/", 1)[-1]
            elif f.endswith(("bible.md", "shots.json", "cast.js")):
                hint = "story plan (" + f.rsplit("/", 1)[-1] + ")"
            elif name == "Read" and f.endswith(".png"):
                hint = "looking at renders"
            elif name == "Skill":
                hint = "loading the skill"
        if hint:
            self._anim_hint = hint

    def _pipeline_state(self, slug, t0):
        """(fraction, stage text, eta seconds or None) from the project folder."""
        P = STUDIO / "projects" / slug
        fresh = lambda p: p.exists() and p.stat().st_mtime >= t0 - 1
        frac, stage, eta = 0.01, "starting", None
        if (P / "config.json").exists():
            frac, stage = 0.03, "project created"
        tl = P / "timeline"
        if tl.is_dir() and any(tl.iterdir()):
            frac, stage = 0.07, "timestamps ready"
        shots, ids = P / "story" / "shots.json", []
        if (P / "story" / "bible.md").exists():
            frac, stage = 0.10, "story plan"
        try:
            ids = [s["id"] for s in json.loads(shots.read_text(encoding="utf-8")).get("shots", []) if s.get("scene")]
        except Exception:
            pass
        if ids:
            frac, stage = 0.12, f"shot list ({len(ids)} shots)"
        if list((P / "build" / "styles").glob("*.png")) if (P / "build" / "styles").is_dir() else []:
            frac, stage = 0.14, "style chosen"
        built = set()
        for f in (P / "scenes" / "shots").glob("*.js") if (P / "scenes" / "shots").is_dir() else []:
            try:
                built |= set(re.findall(r"registerShot\(\s*['\"]([^'\"]+)", f.read_text(encoding="utf-8")))
            except Exception:
                pass
        if ids and built:
            k = len(built & set(ids))
            frac, stage = 0.15 + 0.45 * k / len(ids), f"building shots {k}/{len(ids)}"
        rp = P / "build" / "render_progress.json"
        if fresh(rp):
            try:
                r = json.loads(rp.read_text(encoding="utf-8"))
                done, total = r.get("done", 0), max(1, r.get("total", 1))
                rate = done / max(1e-3, (r.get("t", 0) - r.get("t0", 0)) / 1000)
                if r.get("full"):
                    frac, stage = 0.60 + 0.32 * done / total, f"rendering frame {done:,}/{total:,} ({rate:.1f} fps)"
                    eta = (total - done) / rate + 60 if rate > 0 else None
                else:
                    stage = f"preview render {done:,}/{total:,} frames"
            except Exception:
                pass
        if fresh(P / "build" / "video_silent.mp4"):
            frac, stage, eta = 0.92, "video rendered — adding sound", None
        if fresh(P / "build" / "mix.wav"):
            frac, stage = max(frac, 0.95), "mixing music & SFX"
        if any(fresh(f) for f in (P / "out").glob("*.mp4")) if (P / "out").is_dir() else False:
            frac, stage = 0.98, "final MP4 written — checking it"
        return frac, stage, eta

    def _watch_pipeline(self, slug, t0, stop):
        while not stop.is_set():
            try:
                frac, stage, eta = self._pipeline_state(slug, t0)
                hint = self._anim_hint
                self.prog(frac, f"{self._anim_pass}{stage}" + (f" · {hint}" if hint and hint not in stage else ""), eta)
            except Exception:
                pass
            stop.wait(2)

    def interactive_video(self):
        try:
            prompt = self._video_prompt().replace("I am away: do NOT ask me anything. At every checkpoint take the defaults,\n"
                                                  "state your assumption in one line, and continue until the final MP4 exists.",
                                                  "Show me the style grid and the preview at the checkpoints.")
        except RuntimeError as e:
            messagebox.showinfo("Animate", str(e))
            return
        f = self._workdir() / "claude_prompt.txt"
        f.write_text(prompt, encoding="utf-8")
        self.clipboard_clear()
        self.clipboard_append(prompt)
        exe = claude_exe()
        if not exe:
            messagebox.showerror("Claude", "Claude Code CLI not found.")
            return
        messagebox.showinfo("Claude Code", "The video prompt is copied to your clipboard.\n\n"
                            "In the Claude Code window that opens, paste it (right-click or Ctrl+V) and press Enter.")
        subprocess.Popen(["cmd", "/k", exe], cwd=str(STUDIO), env=ENV, creationflags=subprocess.CREATE_NEW_CONSOLE)

    def _latest_mp4(self):
        cand = []
        slug = self.s.get("slug")
        base = STUDIO / "projects"
        dirs = [base / slug / "out"] if slug and (base / slug).exists() else []
        dirs += list(base.glob("*/out"))
        for d in dirs:
            cand += list(d.glob("*.mp4"))
        return str(max(cand, key=lambda p: p.stat().st_mtime)) if cand else None

    def open_project(self):
        d = STUDIO / "projects" / self.s.get("slug", "")
        open_path(d if self.s.get("slug") and d.exists() else STUDIO / "projects")

    # ================================================================== UPLOAD PAGE
    def _page_upload(self, p):
        self.header(p, "④ Thumbnail & Upload to YouTube", "Make a thumbnail from a frame of your video, "
                    "fill in the details (pre-filled from the script) and upload straight to your channel.")
        body = ctk.CTkFrame(p, fg_color="transparent")
        body.pack(fill="both", expand=True)
        body.grid_columnconfigure(0, weight=3)
        body.grid_columnconfigure(1, weight=2)
        body.grid_rowconfigure(0, weight=1)
        left = ctk.CTkScrollableFrame(body, fg_color=CARD_BG, corner_radius=14)
        left.grid(row=0, column=0, sticky="nsew", padx=(0, 8))
        right = ctk.CTkFrame(body, fg_color=CARD_BG, corner_radius=14)
        right.grid(row=0, column=1, sticky="nsew")

        def field(label):
            ctk.CTkLabel(left, text=label, font=ctk.CTkFont(size=13, weight="bold")).pack(anchor="w", padx=14, pady=(10, 2))
        field("Video file")
        r = ctk.CTkFrame(left, fg_color="transparent")
        r.pack(fill="x", padx=14)
        self.ent_video = ctk.CTkEntry(r)
        self.ent_video.pack(side="left", fill="x", expand=True)
        ctk.CTkButton(r, text="Browse", width=80, command=lambda: self._browse(self.ent_video, [("Video", "*.mp4 *.mov *.webm")])).pack(side="left", padx=6)
        ctk.CTkButton(r, text="Latest render", width=110, fg_color="#1d222b", hover_color="#272d38",
                      command=lambda: self._set(self.ent_video, self._latest_mp4() or "")).pack(side="left")
        field("Title (max 100)")
        self.ent_title = ctk.CTkEntry(left)
        self.ent_title.pack(fill="x", padx=14)
        field("Description")
        self.txt_desc = ctk.CTkTextbox(left, height=150, wrap="word", fg_color="#0d0f13")
        self.txt_desc.pack(fill="x", padx=14)
        field("Tags (comma separated)")
        self.ent_tags = ctk.CTkEntry(left)
        self.ent_tags.pack(fill="x", padx=14)
        r2 = ctk.CTkFrame(left, fg_color="transparent")
        r2.pack(fill="x", padx=14, pady=(12, 4))
        ctk.CTkLabel(r2, text="Category").pack(side="left")
        self.opt_cat = ctk.CTkOptionMenu(r2, values=list(CATEGORIES), width=170)
        self.opt_cat.set("Education")
        self.opt_cat.pack(side="left", padx=(6, 16))
        r2b = ctk.CTkFrame(left, fg_color="transparent")
        r2b.pack(fill="x", padx=14, pady=4)
        ctk.CTkLabel(r2b, text="Privacy").pack(side="left")
        self.opt_priv = ctk.CTkSegmentedButton(r2b, values=["private", "unlisted", "public"])
        self.opt_priv.set("private")
        self.opt_priv.pack(side="left", padx=6)
        field("Schedule (optional, local time)")
        self.ent_sched = ctk.CTkEntry(left, width=200, placeholder_text="YYYY-MM-DD HH:MM")
        self.ent_sched.pack(anchor="w", padx=14)
        self.chk_kids = ctk.CTkCheckBox(left, text="Made for kids")
        self.chk_kids.pack(anchor="w", padx=14, pady=6)
        r4 = ctk.CTkFrame(left, fg_color="transparent")
        r4.pack(fill="x", padx=14, pady=(10, 14))
        ctk.CTkButton(r4, text="🚀 Upload to YouTube", height=42, font=ctk.CTkFont(size=15, weight="bold"),
                      command=self.upload).pack(side="left")
        ctk.CTkButton(r4, text="🔗 YouTube setup", height=42, fg_color="#1d222b", hover_color="#272d38",
                      command=self.youtube_setup).pack(side="left", padx=8)
        self.lbl_up = ctk.CTkLabel(left, text="", text_color=ACCENT)
        self.lbl_up.pack(anchor="w", padx=14, pady=(0, 10))

        ctk.CTkLabel(right, text="Thumbnail", font=ctk.CTkFont(size=16, weight="bold")).pack(anchor="w", padx=14, pady=(12, 4))
        self.thumb_preview = ctk.CTkLabel(right, text="No thumbnail yet", width=340, height=191, fg_color="#0d0f13",
                                          corner_radius=10)
        self.thumb_preview.pack(padx=14, pady=4)
        ctk.CTkLabel(right, text="Text on thumbnail").pack(anchor="w", padx=14, pady=(8, 2))
        self.ent_thumb_text = ctk.CTkEntry(right)
        self.ent_thumb_text.pack(fill="x", padx=14)
        rr = ctk.CTkFrame(right, fg_color="transparent")
        rr.pack(fill="x", padx=14, pady=4)
        ctk.CTkLabel(rr, text="Frame at").pack(side="left")
        self.sld_frame = ctk.CTkSlider(rr, from_=0, to=100, width=180)
        self.sld_frame.set(35)
        self.sld_frame.pack(side="left", padx=6)
        ctk.CTkLabel(rr, text="% of video").pack(side="left")
        r5 = ctk.CTkFrame(right, fg_color="transparent")
        r5.pack(fill="x", padx=14, pady=8)
        ctk.CTkButton(r5, text="🖼 Make thumbnail", command=self.make_thumb).pack(side="left")
        ctk.CTkButton(r5, text="Browse…", width=80, fg_color="#1d222b", hover_color="#272d38",
                      command=self.pick_thumb).pack(side="left", padx=6)
        self.thumb_path = None

    @staticmethod
    def _set(entry, value):
        entry.delete(0, "end")
        entry.insert(0, value)

    def _browse(self, entry, types):
        f = filedialog.askopenfilename(filetypes=types + [("All", "*.*")])
        if f:
            self._set(entry, f)

    def _sync_upload_page(self):
        meta = self.s.get("meta", {})
        if not self.ent_video.get():
            self._set(self.ent_video, self.s.get("video") or self._latest_mp4() or "")
        if not self.ent_title.get():
            t = self.s.get("title", "")
            self._set(self.ent_title, (t + " #shorts") if self.s.get("shorts") and t else t)
        if not self.txt_desc.get("1.0", "end").strip():
            self.txt_desc.insert("1.0", meta.get("description", ""))
        if not self.ent_tags.get():
            self._set(self.ent_tags, ", ".join(meta.get("tags", [])))
        if not self.ent_thumb_text.get():
            self._set(self.ent_thumb_text, meta.get("thumbnail_text", ""))
        cat = {"4. SCIENCE": "Science & Technology", "3. WHAT IF": "Science & Technology"}.get(self.s.get("niche_main"), "Education")
        self.opt_cat.set(cat)

    def _show_thumb(self, path):
        try:
            from PIL import Image
            img = Image.open(path)
            img.thumbnail((340, 191))
            self._thumb_img = ctk.CTkImage(light_image=img, dark_image=img, size=img.size)
            self.thumb_preview.configure(image=self._thumb_img, text="")
            self.thumb_path = str(path)
        except Exception as e:
            messagebox.showerror("Thumbnail", str(e))

    def pick_thumb(self):
        f = filedialog.askopenfilename(filetypes=[("Images", "*.png *.jpg *.jpeg")])
        if f:
            self._show_thumb(f)

    def make_thumb(self):
        video = self.ent_video.get().strip()
        if not video or not Path(video).exists():
            messagebox.showinfo("Thumbnail", "Choose the video file first.")
            return
        text = self.ent_thumb_text.get().strip().upper()
        pct = self.sld_frame.get() / 100
        out = self._workdir() / "thumbnail.jpg"

        def work():
            self.prog(0.1, "reading the video length")
            r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", video],
                               capture_output=True, text=True, env=ENV, creationflags=NO_WINDOW)
            dur = float(r.stdout.strip() or 10)
            frame = out.with_suffix(".frame.png")
            self.prog(0.3, "grabbing the frame")
            subprocess.run(["ffmpeg", "-y", "-ss", f"{dur * pct:.2f}", "-i", video, "-frames:v", "1", str(frame)],
                           capture_output=True, env=ENV, creationflags=NO_WINDOW)
            from PIL import Image, ImageDraw, ImageFont, ImageEnhance
            img = Image.open(frame).convert("RGB")
            w, h = img.size
            tw, th = (1280, 720) if w >= h else (1080, 1920)
            scale = max(tw / w, th / h)
            img = img.resize((int(w * scale), int(h * scale)))
            l, t = (img.width - tw) // 2, (img.height - th) // 2
            img = ImageEnhance.Contrast(img.crop((l, t, l + tw, t + th))).enhance(1.15)
            img = ImageEnhance.Color(img).enhance(1.2)
            if text:
                d = ImageDraw.Draw(img)
                font_file = next((f for f in [r"C:\Windows\Fonts\impact.ttf", r"C:\Windows\Fonts\arialbd.ttf"]
                                  if Path(f).exists()), None)
                size = int(th * (0.16 if tw > th else 0.09))
                font = ImageFont.truetype(font_file, size) if font_file else ImageFont.load_default()
                words, lines, cur = text.split(), [], ""
                for wd in words:
                    test = (cur + " " + wd).strip()
                    if d.textlength(test, font=font) > tw * 0.9 and cur:
                        lines.append(cur)
                        cur = wd
                    else:
                        cur = test
                lines.append(cur)
                y = th * 0.08
                for ln in lines:
                    x = (tw - d.textlength(ln, font=font)) / 2
                    d.text((x, y), ln, font=font, fill="#ffe14d", stroke_width=max(4, size // 12), stroke_fill="black")
                    y += size * 1.08
            self.prog(0.9, "saving")
            img.save(out, quality=92)
            frame.unlink(missing_ok=True)
            return out
        self.run_job("Making thumbnail", work, self._show_thumb)

    def youtube_setup(self):
        YT_DIR.mkdir(parents=True, exist_ok=True)
        win = ctk.CTkToplevel(self)
        win.title("Connect YouTube")
        win.geometry("640x470")
        win.transient(self)
        steps = ("One-time setup (about 5 minutes, free):\n\n"
                 "1. Open Google Cloud Console and create a project (any name).\n"
                 "2. APIs & Services → Library → enable “YouTube Data API v3”.\n"
                 "3. APIs & Services → OAuth consent screen → External → add your\n"
                 "    Google account under “Test users”.\n"
                 "4. Credentials → Create credentials → OAuth client ID →\n"
                 "    Application type: Desktop app → Create → Download JSON.\n"
                 "5. Click “Choose client_secret.json” below and pick that file.\n"
                 "6. Click “Connect” and sign in with the channel’s Google account.\n\n"
                 "Note: until Google verifies your app, uploads from new API projects may be\n"
                 "locked to private — you can switch them to public in YouTube Studio.")
        ctk.CTkLabel(win, text=steps, justify="left", anchor="w").pack(fill="x", padx=20, pady=16)
        r = ctk.CTkFrame(win, fg_color="transparent")
        r.pack(pady=6)
        ctk.CTkButton(r, text="Open Google Cloud Console",
                      command=lambda: webbrowser.open("https://console.cloud.google.com/apis/library/youtube.googleapis.com")).pack(side="left", padx=4)

        def choose():
            f = filedialog.askopenfilename(parent=win, filetypes=[("JSON", "*.json")])
            if f:
                shutil.copy2(f, YT_DIR / "client_secret.json")
                lbl.configure(text="client_secret.json saved ✔")
        ctk.CTkButton(r, text="Choose client_secret.json", command=choose).pack(side="left", padx=4)

        def connect():
            def work():
                svc = self._yt_service()
                ch = svc.channels().list(part="snippet", mine=True).execute()
                items = ch.get("items", [])
                return items[0]["snippet"]["title"] if items else "(no channel found on this account)"
            self.run_job("Connecting YouTube (finish the sign-in in your browser)", work,
                         lambda name: lbl.configure(text=f"Connected to: {name} ✔"), indeterminate=True)
        ctk.CTkButton(r, text="Connect", fg_color=ACCENT, command=connect).pack(side="left", padx=4)
        lbl = ctk.CTkLabel(win, text=("Connected ✔" if (YT_DIR / "token.json").exists() else ""), text_color=ACCENT)
        lbl.pack(pady=8)

    SCOPES = ["https://www.googleapis.com/auth/youtube.upload", "https://www.googleapis.com/auth/youtube.readonly"]

    def _yt_service(self):
        from google.auth.transport.requests import Request
        from google.oauth2.credentials import Credentials
        from google_auth_oauthlib.flow import InstalledAppFlow
        from googleapiclient.discovery import build
        tok, secret = YT_DIR / "token.json", YT_DIR / "client_secret.json"
        creds = Credentials.from_authorized_user_file(str(tok), self.SCOPES) if tok.exists() else None
        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
            else:
                if not secret.exists():
                    raise RuntimeError("Add your client_secret.json first (Upload → YouTube setup).")
                flow = InstalledAppFlow.from_client_secrets_file(str(secret), self.SCOPES)
                creds = flow.run_local_server(port=0, open_browser=True,
                                              success_message="2D Animation Studio is connected. You can close this tab.")
            YT_DIR.mkdir(parents=True, exist_ok=True)
            tok.write_text(creds.to_json(), encoding="utf-8")
        return build("youtube", "v3", credentials=creds, cache_discovery=False)

    def upload(self):
        video = self.ent_video.get().strip()
        title = self.ent_title.get().strip()
        if not video or not Path(video).exists():
            messagebox.showinfo("Upload", "Choose a video file.")
            return
        if not title:
            messagebox.showinfo("Upload", "Enter a title.")
            return
        privacy = self.opt_priv.get()
        sched = self.ent_sched.get().strip()
        body = {"snippet": {"title": title[:100], "description": self.txt_desc.get("1.0", "end").strip()[:5000],
                            "tags": [t.strip() for t in self.ent_tags.get().split(",") if t.strip()],
                            "categoryId": CATEGORIES[self.opt_cat.get()]},
                "status": {"privacyStatus": privacy, "selfDeclaredMadeForKids": bool(self.chk_kids.get())}}
        if sched:
            try:
                when = datetime.strptime(sched, "%Y-%m-%d %H:%M").astimezone(timezone.utc)
            except ValueError:
                messagebox.showerror("Upload", "Schedule must look like 2026-11-12 18:00")
                return
            body["status"].update({"privacyStatus": "private", "publishAt": when.strftime("%Y-%m-%dT%H:%M:%SZ")})
        if not messagebox.askyesno("Upload to YouTube",
                                   f"Upload “{title[:80]}” as {body['status']['privacyStatus'].upper()}"
                                   + (f", scheduled for {sched}" if sched else "") + "?"):
            return
        thumb = self.thumb_path

        def work():
            from googleapiclient.http import MediaFileUpload
            self.prog(0.01, "signing in to YouTube")
            svc = self._yt_service()
            size = os.path.getsize(video)
            media = MediaFileUpload(video, chunksize=4 * 1024 * 1024, resumable=True, mimetype="video/*")
            req = svc.videos().insert(part="snippet,status", body=body, media_body=media)
            resp, t_up = None, time.time()
            self.prog(0.02, f"uploading 0 / {size / 1e6:.0f} MB")
            while resp is None:
                self.check_cancel()
                st, resp = req.next_chunk()
                if st:
                    pr = st.progress()
                    sent = pr * size
                    speed = sent / max(0.5, time.time() - t_up)
                    self.prog(0.02 + 0.93 * pr, f"uploading {sent / 1e6:.0f} / {size / 1e6:.0f} MB "
                              f"({speed / 1e6:.1f} MB/s)", (size - sent) / speed if speed > 0 else None)
                    self.ui(lambda v=pr: self.lbl_up.configure(text=f"Uploading… {v:.0%}"))
            vid = resp["id"]
            note = ""
            if thumb:
                self.prog(0.97, "setting the thumbnail")
                try:
                    svc.thumbnails().set(videoId=vid, media_body=MediaFileUpload(thumb)).execute()
                except Exception as e:
                    note = f"\n(Thumbnail not set: {str(e)[:150]} — custom thumbnails need a verified channel.)"
            return vid, note

        def done(r):
            vid, note = r
            url = f"https://youtu.be/{vid}"
            self.lbl_up.configure(text=f"Uploaded ✔  {url}")
            self.s.setdefault("uploads", []).append(url)
            self.save_state()
            if messagebox.askyesno("Uploaded", f"Done! {url}{note}\n\nOpen in YouTube Studio?"):
                webbrowser.open(f"https://studio.youtube.com/video/{vid}/edit")
        self.run_job("Uploading to YouTube", work, done)

    # ------------------------------------------------------------------
    def _on_close(self):
        if self.busy and not messagebox.askyesno("Quit", "A task is still running. Stop it and quit?"):
            return
        self.stop_job()
        self.save_state()
        self.destroy()


if __name__ == "__main__":
    HOME.mkdir(parents=True, exist_ok=True)
    WORK.mkdir(parents=True, exist_ok=True)
    Studio().mainloop()
