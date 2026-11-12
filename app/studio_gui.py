"""2D Animation Studio - Windows GUI.

Pipeline:  ScriptForge (ideas + script, via the selected AI)  ->  voiceover (edge-tts or your file)
           ->  GrowKaz Stickman Studio animation (the selected agent runs the make-2d-video skill)
               or OpenArt AI shots cut to the narration (shots_video + openart_provider, no agent)
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
from ai_providers import PROVIDERS, TEXT_PROVIDERS, cli_command, run_agent, portable_prompt, load_env_file
from host_render import HostAnimation
import openart_provider
import shots_video
from parallel_commands import CommandGroup
from openart_defaults import migrate_defaults, build_options, RETENTION_BRIEF, DEFAULT_RESOLUTION
from openart_provider import OPENART
import session_log
import piper_voice
from thumb_text import drawable, set_label_image
import ollama_provider
from ollama_provider import OLLAMA
from language_policy import (ENGLISH_VOICES, english_voice, english_prompt, narration_hash,
                             normalize_narration_prompt, migrate_speech_settings, verify_english_recording)
from datetime import datetime, timezone
from pathlib import Path

APP_DIR = Path(__file__).resolve().parent
from portable_paths import local_environment

HOME = APP_DIR.parent
PIPER_DIR = HOME / ".cache" / "piper"   # downloaded Piper voices
STUDIO = HOME / "growkaz-stickman-studio"
WORK = HOME / "work"
YT_DIR = HOME / "youtube"
SETTINGS_FILE = HOME / "settings.json"
PROMPT_FILE = APP_DIR / "skills" / "scriptforge" / "SKILL.md"
SKILLS_DIR = HOME / ".claude" / "skills"
ERR_LOG = HOME / "gui_error.log"
LOG_FILE = HOME / "studio.log"   # this session only; started fresh on every launch
NO_WINDOW = 0x08000000 if os.name == "nt" else 0


def _log_crash(exc_type, exc, tb):
    try:
        ERR_LOG.write_text("".join(traceback.format_exception(exc_type, exc, tb)), encoding="utf-8")
    except Exception:
        pass
    session_log.error("Uncaught error", exc, tb)
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
VOICES = ENGLISH_VOICES
STYLES = {"Emerald (GrowKaz)": "emerald", "Ember Forge": "ember", "Arctic Glass": "arctic",
          "Sakura Bloom": "sakura", "Retro Print": "retro", "Let AI choose": "auto"}
OA_MODES = {"Stills + AI video clips": True, "Stills only (Ken Burns, cheaper)": False}
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
    return local_environment(HOME, env)


ENV = fresh_env()
# API keys the user keeps in the studio's .env file (Gemini API).
load_env_file(HOME / ".env", ENV)
session_log.start(LOG_FILE, ENV)
session_log.write("INFO", f"2D Animation Studio started in {HOME} (Python {sys.version.split()[0]})")
threading.excepthook = lambda a: session_log.error(f"Error in background thread {a.thread.name if a.thread else ''}",
                                                   a.exc_value, a.exc_traceback)


def _log_dialogs():
    """Every message box the app shows is also written to the session log."""
    def wrap(name, kind):
        shown = getattr(messagebox, name)
        def logged(title=None, message=None, **kw):
            session_log.write(kind, f"[{title}] {message}")
            answer = shown(title, message, **kw)
            if name.startswith("ask"):
                session_log.write("INFO", f"[{title}] answer: {answer}")
            return answer
        setattr(messagebox, name, logged)
    for name, kind in (("showerror", "ERROR"), ("showwarning", "WARN"), ("showinfo", "INFO"),
                       ("askyesno", "ASK"), ("askyesnocancel", "ASK"), ("askokcancel", "ASK")):
        wrap(name, kind)


_log_dialogs()
# Python libraries also use local caches when called directly rather than as children.
for _key in ("TEMP", "TMP", "XDG_CACHE_HOME", "HF_HOME", "PIP_CACHE_DIR", "PLAYWRIGHT_BROWSERS_PATH"):
    os.environ[_key] = ENV[_key]



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
    return t.strip() + "\n\n" + RETENTION_BRIEF


def extract_json(text, opener="["):
    closer = "]" if opener == "[" else "}"
    a, b = text.find(opener), text.rfind(closer)
    if a < 0 or b <= a:
        raise ValueError("AI did not return JSON:\n" + text[:500])
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
        self.report_callback_exception = lambda *err: session_log.error("Error in the window", err[1], err[2])
        self.proc = None
        self._openart_commands = CommandGroup(ENV, creationflags=NO_WINDOW, log=session_log.write)
        self.busy = False
        self.settings = piper_voice.migrate_voice(migrate_defaults(migrate_speech_settings(load_settings())))
        self.s = self.settings.get("current", {})   # current video state
        save_settings(self.settings)
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
        self.apply_offline()
        self._refresh_offline_badge()
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
        self.btn_auto = ctk.CTkButton(sb, text="⚡ Auto", height=48, corner_radius=12,
                                      font=ctk.CTkFont(size=17, weight="bold"), command=self.auto_run)
        self.btn_auto.pack(fill="x", padx=18, pady=(4, 2))
        ctk.CTkLabel(sb, text="script → voice → animation → thumbnail,\nthen waits for you to Publish",
                     text_color="#7c8594", font=ctk.CTkFont(size=11), justify="left").pack(anchor="w", padx=22, pady=(0, 8))
        self._auto, self._chain, self._auto_tries, self._auto_n = False, None, {}, 0
        ctk.CTkButton(sb, text="＋ New video", height=34, fg_color="#1d222b", hover_color="#272d38",
                      command=self.new_video).pack(fill="x", padx=18, pady=4)
        ctk.CTkButton(sb, text="📁 Open studio folder", height=34, fg_color="#1d222b", hover_color="#272d38",
                      command=lambda: open_path(HOME)).pack(fill="x", padx=18, pady=4)
        ctk.CTkButton(sb, text="📜 Show logs", height=34, fg_color="#1d222b", hover_color="#272d38",
                      command=self.show_logs).pack(fill="x", padx=18, pady=4)
        self.lbl_offline = ctk.CTkLabel(sb, text="", text_color="#f59e0b", font=ctk.CTkFont(size=13, weight="bold"))
        self.lbl_offline.pack(fill="x", padx=18, pady=(2, 0))
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
                    session_log.error("Error while updating the window")
                    traceback.print_exc()
        except queue.Empty:
            pass
        self.after(80, self._pump)

    def log(self, box, text):
        session_log.write("OUT", text)
        def _w():
            box.insert("end", text.rstrip() + "\n")
            box.see("end")
        self.ui(_w)

    def status(self, text):
        session_log.write("STEP", text)
        self.ui(lambda: self.lbl_status.configure(text=text))

    def show_logs(self):
        """Window with this session's log; it follows the file while the studio works."""
        win = getattr(self, "_log_win", None)
        if win and win.winfo_exists():
            win.lift()
            win.focus()
            return
        win = self._log_win = ctk.CTkToplevel(self)
        win.title("2D Animation Studio — logs (this session)")
        win.geometry("980x620")
        win.configure(fg_color="#0b0d10")
        bar = ctk.CTkFrame(win, fg_color="transparent")
        bar.pack(fill="x", padx=12, pady=(10, 4))
        box = self.logbox(win)
        box.pack(fill="both", expand=True, padx=12, pady=(4, 12))
        errors_only = ctk.BooleanVar(value=False)
        shown = {"size": -1, "errors": None}

        def read():
            try:
                return LOG_FILE.read_text(encoding="utf-8", errors="replace")
            except OSError as e:
                return f"The log file cannot be read: {e}"

        def errors(text):
            # Every line of an entry, traceback included, carries the entry's tag after the time.
            return "\n".join(l for l in text.splitlines() if l[9:14] in ("ERROR", "WARN ")) or "No errors so far."

        def refresh():
            if not win.winfo_exists():
                return
            try:
                size = LOG_FILE.stat().st_size
            except OSError:
                size = 0
            if (size, errors_only.get()) != (shown["size"], shown["errors"]):
                at_end = box.yview()[1] > 0.999 or shown["errors"] != errors_only.get()
                text = read()
                box.configure(state="normal")
                box.delete("1.0", "end")
                box.insert("end", errors(text) if errors_only.get() else text)
                box.configure(state="disabled")
                if at_end:
                    box.see("end")
                shown.update(size=size, errors=errors_only.get())
            win.after(1000, refresh)

        def copy():
            self.clipboard_clear()
            self.clipboard_append(read())

        ctk.CTkLabel(bar, text=str(LOG_FILE), text_color="#7c8594", font=ctk.CTkFont(size=11)).pack(side="left")
        ctk.CTkButton(bar, text="Open file", width=90, fg_color="#1d222b", hover_color="#272d38",
                      command=lambda: open_path(LOG_FILE)).pack(side="right", padx=(6, 0))
        ctk.CTkButton(bar, text="Copy all", width=90, fg_color="#1d222b", hover_color="#272d38",
                      command=copy).pack(side="right", padx=(6, 0))
        ctk.CTkCheckBox(bar, text="Errors only", variable=errors_only, width=110).pack(side="right", padx=(6, 0))
        win.after(200, win.lift)   # CTkToplevel opens behind the main window on Windows
        refresh()

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
        if self._auto:
            label = f"⚡ Auto {self._auto_n}/5 · {label}"
        self.busy = True
        self._job_ai = {k: v for k, v in self.settings.items() if k.endswith(("_provider", "_model"))}
        self._cancel = False
        session_log.write("STEP", f"Started: {label}  ({', '.join(f'{k}={v or chr(45)}' for k, v in self._job_ai.items())})")
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
                if self._cancel:
                    session_log.write("STEP", f"Stopped by the user: {label} ({e})")
                else:
                    session_log.error(f"Failed: {label}")
                traceback.print_exc()

            def finish():
                el = time.time() - self._job["t0"] if self._job else 0
                if not err:
                    session_log.write("STEP", f"Done: {label} (took {self._fmt_t(el)})")
                self.busy = False
                self.proc = None
                self._job = None
                self.progress.stop()
                self.progress.configure(mode="determinate")
                self.btn_stop.configure(state="disabled")
                if err:
                    was_auto = self._auto
                    self._auto_stop()
                    self.lbl_status.configure(text=f"{label}: {'stopped' if self._cancel else 'failed'}")
                    self.lbl_pct.configure(text=f"after {self._fmt_t(el)}")
                    if not self._cancel:
                        messagebox.showerror(label, str(err)[:1500] + ("\n\n⚡ Auto stopped here. Fix it and press "
                                                                         "Auto again — it continues from this step."
                                                                         if was_auto else ""))
                else:
                    self.progress.set(1)
                    self.lbl_status.configure(text=f"{label}: done")
                    self.lbl_pct.configure(text=f"100%  ·  took {self._fmt_t(el)}")
                    if done:
                        done(res)
                    nxt, self._chain = self._chain, None
                    if nxt and self._auto:
                        self.after(400, nxt)
            self.ui(finish)
        threading.Thread(target=worker, daemon=True).start()

    def stop_job(self):
        self._cancel = True
        self._openart_commands.stop()
        if self.proc and self.proc.poll() is None:
            subprocess.run(["taskkill", "/PID", str(self.proc.pid), "/T", "/F"], capture_output=True,
                           creationflags=NO_WINDOW)
        self.status("Stopping…")

    def run_cmd(self, cmd, cwd=None, stdin_text=None, on_line=None):
        session_log.write("RUN", f"{subprocess.list2cmdline([str(c) for c in cmd])[:600]}  (in {cwd or os.getcwd()})")
        self.proc = subprocess.Popen(
            cmd, cwd=cwd, env=getattr(self, "_child_env", None) or ENV,
            stdin=subprocess.PIPE if stdin_text is not None else subprocess.DEVNULL,
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding="utf-8", errors="replace",
            creationflags=NO_WINDOW)
        if stdin_text is not None:
            self.proc.stdin.write(stdin_text)
            self.proc.stdin.close()
        for line in self.proc.stdout:
            session_log.write("OUT", line)
            if on_line:
                on_line(line.rstrip("\n"))
        code = self.proc.wait()
        session_log.write("RUN", f"exit code {code}: {Path(str(cmd[0])).name}")
        return code

    def ask_ai(self, prompt, box=None, tools=None, full_auto=False, cwd=None, expect_chars=None, on_tool=None):
        prompt = english_prompt(prompt)
        stage = "animation" if tools else "script"
        ai = getattr(self, "_job_ai", self.settings)
        provider = ai.get(stage + "_provider", "Claude")
        if provider == OPENART and tools:
            raise RuntimeError("OpenArt videos are built by the studio itself: use Make the video.")
        if self.settings.get("offline") or provider == OLLAMA:
            # the stage's Model box only counts when Ollama was chosen for that stage
            model = (ai.get(stage + "_model", "") if provider == OLLAMA else "") or ai.get("ollama_model", "")
            session_log.write("STEP", f"Asking {OLLAMA} ({stage}, model {model or ollama_provider.DEFAULT_MODEL}, "
                                      f"prompt {len(prompt)} characters)")
            return self.ask_ollama(prompt, model, box, tools, full_auto, cwd, expect_chars, on_tool)
        session_log.write("STEP", f"Asking {provider} ({stage}, model {ai.get(stage + '_model') or 'default'}, "
                                  f"prompt {len(prompt)} characters)")
        if provider == "Claude":
            return self.ask_claude(prompt, box, tools, full_auto, cwd, expect_chars, on_tool)
        self.prog(0.03, f"starting {provider}")
        written = 0

        def event(kind, value):
            nonlocal written
            if kind == "tool":
                if on_tool:
                    on_tool(value.get("name", "tool"), value)
                if box is not None:
                    self.log(box, f"🔧 {value.get('name')}: {str(value.get('command') or value.get('file_path') or '')[:160]}")
            else:
                if box is not None:
                    self.log(box, value)
                if kind == "text" and expect_chars:
                    written += len(value)
                    self.prog(min(0.97, 0.06 + 0.91 * written / expect_chars), f"writing… {written // 6:,} words")
        return run_agent(provider, prompt, self.run_cmd, cwd=cwd or HOME, env=ENV,
                         animation=bool(tools), full_auto=full_auto,
                         model=ai.get(stage + "_model", ""),
                         skill_dir=SKILLS_DIR / "make-2d-video", on_event=event)

    def offline(self):
        """True when "Always work offline" is on: local AI and Piper voice. Upload still works."""
        return bool(self.settings.get("offline"))

    def apply_offline(self):
        """Keep child tools off the network too (Whisper then uses its downloaded model)."""
        for key in ("HF_HUB_OFFLINE", "TRANSFORMERS_OFFLINE"):
            if self.offline():
                ENV[key] = "1"
            else:
                ENV.pop(key, None)

    def ask_ollama(self, prompt, model, box=None, tools=None, full_auto=False, cwd=None, expect_chars=None, on_tool=None):
        """Local model through Ollama. Text is one streamed request; animation runs the Claude Code CLI
        against the local Ollama server, so the same skill and tools are used with no internet."""
        self.prog(0.02, "starting Ollama (a local model can take minutes to answer)")
        if not tools:
            written = 0

            def piece(kind, value):
                nonlocal written
                self.check_cancel()
                written += len(value)
                self.prog(min(0.97, 0.06 + 0.91 * written / expect_chars) if expect_chars else None,
                          f"writing… {written // 6:,} words")
            answer = run_agent(OLLAMA, prompt, self.run_cmd, cwd=cwd or HOME, env=ENV, model=model,
                               skill_dir=SKILLS_DIR / "make-2d-video", on_event=piece)
            if box is not None:
                self.log(box, answer)
            return answer
        if not claude_exe():
            raise RuntimeError("Offline animation runs the Claude Code CLI against Ollama, and the CLI was not "
                               "found. Go to Setup and re-run the installer (no Claude login is needed).")
        local = ollama_provider.agent_model(model, ENV)
        self._child_env, self._claude_model = ollama_provider.claude_env(ENV, local), local
        try:
            return self.ask_claude(prompt, box, tools, full_auto, cwd, expect_chars, on_tool)
        except RuntimeError as exc:
            if str(exc) == "Stopped.":
                raise
            raise RuntimeError(f"Ollama ({local}) could not finish this step: {exc}\n\nLocal models are much weaker "
                               "than the online ones. A larger model (offline model box in Setup) may be "
                               "needed.") from exc
        finally:
            self._child_env = self._claude_model = None

    def ask_claude(self, prompt, box=None, tools=None, full_auto=False, cwd=None, expect_chars=None, on_tool=None):
        """Run `claude -p` headless, stream progress into box, return the final result text.
        expect_chars: roughly how long the answer is, so the bar can follow the text as it is written.
        on_tool(name, input): called for every tool Claude uses (the Animate page uses it for stages)."""
        exe = claude_exe()
        if not exe:
            raise RuntimeError("Claude Code CLI not found. Go to Setup and install / log in.")
        cmd = [exe, "-p", "--output-format", "stream-json", "--verbose"]
        stage = "animation" if tools else "script"
        model = getattr(self, "_claude_model", None) or getattr(self, "_job_ai", self.settings).get(stage + "_model", "")
        if model:
            cmd += ["--model", model]
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
        if rc != 0:
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
        self._reset_project()
        self.show("script")

    def _reset_project(self):
        """Forget the current video (its files stay in work\\) so the next one starts from scratch."""
        self.s = {}
        self.ideas = []
        self.save_state()
        self.txt_script.delete("1.0", "end")
        self._render_ideas()
        self._clear_upload_page()

    def _clear_upload_page(self):
        for e in (self.ent_video, self.ent_title, self.ent_tags, self.ent_thumb_text, self.ent_sched):
            e.delete(0, "end")
        self.txt_desc.delete("1.0", "end")
        self.thumb_path = None
        self._thumb_img = None
        set_label_image(self.thumb_preview, None, "No thumbnail yet")
        self.lbl_up.configure(text="")

    # ================================================================== ⚡ AUTO
    AUTO_STEPS = ["ideas", "script", "voiceover", "animation", "thumbnail"]

    def auto_run(self):
        if self.busy:
            messagebox.showinfo("Auto", "A task is running. Wait for it or press Stop first.")
            return
        start, fresh = self._auto_start(), False
        if start != "ideas":   # there is work in progress: new video, or carry on with this one?
            choice = self._ask_auto_mode(start)
            if choice is None:
                return
            fresh = choice == "fresh"
            if fresh:
                start = "ideas"   # the project is only cleared once the summary below is confirmed
        s = self.s
        todo = self.AUTO_STEPS[self.AUTO_STEPS.index(start):]
        main, sub = self._niche()
        self._sync_animate_page()
        engine = self.opt_engine.get()
        voice = self.opt_el_voice.get() if engine == "ElevenLabs" else self.opt_voice.get()
        credit_note = ("OpenArt: Save credits is on (stills, local camera motion, 720p; existing plans resume).\n"
                       if self.settings.get("animation_provider") == OPENART
                       and self.settings.get("openart_save_credits", True) else "")
        summary = (f"⚡ Auto will do: {' → '.join(todo)}, then stop on the Upload page.\n"
                   f"Nothing is published until you press Publish.\n\n"
                   + (f"Niche: {sub}\nLength: {self.opt_len.get()}  (uses the first idea)\n" if start in ("ideas", "script")
                      else f"Video: {s.get('title', '—')}\n")
                   + f"Voice: {engine} · {voice}\n"
                   + credit_note
                   + f"Video: {self.opt_aspect.get()} · {self.opt_res.get()} · {self.opt_style.get()} · parts {self.opt_parts.get()}\n\n"
                   "Settings come from the Script, Voiceover and Animate pages — change them there first if needed.\n"
                   "The animation step can take a long time. Start?")
        if not messagebox.askyesno("⚡ Auto", summary):
            return
        if fresh:
            self._reset_project()
            self._sync_animate_page()
        self._auto, self._auto_tries = True, {}
        self.btn_auto.configure(text="⚡ Auto running…", state="disabled")
        self._auto_step()

    def _auto_start(self):
        """The first Auto step still to do for the current project."""
        s = self.s
        have = lambda k: bool(s.get(k)) and Path(s[k]).exists()
        return ("thumbnail" if have("video") else "animation" if have("voice") else
                "voiceover" if s.get("script") else "script" if self.ideas else "ideas")

    def _ask_auto_mode(self, start):
        """Ask whether Auto starts a brand-new video or continues the current one.
        Returns "fresh", "continue" or None (cancelled)."""
        done = self.AUTO_STEPS[:self.AUTO_STEPS.index(start)]
        title = self.s.get("title") or "(untitled — ideas only)"
        win = ctk.CTkToplevel(self)
        win.title("⚡ Auto")
        win.geometry("520x300")
        win.resizable(False, False)
        win.transient(self)
        win.configure(fg_color=CARD_BG)
        result = {"v": None}

        def pick(v):
            result["v"] = v
            win.destroy()

        ctk.CTkLabel(win, text="What should ⚡ Auto make?", font=ctk.CTkFont(size=18, weight="bold")
                     ).pack(anchor="w", padx=20, pady=(18, 6))
        ctk.CTkLabel(win, text=f"Current project: {title}\n"
                               f"Done: {', '.join(done) or 'nothing yet'}   ·   Next: {start}",
                     justify="left", wraplength=480, text_color="#9aa3b2").pack(anchor="w", padx=20)
        ctk.CTkButton(win, text="✨  Start fresh — new ideas, new script, the whole process", height=40,
                      anchor="w", command=lambda: pick("fresh")).pack(fill="x", padx=20, pady=(18, 6))
        ctk.CTkButton(win, text=f"▶  Continue this project — from {start}", height=40, anchor="w",
                      fg_color="#1d222b", hover_color="#272d38", command=lambda: pick("continue")
                      ).pack(fill="x", padx=20, pady=6)
        ctk.CTkLabel(win, text="Starting fresh keeps the current project saved in work\\.",
                     text_color="#6b7380").pack(anchor="w", padx=20, pady=(4, 0))
        ctk.CTkButton(win, text="Cancel", width=90, fg_color="transparent", border_width=1,
                      border_color="#2b313c", command=lambda: pick(None)).pack(anchor="e", padx=20, pady=10)
        win.protocol("WM_DELETE_WINDOW", lambda: pick(None))
        win.bind("<Escape>", lambda e: pick(None))
        win.after(50, win.grab_set)   # modal; CTkToplevel needs a moment before grab works
        win.after(60, win.focus_force)
        self.wait_window(win)
        return result["v"]

    def _auto_stop(self, msg=None):
        self._auto, self._chain = False, None
        self.btn_auto.configure(text="⚡ Auto", state="normal")
        if msg:
            self.lbl_status.configure(text=msg)

    def _auto_go(self, step, fn):
        """Run one step; when its job finishes, _auto_step picks the next one from the saved state."""
        tries = self._auto_tries.get(step, 0) + 1
        self._auto_tries[step] = tries
        if tries > 2:   # the step "finished" twice without producing its result — don't loop forever
            self._auto_stop(f"⚡ Auto stopped: the {step} step finished without a result")
            messagebox.showwarning("⚡ Auto", f"The {step} step finished but didn't produce its result. "
                                              "Check its page and log, then press Auto again.")
            return
        self._auto_n = self.AUTO_STEPS.index(step) + 1
        self._chain = self._auto_step
        fn()
        if not self.busy:   # the step refused to start (it showed why)
            self._auto_stop(f"⚡ Auto stopped before the {step} step")

    def _auto_step(self):
        if not self._auto:
            return
        s = self.s
        have = lambda k: bool(s.get(k)) and Path(s[k]).exists()
        if not s.get("script"):
            if not self.ideas:
                self.show("script")
                return self._auto_go("ideas", self.get_ideas)
            used = set(s.get("used_ideas", []))
            idea = next((i for i in self.ideas if i.get("title") not in used), self.ideas[0])
            self.show("script")
            return self._auto_go("script", lambda: self.write_script(idea))
        if not have("voice"):
            self.show("voice")
            return self._auto_go("voiceover", self.make_voice)
        if not have("video"):
            self.show("animate")
            return self._auto_go("animation", self.make_video)
        if not have("thumb"):
            self.show("upload")
            return self._auto_go("thumbnail", self.make_thumb)
        # everything is ready: hand over to the user
        self._auto_stop("⚡ Auto finished — review and press Publish")
        self.show("upload")
        self.deiconify()
        self.lift()
        self.attributes("-topmost", True)
        self.after(600, lambda: self.attributes("-topmost", False))
        self.bell()
        self.btn_publish.configure(fg_color="#f59e0b", hover_color="#d97706", text_color="#111111")
        messagebox.showinfo("⚡ Auto finished", f"“{s.get('title', 'Your video')}” is ready.\n\n"
                                                "Check the title, description, tags, privacy and thumbnail on this page, "
                                                "then press 🚀 Publish to YouTube.")

    # ================================================================== SETUP PAGE
    def _page_setup(self, p):
        self.header(p, "Setup & Tools", "Everything the pipeline needs. Green = ready. "
                    "Choose your AI providers below, then install and sign in to their CLIs.")
        ai = self.card(p)
        for stage, label in [("script", "Ideas & script"), ("animation", "Animation & character designs")]:
            row_ai = ctk.CTkFrame(ai, fg_color="transparent")
            row_ai.pack(fill="x", padx=12, pady=5)
            ctk.CTkLabel(row_ai, text=label, width=200, anchor="w").pack(side="left")
            def save_provider(value, stage=stage):
                self.settings[stage + "_provider"] = value
                save_settings(self.settings)
            menu = ctk.CTkOptionMenu(row_ai, values=list(PROVIDERS if stage == "animation" else TEXT_PROVIDERS),
                                     command=save_provider)
            menu.set(self.settings.get(stage + "_provider", "Claude"))
            menu.pack(side="left", padx=6)
            model = ctk.CTkEntry(row_ai, placeholder_text="Model (blank = default)", width=220)
            model.insert(0, self.settings.get(stage + "_model", ""))
            model.pack(side="left", padx=6)
            def save_model(event=None, stage=stage, entry=model):
                self.settings[stage + "_model"] = entry.get().strip()
                save_settings(self.settings)
            model.bind("<FocusOut>", save_model)
            model.bind("<Return>", save_model)
        row_off = ctk.CTkFrame(ai, fg_color="transparent")
        row_off.pack(fill="x", padx=12, pady=5)
        self.sw_offline = ctk.CTkSwitch(row_off, text="Always work offline (Ollama + Piper voice)",
                                        command=self._toggle_offline)
        if self.offline():
            self.sw_offline.select()
        self.sw_offline.pack(side="left")
        self.ent_ollama = ctk.CTkEntry(row_off, width=220,
                                       placeholder_text=f"Offline model ({ollama_provider.DEFAULT_MODEL})")
        self.ent_ollama.insert(0, self.settings.get("ollama_model", ""))
        self.ent_ollama.pack(side="left", padx=12)

        def save_ollama(event=None):
            self.settings["ollama_model"] = self.ent_ollama.get().strip()
            save_settings(self.settings)
        self.ent_ollama.bind("<FocusOut>", save_ollama)
        self.ent_ollama.bind("<Return>", save_ollama)
        ctk.CTkButton(row_off, text="Install Ollama", command=self.install_ollama).pack(side="left", padx=4)
        ctk.CTkButton(row_off, text="Download offline model", command=self.download_ollama_model).pack(side="left", padx=4)
        row_oa = ctk.CTkFrame(ai, fg_color="transparent")
        row_oa.pack(fill="x", padx=12, pady=5)
        ctk.CTkLabel(row_oa, text="OpenArt (AI shots)", width=200, anchor="w").pack(side="left")
        self.opt_oa_mode = ctk.CTkOptionMenu(row_oa, values=list(OA_MODES), width=220, command=self._save_openart)
        self.opt_oa_mode.set(next((k for k, v in OA_MODES.items() if v == self.settings.get("openart_motion", True)),
                                  next(iter(OA_MODES))))
        self.opt_oa_mode.pack(side="left", padx=6)
        self.ent_oa = {}
        for key, width, hint in (("openart_clip_seconds", 150, f"Seconds per shot ({shots_video.DEFAULT_CLIP_SECONDS})"),
                                 ("openart_image_model", 190, f"Image model ({openart_provider.DEFAULT_IMAGE_MODEL})"),
                                 ("openart_video_model", 190, f"Video model ({openart_provider.DEFAULT_VIDEO_MODEL})")):
            entry = ctk.CTkEntry(row_oa, width=width, placeholder_text=hint)
            entry.insert(0, str(self.settings.get(key, "")))
            entry.pack(side="left", padx=6)
            entry.bind("<FocusOut>", self._save_openart)
            entry.bind("<Return>", self._save_openart)
            self.ent_oa[key] = entry
        row_parallel = ctk.CTkFrame(ai, fg_color="transparent")
        row_parallel.pack(fill="x", padx=12, pady=5)
        ctk.CTkLabel(row_parallel, text="OpenArt parallel shots", width=200, anchor="w").pack(side="left")
        self.opt_oa_parallel = ctk.CTkOptionMenu(
            row_parallel, values=[str(i) for i in range(1, shots_video.MAX_PARALLEL_SHOTS + 1)],
            width=90, command=self._save_openart)
        self.opt_oa_parallel.set(str(shots_video.parallel_shots(self.settings.get("openart_parallel_shots"))))
        self.opt_oa_parallel.pack(side="left", padx=6)
        ctk.CTkLabel(row_parallel, text="Simultaneous scenes (1 = sequential; default 3)").pack(side="left", padx=6)
        row_economy = ctk.CTkFrame(ai, fg_color="transparent")
        row_economy.pack(fill="x", padx=12, pady=5)
        self.sw_oa_economy = ctk.CTkSwitch(row_economy, text="Save OpenArt credits (recommended)",
                                          command=self._save_openart)
        if self.settings.get("openart_save_credits", True):
            self.sw_oa_economy.select()
        self.sw_oa_economy.pack(side="left")
        ctk.CTkLabel(row_economy, wraplength=420, justify="left",
                    text="720p stills + smooth camera motion; 12s long / 6s Shorts; existing plans resume"
                    ).pack(side="left", padx=12)
        self._openart_economy_controls()
        buttons_ai = ctk.CTkFrame(ai, fg_color="transparent")
        buttons_ai.pack(fill="x", padx=12, pady=6)
        for provider in ("OpenAI (Codex)", "Gemini"):
            ctk.CTkButton(buttons_ai, text=f"Install {provider}", command=lambda v=provider: self.install_ai(v)).pack(side="left", padx=4)
            ctk.CTkButton(buttons_ai, text=f"Sign in: {provider}", command=lambda v=provider: self.login_ai(v)).pack(side="left", padx=4)
        for txt, cmd in [("Install OpenArt", self.install_openart), ("Sign in: OpenArt", self.login_openart),
                         ("Check OpenArt account", self.check_openart)]:
            ctk.CTkButton(buttons_ai, text=txt, command=cmd).pack(side="left", padx=4)
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

    def _save_openart(self, event=None):
        was_economy = self.settings.get("openart_save_credits", True)
        self.settings["openart_save_credits"] = bool(self.sw_oa_economy.get())
        if was_economy and not self.settings["openart_save_credits"]:
            self.opt_oa_mode.set(next(k for k, v in OA_MODES.items()
                                      if v == self.settings.get("openart_motion", True)))
        if not self.settings["openart_save_credits"]:
            self.settings["openart_motion"] = OA_MODES.get(self.opt_oa_mode.get(), True)
        self.settings["openart_parallel_shots"] = shots_video.parallel_shots(self.opt_oa_parallel.get())
        for key, entry in self.ent_oa.items():
            value = entry.get().strip()
            if key == "openart_clip_seconds":
                value = shots_video.clip_seconds(value) if value else ""
            self.settings[key] = value
        save_settings(self.settings)

        self._openart_economy_controls()

    def _openart_economy_controls(self):
        state = "disabled" if self.sw_oa_economy.get() else "normal"
        if self.sw_oa_economy.get():
            self.opt_oa_mode.set(next(k for k, v in OA_MODES.items() if not v))
        self.opt_oa_mode.configure(state=state)
        self.ent_oa["openart_clip_seconds"].configure(state=state)

    def _openart_run(self, cmd, cwd=None):
        """Each concurrent command has its own process/output; Stop kills all of them."""
        return self._openart_commands.run(cmd, cwd or HOME, check=self.check_cancel)

    def install_openart(self):
        """The release binary goes into the studio's .tools folder (already on PATH); no installer script,
        so the user's Windows PATH and profile stay untouched."""
        def work():
            openart_provider.install(HOME / ".tools", lambda text: self.log(self.setup_log, text))
            self.log(self.setup_log, 'Now press "Sign in: OpenArt": a console and your browser open for the OpenArt login.')
        self.run_job("Installing OpenArt CLI", work, lambda _: self.check_setup(), indeterminate=True)

    def login_openart(self):
        try:
            cmd = openart_provider.command(ENV, "login")
        except RuntimeError as e:
            messagebox.showerror("OpenArt", str(e))
            return
        # The credential lands in the studio's own home (.runtime/home/.openart), like the other CLIs.
        subprocess.Popen(["cmd", "/k", *cmd], cwd=str(HOME), env=ENV, creationflags=subprocess.CREATE_NEW_CONSOLE)

    def check_openart(self):
        def work():
            info = openart_provider.account(self._openart_run, ENV)
            self.log(self.setup_log, "OpenArt account: " + json.dumps(info)[:500])
        self.log(self.setup_log, "> openart account --json")
        self.run_job("Checking OpenArt account", work, indeterminate=True)

    def _toggle_offline(self):
        self.settings["offline"] = bool(self.sw_offline.get())
        save_settings(self.settings)
        self.apply_offline()
        session_log.write("INFO", f"Always work offline: {'on' if self.offline() else 'off'}")
        if hasattr(self, "opt_engine"):
            self._on_engine(self.settings.get("engine"))
        self._refresh_offline_badge()

    def _refresh_offline_badge(self):
        if hasattr(self, "lbl_offline"):
            self.lbl_offline.configure(text="✈ Offline mode" if self.offline() else "")

    def install_ollama(self):
        if ollama_provider.executable():
            messagebox.showinfo("Ollama", "Ollama is already installed.")
            return

        def work():
            self.log(self.setup_log, "> winget install Ollama.Ollama   (about 1 GB, needs internet)")
            rc = self.run_cmd(["winget", "install", "--id", "Ollama.Ollama", "-e", "--silent",
                               "--accept-package-agreements", "--accept-source-agreements"],
                              on_line=lambda line: line.strip() and self.log(self.setup_log, line))
            if not ollama_provider.executable():
                raise RuntimeError(f"Ollama was not installed (winget exit {rc}). Install it from ollama.com instead.")
        self.run_job("Installing Ollama", work, lambda _: self.check_setup(), indeterminate=True)

    def download_ollama_model(self):
        model = self.ent_ollama.get().strip() or ENV.get("OLLAMA_MODEL") or ollama_provider.DEFAULT_MODEL
        if not messagebox.askyesno("Download offline model", f"Download the Ollama model \"{model}\"?\n\n"
                                   "Models are large (the default is about 14 GB) and this needs internet. "
                                   "After that it works with no connection."):
            return

        def work():
            ollama_provider.ensure_running(ENV)
            self.log(self.setup_log, f"> ollama pull {model}")

            def progress(fraction, status):
                self.check_cancel()
                self.prog(fraction, f"{model}: {status}")
            ollama_provider.pull(model, ENV, progress)
            self.log(self.setup_log, f"{model} is ready for offline use.")
        self.run_job(f"Downloading {model}", work, lambda _: self.check_setup())

    def _offline_status(self):
        """Setup rows for the pieces offline work needs."""
        model = self.settings.get("ollama_model") or ENV.get("OLLAMA_MODEL") or ollama_provider.DEFAULT_MODEL
        if not ollama_provider.executable():
            ollama = None
        else:
            try:
                names = ollama_provider.models(ENV) if ollama_provider.is_running(ENV) else None
            except Exception:
                names = None
            ollama = ("installed (not running)" if names is None else
                      f"{model} ready" if ollama_provider._installed(model, names) else None)
        whisper = any((Path(ENV.get("HF_HOME", "")) / "hub").glob("models--Systran--faster-whisper-*/snapshots/*/model.bin"))
        voice = piper_voice.piper_voice(self.settings.get("piper_voice"))
        return [("Ollama + offline model (optional)", ollama),
                ("Whisper model (offline timestamps)", "downloaded" if whisper else None),
                ("Piper voice (offline)", voice if piper_voice.installed(voice, PIPER_DIR) else None)]

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
                ("Local skills (make-2d-video, scriptforge)", "installed" if (SKILLS_DIR / "make-2d-video" / "SKILL.md").exists()
                 and (SKILLS_DIR / "scriptforge" / "SKILL.md").exists() else None),
            ]
            for provider in ("OpenAI (Codex)", "Gemini"):
                try:
                    items.append((provider + " CLI (optional)", probe(cli_command(provider, ENV) + ["--version"])))
                except RuntimeError:
                    items.append((provider + " CLI (optional)", None))
            for mod, label in [("faster_whisper", "faster-whisper"), ("edge_tts", "edge-tts (voices)"),
                               ("piper", "Piper (offline voice)"),
                               ("googleapiclient", "YouTube API client"), ("PIL", "Pillow (thumbnails)")]:
                try:
                    __import__(mod)
                    items.append((label, "installed"))
                except Exception:
                    items.append((label, None))
            items += self._offline_status()
            exe = openart_provider.executable(ENV)
            items.append(("OpenArt CLI (optional)", probe([exe, "version"]) if exe else None))
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
            self.run_cmd([PY, "-m", "pip", "install", "--upgrade", "numpy", "scipy", "faster-whisper", "edge-tts", "piper-tts",
                          "customtkinter", "pillow", "google-api-python-client", "google-auth-oauthlib",
                          "google-auth-httplib2"], on_line=pip_line)
            self.check_cancel()
            voice = piper_voice.piper_voice(self.settings.get("piper_voice"))
            if not piper_voice.installed(voice, PIPER_DIR):
                self.prog(0.6, f"downloading the Piper voice {voice}")
                try:
                    piper_voice.download(voice, PIPER_DIR)
                except RuntimeError as error:       # optional: it downloads on first use instead
                    self.log(self.setup_log, str(error))
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
            if messagebox.askyesno("Claude Code", "Claude Code is not installed. Install it in this studio folder?"):
                def install():
                    rc = self.run_cmd(["cmd", "/c", "npm", "install", "--prefix", str(HOME / ".tools"),
                                       "-g", "@anthropic-ai/claude-code"],
                                      on_line=lambda line: self.log(self.setup_log, line))
                    if rc:
                        raise RuntimeError("Claude installation failed. See Setup log.")
                self.run_job("Installing Claude", install, lambda _: self.check_setup())
            return
        messagebox.showinfo("Log in to Claude", "A Claude Code window will open.\n\n"
                            "Sign in when asked (or type /login), then type /exit and close that window.")
        # pass the exe as its own argument: embedding quotes made Python escape them as \" and cmd failed
        subprocess.Popen(["cmd", "/k", exe], cwd=str(STUDIO if STUDIO.exists() else HOME), env=ENV,
                         creationflags=subprocess.CREATE_NEW_CONSOLE)

    def install_ai(self, provider):
        package = "@openai/codex" if provider == "OpenAI (Codex)" else "@google/gemini-cli"
        def work():
            cmd = ["cmd", "/c", "npm", "install", "--prefix", str(HOME / ".tools"), "-g"]
            if provider == "Gemini":
                # npm requires explicit approval for this native credential-store dependency.
                # Keep approval on this command, rather than changing the user's npm config.
                cmd.append("--allow-scripts=@github/keytar")
                self.log(self.setup_log, "Allowing Gemini's @github/keytar install script for this installation.")
            else:
                cmd.append("--allow-scripts=@openai/codex")
            cmd.append(package)
            rc = self.run_cmd(cmd,
                              on_line=lambda line: self.log(self.setup_log, line))
            if rc:
                raise RuntimeError(f"Could not install {provider}. See the Setup log.")
            ENV.update(fresh_env())
            self.log(self.setup_log, f"{provider} installed. Deprecation warnings alone do not mean installation failed.")
        self.run_job(f"Installing {provider}", work, lambda _: self.check_setup())

    def login_ai(self, provider):
        try:
            cmd = cli_command(provider, ENV)
        except RuntimeError as e:
            messagebox.showerror(provider, str(e))
            return
        if provider == "OpenAI (Codex)":
            cmd += ["login"]
        subprocess.Popen(["cmd", "/k", *cmd], cwd=str(HOME), env=ENV,
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
        self.header(p, "① Script — ScriptForge", "Pick a niche, get 10 ideas from your selected AI, choose one, "
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
            return extract_json(self.ask_ai(prompt, cwd=HOME, expect_chars=1900), "[")

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
        used = self.s.setdefault("used_ideas", [])
        if idea.get("title") and idea["title"] not in used:
            used.append(idea["title"])
        self._script_request(prompt, idea.get("title", "video"), shorts, words, new_video=True)

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

    # Kept when a script for a new idea starts a new project; everything else belongs to the old video.
    SESSION_KEYS = ("niche_main", "niche_sub", "ideas", "used_ideas")

    def _script_request(self, prompt, fallback_title, shorts, words=525, new_video=False, after_done=None):
        """new_video: this script is for a new idea, so it gets its own project (slug, voiceover,
        video, uploads). Revising the current script keeps the current project."""
        # SCRIPT (narration + visual cues + headers) + NARRATION again + META JSON ≈ 2.4× the spoken text
        expect = int(words * 6 * 2.4 + 900)

        def work():
            return self.ask_ai(prompt, cwd=HOME, expect_chars=expect)

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
            if new_video and self.s.get("slug"):
                # Start a new project. Reusing the old slug made the new video overwrite the old one's
                # voiceover in work\ and wipe its finished project folder when Animate ran.
                self.s = {k: self.s[k] for k in self.SESSION_KEYS if k in self.s}
                self._clear_upload_page()
            slug = self.s.get("slug") or (slugify(title) + datetime.now().strftime("-%m%d%H%M"))
            if narration != self.s.get("narration"):
                for key in ("voice", "video", "thumb", "script_file"):
                    self.s.pop(key, None)
            self.s.update({"script": script, "narration": narration, "meta": meta, "title": title,
                           "slug": slug, "shorts": shorts, "lang": "en",
                           "narration_en_hash": narration_hash(narration)})
            self.txt_script.delete("1.0", "end")
            self.txt_script.insert("1.0", script + self._meta_block(meta))
            self.save_state()
            if after_done:
                after_done()
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
        prompt = ("Import this script faithfully in English. Translate non-English content; keep existing "
                  "English wording and meaning. Do not expand or shorten the narration. Extract spoken words "
                  "separately from timestamps and directions.\n\n" + text + "\n\n" + self.SCRIPT_FORMAT)
        self._script_request(prompt, title, False, max(1, len(text.split())), new_video=True)

    def script_next(self):
        text = self.txt_script.get("1.0", "end").strip()
        if not text:
            messagebox.showinfo("Script", "Write or load a script first.")
            return
        text = text.split("\n\n──────── extras ────────")[0]
        if text != self.s.get("script") or not self.s.get("narration_en_hash"):
            prompt = ("Normalize this edited script into English without changing its meaning or expanding "
                      "its narration. Keep English spoken words unchanged; translate other languages. "
                      "Extract the exact narration from the edited text, not from an older version.\n\n"
                      + text + "\n\n" + self.SCRIPT_FORMAT)
            self._script_request(prompt, self.s.get("title", "My video"), self.s.get("shorts", False),
                                 max(1, len(text.split())), after_done=lambda: self.show("voice"))
            return
        if not self.s.get("slug"):
            self.s["title"] = self.s.get("title") or "My video"
            self.s["slug"] = slugify(self.s["title"]) + datetime.now().strftime("-%m%d%H%M")
        self.save_state()
        self.show("voice")

    # ================================================================== VOICE PAGE
    def _page_voice(self, p):
        self.header(p, "② Voiceover", "English narration: Microsoft Neural voices (online) or Piper voices that run on this PC "
                    "(offline). Imported recordings must also be in English.")
        eng = self.card(p)
        ctk.CTkLabel(eng, text="Voice engine").grid(row=0, column=0, padx=(16, 6), pady=12)
        self.opt_engine = ctk.CTkSegmentedButton(eng, values=[piper_voice.ENGINE, "Free (Edge)"], command=self._on_engine)
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
        self.opt_voice.set(english_voice(self.settings.get("voice")))
        self.opt_voice.grid(row=0, column=1)
        ctk.CTkLabel(c, text="Speed").grid(row=0, column=2, padx=(18, 6))
        self.sld_rate = ctk.CTkSlider(c, from_=-30, to=30, number_of_steps=12, width=160,
                                      command=lambda v: self.lbl_rate.configure(text=f"{int(v):+d}%"))
        self.sld_rate.set(self.settings.get("rate", -5))
        self.sld_rate.grid(row=0, column=3)
        self.lbl_rate = ctk.CTkLabel(c, text=f"{int(self.sld_rate.get()):+d}%", width=50)
        self.lbl_rate.grid(row=0, column=4)
        ctk.CTkButton(c, text="🎙 Generate voiceover", height=36, command=self.make_voice).grid(row=0, column=5, padx=12)
        ctk.CTkButton(c, text="📂 English recording…", height=36, fg_color="#1d222b", hover_color="#272d38",
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
        self.opt_engine.set(self.settings.get("engine", piper_voice.ENGINE))
        self._on_engine(self.opt_engine.get())

    def _on_engine(self, v):
        if not self.offline():                      # offline mode forces Piper without changing the choice
            self.settings["engine"] = piper_voice.ENGINE if v == piper_voice.ENGINE else "Free (Edge)"
        piper = self.offline() or self.settings["engine"] == piper_voice.ENGINE
        self.opt_engine.set(piper_voice.ENGINE if piper else "Free (Edge)")
        self.el_frame.grid_forget()
        shown = self.opt_voice.get()               # keep the voice picked for the other engine
        self.settings["piper_voice" if shown in piper_voice.VOICES else "voice"] = shown
        self.opt_voice.configure(state="normal", values=piper_voice.VOICES if piper else VOICES)
        self.opt_voice.set(piper_voice.piper_voice(self.settings.get("piper_voice")) if piper
                           else english_voice(self.settings.get("voice")))

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

    VOICE_WORKERS = 3   # passages voiced at the same time (Edge streams ~real-time, so this is ~3x faster)

    def _make_voice_edge(self, text, d, out, voice, rate):
        """Edge neural voice in passages (as in reddit-video-generator): cached, 3 tries each,
        VOICE_WORKERS passages at once, joined in order."""
        import asyncio
        import edge_tts
        voice = english_voice(voice)
        rate_s = f"{rate:+d}%"
        parts = self._speech_chunks(text)
        if not parts:
            raise RuntimeError("The narration is empty.")
        cache = d / "voice_parts"
        cache.mkdir(exist_ok=True)
        n = len(parts)
        files = [cache / (hashlib.sha256((voice + "\n" + rate_s + "\n" + p).encode()).hexdigest()[:24] + ".mp3")
                 for p in parts]
        state = {"done": sum(1 for f in files if f.exists() and f.stat().st_size > 0), "retries": 0}
        failed = {}

        def report():
            extra = f" · {state['retries']} retried" if state["retries"] else ""
            self.prog(state["done"] / n * 0.95, f"voice passages {state['done']}/{n} done "
                                                f"({min(self.VOICE_WORKERS, n - state['done'])} at a time){extra}")

        async def one(i, sem):
            mp3 = files[i]
            if mp3.exists() and mp3.stat().st_size > 0:
                return
            async with sem:
                for attempt in range(3):
                    self.check_cancel()
                    partial = mp3.with_name(mp3.stem + ".partial.mp3")
                    try:
                        await asyncio.wait_for(edge_tts.Communicate(parts[i], voice=voice, rate=rate_s,
                                                                  receive_timeout=30)
                                               .save(str(partial)), timeout=180)
                        if not partial.is_file() or partial.stat().st_size == 0:
                            raise RuntimeError("no speech received")
                        os.replace(partial, mp3)
                        break
                    except Exception as exc:
                        partial.unlink(missing_ok=True)
                        if self._cancel:
                            raise RuntimeError("Stopped.")
                        if attempt == 2:
                            failed[i] = exc
                            return  # Let the other passages finish before serial recovery.
                        state["retries"] += 1
                        report()
                        await asyncio.sleep(attempt + 1)
                    finally:
                        partial.unlink(missing_ok=True)
            state["done"] += 1
            report()

        async def run_all():
            sem = asyncio.Semaphore(self.VOICE_WORKERS)
            tasks = [asyncio.create_task(one(i, sem)) for i in range(n)]
            try:
                await asyncio.gather(*tasks)
            except BaseException:
                for t in tasks:
                    t.cancel()
                await asyncio.gather(*tasks, return_exceptions=True)
                raise
            for i in failed:
                self.check_cancel()
                self.prog(state["done"] / n * 0.95,
                          f"recovering voice passage {i + 1}/{n} in smaller pieces, one at a time")
                recovered = []
                for piece in self._speech_chunks(parts[i], limit=450):
                    key = hashlib.sha256((voice + "\n" + rate_s + "\n" + piece).encode()).hexdigest()[:24]
                    dest = cache / (key + ".mp3")
                    recovered.append(dest)
                    if dest.exists() and dest.stat().st_size:
                        continue
                    partial = dest.with_name(dest.stem + ".partial.mp3")
                    for attempt in range(3):
                        self.check_cancel()
                        try:
                            await asyncio.wait_for(edge_tts.Communicate(piece, voice=voice, rate=rate_s,
                                                                      receive_timeout=30)
                                                   .save(str(partial)), timeout=90)
                            if not partial.is_file() or not partial.stat().st_size:
                                raise RuntimeError("no speech received")
                            os.replace(partial, dest)
                            break
                        except Exception as exc:
                            partial.unlink(missing_ok=True)
                            self.check_cancel()
                            if attempt == 2:
                                raise RuntimeError(
                                    f"Microsoft returned no usable speech for passage {i + 1}/{n}, even after "
                                    f"retrying smaller pieces one at a time ({exc}).\n\n"
                                    "This can be a temporary voice-service failure. Wait a few minutes, then "
                                    "press Auto again. Completed passages and recovery pieces are cached.") from exc
                            state["retries"] += 1
                            await asyncio.sleep(3 * (attempt + 1))
                        finally:
                            partial.unlink(missing_ok=True)
                assembled = files[i].with_name(files[i].stem + ".partial.mp3")
                try:
                    self._join_mp3(recovered, assembled)
                    os.replace(assembled, files[i])
                finally:
                    assembled.unlink(missing_ok=True)
                state["done"] += 1
                report()
        report()
        asyncio.run(run_all())
        self.prog(0.97, "joining passages")
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
        rate, shown = int(self.sld_rate.get()), self.opt_voice.get()
        piper = bool(self.settings.get("offline")) or self.settings.get("engine") == piper_voice.ENGINE
        if piper:
            voice = piper_voice.piper_voice(shown if shown in piper_voice.VOICES else self.settings.get("piper_voice"))
            self.settings.update({"piper_voice": voice, "rate": rate})
        else:
            voice = english_voice(shown)
            self.settings.update({"voice": voice, "rate": rate, "engine": "Free (Edge)"})
        self.opt_voice.set(voice)
        out = d / "voiceover.mp3"
        english_verified = self.s.get("narration_en_hash") == narration_hash(text)

        def work():
            narration = text if english_verified else self.ask_ai(normalize_narration_prompt(text), cwd=HOME)
            self.check_cancel()
            (d / "script.txt").write_text(narration + "\n", encoding="utf-8")
            (d / "voiceover.srt").unlink(missing_ok=True)   # leftover from the old single-request method
            if piper:
                self.prog(None, f"speaking with the Piper voice {voice} (on this PC)")
                return piper_voice.speak(narration, out, voice=voice, rate=rate, folder=PIPER_DIR, env=ENV), narration
            return self._make_voice_edge(narration, d, out, voice, rate), narration

        def done(o):
            audio, narration = o
            self.s.pop("video", None)
            self.s.pop("thumb", None)
            self.s.update({"voice": str(audio), "lang": "en", "narration": narration,
                           "narration_en_hash": narration_hash(narration),
                           "speech_engine": "piper-offline" if piper else "microsoft-neural"})
            self.txt_narr.delete("1.0", "end")
            self.txt_narr.insert("1.0", narration)
            self.save_state()
            self._sync_voice_page()
        self.run_job("Generating voiceover", work, done)

    def pick_voice(self):
        f = filedialog.askopenfilename(filetypes=[("Audio", "*.mp3 *.wav *.m4a *.flac *.ogg *.aac"), ("All", "*.*")])
        if f:
            text, d = self._save_narration()
            def work():
                self.prog(0.1, "Checking that the recording is English")
                verify_english_recording(f, ENV, NO_WINDOW)
                return text if self.s.get("narration_en_hash") == narration_hash(text) else self.ask_ai(normalize_narration_prompt(text), cwd=HOME)
            def done(narration):
                (d / "script.txt").write_text(narration + "\n", encoding="utf-8")
                self.s.pop("video", None)
                self.s.pop("thumb", None)
                self.s.update({"voice": f, "lang": "en", "narration": narration,
                               "narration_en_hash": narration_hash(narration), "speech_engine": "imported-english"})
                self.txt_narr.delete("1.0", "end")
                self.txt_narr.insert("1.0", narration)
                self.save_state()
                self._sync_voice_page()
            self.run_job("Checking English recording", work, done)

    # ================================================================== ANIMATE PAGE
    def _page_animate(self, p):
        self.header(p, "③ Animate — GrowKaz Stickman Studio", "the selected agent runs the make-2d-video skill end to end: "
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
        self.opt_res.set(DEFAULT_RESOLUTION)
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
        self.chk_auto = ctk.CTkCheckBox(g, text="Full auto (Claude/Gemini only)")
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
        ctk.CTkLabel(g, text="Parts: long videos are built in several AI passes (Auto = one part per ~2.5 min), "
                             "like splitting the script in the tutorial — then rendered as one final MP4.",
                     text_color="#7c8594", font=ctk.CTkFont(size=11)).grid(row=4, column=0, columnspan=8, sticky="w", pady=(4, 0))
        self.opt_aspect.configure(command=lambda v: self.chk_capt.select() if v == "9:16" else self.chk_capt.deselect())
        self.music_file = None

        row = ctk.CTkFrame(p, fg_color="transparent")
        row.pack(fill="x", pady=8)
        ctk.CTkButton(row, text="🎬 Make the video (automatic)", height=42, font=ctk.CTkFont(size=15, weight="bold"),
                      command=self.make_video).pack(side="left")
        ctk.CTkButton(row, text="💻 Open animation agent (interactive)", height=42, fg_color="#1d222b",
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
        if self.s.get("lang") != "en":
            raise RuntimeError("This voiceover has not been verified as English. Generate an English voiceover first.")
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
- Narration language: English only (en). Use --lang en for transcription/alignment.
- All captions, subtitles and on-screen text: English only; preserve the English spoken words.
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
        """Split the build into n AI passes; files on disk carry state between passes."""
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
        if self.settings.get("animation_provider") == OPENART:
            return self._suggest_characters_openart()
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
        self.log(self.anim_log, "🎨 Asking the animation agent for 4 character designs…")
        tools = ["Bash", "Read", "Write", "Edit", "MultiEdit", "Glob", "Grep", "Skill", "TodoWrite"]

        def work():
            out_dir = STUDIO / "projects" / slug / "build" / "char_styles"
            stop = threading.Event()
            self._anim_hint, t0 = "Animation agent is reading the skill", time.time()

            def watch():   # 4 stills to make; each one that appears is a quarter of the work
                while not stop.wait(1.5):
                    n = len([p for p in out_dir.glob("*.png") if p.stat().st_mtime >= t0 - 1]) if out_dir.is_dir() else 0
                    self.prog(0.1 + 0.85 * min(n, 4) / 4, f"{n}/4 designs rendered · {self._anim_hint}")
            threading.Thread(target=watch, daemon=True).start()
            try:
                res = self.ask_ai(prompt, box=self.anim_log, tools=tools, full_auto=bool(self.chk_auto.get()),
                                      cwd=STUDIO, on_tool=self._anim_tool_hint)
            finally:
                stop.set()
            opts = []
            for m in re.finditer(r"CHAR_STYLE:\s*(\d+)\s*\|\s*([^|]+)\|\s*([^|]+)\|\s*(.+)", res):
                opts.append((m.group(1), m.group(2).strip(), m.group(3).strip(), m.group(4).strip().strip("`\"")))
            if not opts:
                raise RuntimeError("Animation agent did not return character options — see the log.")
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
        if self.settings.get("animation_provider") == OPENART:
            return self._make_video_openart()
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
                 "BashOutput", "KillShell", "KillBash", "Monitor", "TaskOutput", "TaskStop",
                 # Windows: Claude Code prefers its PowerShell tool; without it every call is denied.
                 "PowerShell",
                 # context-mode plugin (if installed) clips long output and points at its own tools,
                 # so those must be allowed or Claude can't read long logs at all.
                 "mcp__plugin_context-mode_context-mode"]
        dur = self._voice_duration()
        sel = self.opt_parts.get()
        n = max(1, min(6, round(dur / 150))) if sel == "Auto" else int(sel)
        prompts = [prompt] if n == 1 else self._part_prompts(n, dur or 60)
        self.anim_log.delete("1.0", "end")
        self.log(self.anim_log, f"▶ Starting animation agent in {STUDIO}  —  voiceover {dur:.0f}s, "
                                f"{len(prompts)} pass{'es' if len(prompts) > 1 else ''}")

        def work():
            res = ""
            t0 = time.time()
            stop = threading.Event()
            self._anim_hint = "Animation agent is reading the skill"
            threading.Thread(target=self._watch_pipeline, args=(self.s["slug"], t0, stop), daemon=True).start()
            try:
                if self._job_ai.get('animation_provider', 'Claude') == 'OpenAI (Codex)':
                    self.log(self.anim_log, 'Codex stays sandboxed; the app renders contact sheets and the final video.')
                    project = STUDIO / 'projects' / self.s['slug']
                    def ask(pr):
                        return self.ask_ai(pr + f'\nYour writable workspace is {project}. '
                                           f'The installed studio is {STUDIO}; read its tools and engine, '
                                           'but write only within this project. Use absolute tool paths or '
                                           'change directory to the studio when calling its Python tools. '
                                           'Keep any new temporary/model cache files inside this project.',
                                           box=self.anim_log, tools=tools, full_auto=False, cwd=project,
                                           on_tool=self._anim_tool_hint)
                    def run(cmd):
                        lines = []
                        def receive(line):
                            lines.append(line)
                            self.log(self.anim_log, line)
                        rc = self.run_cmd(cmd, cwd=str(STUDIO), on_line=receive)
                        return rc, '\n'.join(lines)
                    host = HostAnimation(STUDIO, self.s['slug'], PY, run, ask, self.check_cancel)
                    host.project.mkdir(parents=True, exist_ok=True)
                    return host.execute(prompts, dur)
                for i, pr in enumerate(prompts, 1):
                    self.check_cancel()
                    if len(prompts) > 1:
                        self.log(self.anim_log, f"\n━━━━━━━━ Pass {i} of {len(prompts)} ━━━━━━━━")
                    self._anim_pass = f"pass {i}/{len(prompts)} · " if len(prompts) > 1 else ""
                    res = self.ask_ai(pr, box=self.anim_log, tools=tools, full_auto=full, cwd=STUDIO,
                                          on_tool=self._anim_tool_hint)
            finally:
                stop.set()
            m = re.search(r"FINAL_VIDEO:\s*(.+\.mp4)", res)
            path = m.group(1).strip().strip('"`') if m else None
            if not path or not Path(path).exists():   # only this video's own output, never another project's
                own = STUDIO / "projects" / self.s["slug"] / "out"
                mp4s = [p for p in own.glob("*.mp4") if p.stat().st_mtime >= t0] if own.is_dir() else []
                path = str(max(mp4s, key=lambda p: p.stat().st_mtime)) if mp4s else None
            return path

        self.run_job("Making the video", work, self._video_done)

    def _video_done(self, path):
        if path:
            self.s["video"] = str(path)
            self.save_state()
            self.log(self.anim_log, f"🎉 Video ready: {path}")
            if not self._auto and messagebox.askyesno("Video ready", f"{path}\n\nOpen it now?"):
                open_path(path)
        else:
            messagebox.showwarning("Animate", "Animation agent finished but no MP4 was found. Read the log, "
                                              "or continue in the interactive agent window.")

    # ---- OpenArt: AI-generated shots cut to the narration (no GrowKaz kit, no agent)
    def _openart_ready(self):
        if self.offline():
            raise RuntimeError("OpenArt needs the internet. Turn off \"Always work offline\" in Setup, "
                               "or choose another animation provider.")
        if not which("ffmpeg") or not which("ffprobe"):
            raise RuntimeError("FFmpeg is missing. Run the installer from Setup.")
        openart_provider.command(ENV, "version")   # raises with the Setup hint when the CLI is missing

    def _openart_models(self):
        return (self.settings.get("openart_image_model", "").strip() or openart_provider.DEFAULT_IMAGE_MODEL,
                self.settings.get("openart_video_model", "").strip() or openart_provider.DEFAULT_VIDEO_MODEL)

    def _make_video_openart(self):
        try:
            if self.settings.get("openart_save_credits", True):
                self.opt_res.set(DEFAULT_RESOLUTION)
            self._video_prompt()   # checks the voiceover and saves aspect, resolution and look notes
            self._openart_ready()
        except RuntimeError as e:
            messagebox.showinfo("Animate", str(e))
            return
        dur = self._voice_duration()
        if dur <= 0:
            messagebox.showinfo("Animate", "Could not read the voiceover length (ffprobe). Make the voiceover again.")
            return
        project = self._workdir()
        try:
            saved = json.loads((project / "openart" / "plan.json").read_text(encoding="utf-8"))
        except (OSError, ValueError):
            saved = None
        options = build_options(self.settings, shorts=bool(self.s.get("shorts")), saved=saved,
                                voice=self.s["voice"], duration=dur, aspect=self.opt_aspect.get())
        seconds, motion, parallel = options["seconds"], options["motion"], options["parallel"]
        image_model, video_model = self._openart_models()
        n = len(shots_video.slices(dur, seconds))
        what = (f"one {image_model} still and one {video_model} clip each" if motion
                else f"one {image_model} still each, animated by FFmpeg")
        if not self._auto and not messagebox.askyesno(
                "OpenArt", f"This makes {n} AI shots of about {seconds:g} s ({what}) for a {dur:.0f} s voiceover, "
                           "using your OpenArt credits. Finished shots are kept if it stops half way.\n\nContinue?"):
            return
        music = self.music_file if self.music_file and self.opt_music.get().startswith("Track") else None
        self.anim_log.delete("1.0", "end")
        if options["resuming"]:
            self.log(self.anim_log, "Continuing the existing shot plan to reuse paid media; new defaults apply to new projects.")
        elif options["economy"]:
            self.log(self.anim_log, f"Save credits: images only, local reframing, {DEFAULT_RESOLUTION}. No paid AI video clips.")
        self.log(self.anim_log, f"▶ OpenArt: {n} shots × ~{seconds:g} s for a {dur:.0f} s voiceover → {project}")
        if self.opt_music.get() == "Generated by mood":
            self.log(self.anim_log, "Music by mood is made by the GrowKaz kit; an OpenArt video uses your own track or none.")
        if self.chk_capt.get():
            self.log(self.anim_log, "Burned-in captions are not available for OpenArt videos (no word timestamps).")
        narration = self.s.get("narration") or Path(self.s["script_file"]).read_text(encoding="utf-8")
        aspect, resolution = self.opt_aspect.get(), self.opt_res.get()

        def work():
            def run(cmd):
                return self._openart_run(cmd, project)
            openart_provider.account(run, ENV)   # a clear "Sign in" error before any credit is spent
            build = shots_video.ShotsBuild(
                project, folder="openart",
                make_still=lambda prompt, asp, dest: openart_provider.generate(
                    run, ENV, "image", prompt, dest, model=image_model, aspect=asp),
                make_clip=lambda prompt, still, asp, res, dest: openart_provider.generate(
                    run, ENV, "video", prompt, dest, model=video_model, image=still, aspect=asp, resolution=res),
                ask=lambda pr: self.ask_ai(pr, box=self.anim_log), run=run, progress=self.prog,
                check=self.check_cancel, log=lambda text: self.log(self.anim_log, text))
            return build.execute(voice=self.s["voice"], duration=dur, narration=narration,
                                 title=self.s.get("title", self.s["slug"]), aspect=aspect, resolution=resolution,
                                 look=self.ent_look.get().strip(), seconds=seconds, motion=motion, music=music,
                                 out_name=self.s.get("title") or self.s["slug"], parallel=parallel,
                                 reframe=options["economy"])
        self.run_job("Making the video (OpenArt)", work, self._video_done)

    def _suggest_characters_openart(self):
        try:
            self._openart_ready()
        except RuntimeError as e:
            messagebox.showinfo("Character styles", str(e))
            return
        looks = [("Rim-lit stick figure", "a minimal black stick figure with a glowing rim light on a dark, moody "
                                          "cinematic set"),
                 ("Detailed silhouette", "a detailed human figure seen from behind, with clothes and hair, in warm "
                                         "cinematic light"),
                 ("Rounded chibi", "a rounded chibi character made of simple shapes, soft studio light, playful colours"),
                 ("Painterly", "a painterly illustrated character with visible brush strokes, muted palette and "
                               "dramatic light")]
        title, look, aspect = self.s.get("title", ""), self.ent_look.get().strip(), self.opt_aspect.get() or "16:9"
        image_model = self._openart_models()[0]
        out_dir = self._workdir() / "char_styles"
        self.anim_log.delete("1.0", "end")
        self.log(self.anim_log, f"🎨 Asking OpenArt ({image_model}) for 4 character designs…")

        def work():
            run = lambda cmd: self._openart_run(cmd, out_dir.parent)
            openart_provider.account(run, ENV)
            opts = []
            for i, (name, desc) in enumerate(looks, 1):
                self.check_cancel()
                self.prog(0.05 + 0.9 * (i - 1) / len(looks), f"design {i}/{len(looks)}: {name}")
                prompt = (f"Character design for a faceless YouTube video titled '{title}': {desc}. "
                          f"{look + '. ' if look else ''}Full body, plain background, no readable text, no logos.")
                still = openart_provider.generate(run, ENV, "image", prompt, out_dir / str(i), model=image_model,
                                                  aspect=aspect)
                self.log(self.anim_log, f"🖼 {i}. {name}: {still}")
                opts.append((str(i), name, desc, str(still)))
            return opts
        self.run_job("Designing characters", work, self._pick_character)

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
        provider = self.settings.get("animation_provider", "Claude")
        if provider == OPENART:
            messagebox.showinfo("Animate", "OpenArt has no interactive agent: the studio generates the shots "
                                           "itself. Use \"Make the video (automatic)\".")
            return
        prompt = english_prompt(prompt)
        if provider != "Claude":
            prompt = portable_prompt(prompt, SKILLS_DIR / "make-2d-video", True)
        f = self._workdir() / "animation_prompt.txt"
        f.write_text(prompt, encoding="utf-8")
        self.clipboard_clear()
        self.clipboard_append(prompt)
        try:
            cmd = cli_command(provider, ENV)
        except RuntimeError as e:
            messagebox.showerror(provider, str(e))
            return
        messagebox.showinfo(provider, "The video prompt is copied to your clipboard.\n\n"
                            "In the agent window that opens, paste it (right-click or Ctrl+V) and press Enter.")
        subprocess.Popen(["cmd", "/k", *cmd], cwd=str(STUDIO), env=ENV, creationflags=subprocess.CREATE_NEW_CONSOLE)

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
        if self.s.get("slug") and not d.exists() and (WORK / self.s["slug"] / "openart").exists():
            d = WORK / self.s["slug"]   # an OpenArt video lives in the work folder, not in the kit
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
        self.btn_publish = ctk.CTkButton(r4, text="🚀 Publish to YouTube", height=42,
                                         font=ctk.CTkFont(size=15, weight="bold"), command=self.upload)
        self.btn_publish.pack(side="left")
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
        if not self.thumb_path and self.s.get("thumb") and Path(self.s["thumb"]).exists():
            self._show_thumb(self.s["thumb"])

    def _show_thumb(self, path):
        try:
            from PIL import Image
            img = Image.open(path)
            img.thumbnail((340, 191))
            self._thumb_img = ctk.CTkImage(light_image=img, dark_image=img, size=img.size)
            set_label_image(self.thumb_preview, self._thumb_img, "")
            self.thumb_path = str(path)
            self.s["thumb"] = str(path)
            self.save_state()
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
        text = drawable(self.ent_thumb_text.get()).upper()
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

    @staticmethod
    def _scopes_ok(granted):
        """True if a token's granted scopes allow uploading and reading the channel."""
        g = {s.rsplit("/", 1)[-1] for s in (granted or [])}
        full = bool(g & {"youtube", "youtube.force-ssl"})
        return ("youtube.upload" in g or full) and ("youtube.readonly" in g or full)

    def _yt_service(self):
        from google.auth.transport.requests import Request
        from google.oauth2.credentials import Credentials
        from google_auth_oauthlib.flow import InstalledAppFlow
        from googleapiclient.discovery import build
        tok, secret = YT_DIR / "token.json", YT_DIR / "client_secret.json"
        # Load with the scopes the token was actually granted. Forcing self.SCOPES makes the refresh
        # ask Google for scopes the user never granted (e.g. youtube.readonly on a token that has
        # the broader "youtube" scope), and Google answers invalid_scope.
        creds = Credentials.from_authorized_user_file(str(tok)) if tok.exists() else None
        if creds and not self._scopes_ok(creds.scopes):
            creds = None   # token lacks upload or read access: sign in again with SCOPES
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
            self.lbl_up.configure(text=f"Published ✔  {url}")
            self.btn_publish.configure(fg_color=ACCENT, hover_color=ACCENT_HOVER, text_color="#ffffff")
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
