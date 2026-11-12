"""Voiceover with Qwen3-TTS: an expressive neural voice that runs on this PC's graphics card.

It follows a speaking-style instruction, so the narration can be calm and relaxing. Qwen3-TTS needs
PyTorch and pinned libraries, so it lives in its own Python environment (.venv-qwen) and speaks in a
separate process: the studio's own packages stay untouched and the graphics memory is free again
for rendering as soon as the voiceover is done.

This file is both the studio side (no heavy imports) and, run as a script inside .venv-qwen, the
worker that loads the model:  python qwen_voice.py job.json
"""
import hashlib
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

NO_WINDOW = 0x08000000 if os.name == "nt" else 0
ENGINE = "Qwen3 (calm, on this PC)"
MODEL = "Qwen/Qwen3-TTS-12Hz-1.7B-CustomVoice"
DOWNLOAD_NOTE = "about 8 GB once: PyTorch and the Qwen3-TTS voice model"
TORCH_CUDA_INDEX = "https://download.pytorch.org/whl/cu128"

# Preset speakers of the CustomVoice model, shown as "Name · description".
VOICES = ["Aiden · clear American male", "Ryan · dynamic male", "Serena · warm, gentle female",
          "Uncle_Fu · low, mellow male", "Vivian · bright young female", "Sohee · warm female"]
DEFAULT_VOICE = VOICES[0]
STYLES = {
    "Calm & relaxing": "Speak slowly in a calm, soft, soothing and relaxed tone, with gentle pacing "
                       "and natural pauses, like a peaceful late-evening narration.",
    "Warm storyteller": "Speak in a warm, friendly, unhurried storytelling tone with a gentle smile.",
    "Sleepy & very soft": "Speak very slowly and very softly, almost whispering, in a sleepy, "
                          "comforting bedtime-story tone.",
    "Neutral": "",
}
DEFAULT_STYLE = "Calm & relaxing"
CHUNK_CHARS = 500      # one passage per model call; long calls drift and can be cut off
PAUSE_SECONDS = 0.35   # silence added after each passage


def qwen_voice(saved):
    return saved if saved in VOICES else DEFAULT_VOICE


def qwen_style(saved):
    return saved if saved in STYLES else DEFAULT_STYLE


def speaker(voice):
    return qwen_voice(voice).split(" · ")[0]


def venv_python(home):
    folder = Path(home) / ".venv-qwen"
    return folder / ("Scripts/python.exe" if os.name == "nt" else "bin/python")


def model_dir(home):
    return Path(home) / ".cache" / "qwen3-tts" / MODEL.split("/")[1]


def installed(home):
    return venv_python(home).is_file() and (model_dir(home) / "config.json").is_file() \
        and (model_dir(home) / ".complete").is_file()


def install(home, python, run, progress=lambda frac, text: None):
    """Create .venv-qwen, install PyTorch and qwen-tts into it and download the voice model.

    run(cmd) runs a command, streams its output to the studio log and returns the exit code.
    Finished steps are skipped, so a stopped or failed install continues where it ended.
    """
    py = venv_python(home)

    def step(frac, text, cmd):
        progress(frac, text)
        if run([str(c) for c in cmd]) != 0:
            raise RuntimeError(f"Qwen3-TTS setup stopped while {text}. Check the internet connection "
                               "and free disk space, then try again; finished steps are kept.")

    def has(module):
        return py.is_file() and subprocess.run([str(py), "-c", f"import {module}"], capture_output=True,
                                               creationflags=NO_WINDOW).returncode == 0
    if not py.is_file():
        step(0.02, "creating the Qwen3 Python environment", [python, "-m", "venv", py.parents[1]])
    if not has("torch"):
        index = ["--index-url", TORCH_CUDA_INDEX] if shutil.which("nvidia-smi") else []
        step(0.05, "downloading PyTorch (about 3 GB)", [py, "-m", "pip", "install", "torch", "torchaudio", *index])
    if not has("qwen_tts"):
        step(0.45, "installing qwen-tts", [py, "-m", "pip", "install", "qwen-tts"])
    target = model_dir(home)
    if not (target / ".complete").is_file():
        target.mkdir(parents=True, exist_ok=True)
        code = ("import sys; from huggingface_hub import snapshot_download; "
                "snapshot_download(sys.argv[1], local_dir=sys.argv[2])")
        step(0.55, "downloading the Qwen3-TTS voice model (about 4.5 GB)", [py, "-c", code, MODEL, target])
        (target / ".complete").write_text(MODEL + "\n", encoding="utf-8")
    progress(1.0, "Qwen3-TTS is ready")


def chunks(text, limit=CHUNK_CHARS):
    """Passages of whole sentences up to limit characters (a longer sentence is split at words)."""
    out, current = [], ""
    for word in text.split():
        if current and len(current) + 1 + len(word) > limit:
            out.append(current)
            current = ""
        current = f"{current} {word}".strip()
        if len(current) > limit * .6 and word.endswith((".", "!", "?", '."', '!"', '?"')):
            out.append(current)
            current = ""
    if current:
        out.append(current)
    return out


def tempo(percent):
    """Speed in percent (+20 = faster) to an ffmpeg atempo factor."""
    return round(1 + max(-50, min(100, percent)) / 100, 3)


def part_path(cache, voice, style, passage):
    key = hashlib.sha256("\n".join([MODEL, speaker(voice), STYLES[qwen_style(style)], passage]).encode()).hexdigest()[:24]
    return Path(cache) / f"qwen-{key}.wav"


def speak(text, out_mp3, *, voice=DEFAULT_VOICE, style=DEFAULT_STYLE, rate=0, home, cache, run,
          progress=lambda frac, text: None, ffmpeg="ffmpeg", env=None):
    """Speak text into out_mp3. Finished passages stay in cache, so a stopped job resumes. Returns out_mp3."""
    if not installed(home):
        raise RuntimeError("Qwen3-TTS is not installed yet. Choose it on the Voiceover page and generate again "
                           "to install it.")
    out_mp3, cache = Path(out_mp3), Path(cache)
    cache.mkdir(parents=True, exist_ok=True)
    parts = chunks(text)
    if not parts:
        raise RuntimeError("The narration is empty.")
    files = [part_path(cache, voice, style, p) for p in parts]
    todo = [{"text": p, "out": str(f)} for p, f in zip(parts, files) if not f.is_file()]
    n = len(parts)
    if todo:
        job = cache / "qwen_job.json"
        job.write_text(json.dumps({"model": str(model_dir(home)), "speaker": speaker(voice),
                                   "instruct": STYLES[qwen_style(style)], "pause": PAUSE_SECONDS,
                                   "parts": todo}), encoding="utf-8")
        state = {"done": n - len(todo), "error": ""}
        progress(None, "loading the Qwen3 voice model (about a minute)")

        def on_line(line):
            if line.startswith("QWEN done"):
                state["done"] += 1
                progress(state["done"] / n * 0.95, f"Qwen3 voice passages {state['done']}/{n} (on this PC)")
            elif line.startswith("QWEN device"):
                progress(None, f"speaking with Qwen3 on {line.split(' ', 2)[2]}")
            elif line.startswith("QWEN error"):
                state["error"] = line[11:]
        code = run([str(venv_python(home)), str(Path(__file__).resolve()), str(job)], on_line=on_line)
        job.unlink(missing_ok=True)
        missing = [f for f in files if not f.is_file()]
        if code != 0 or missing:
            raise RuntimeError("Qwen3-TTS stopped before the voiceover was complete"
                               + (f": {state['error']}." if state["error"] else ".")
                               + f" {n - len(missing)} of {n} passages are saved; generate again to continue.")
    progress(0.97, "joining passages")
    listing = cache / "qwen_parts.txt"
    listing.write_text("".join(f"file '{f.as_posix()}'\n" for f in files), encoding="utf-8")
    speed = ["-af", f"atempo={tempo(rate)}"] if tempo(rate) != 1 else []
    done = subprocess.run([ffmpeg, "-y", "-v", "error", "-f", "concat", "-safe", "0", "-i", str(listing), *speed,
                           "-c:a", "libmp3lame", "-b:a", "192k", str(out_mp3)],
                          capture_output=True, text=True, env=env, creationflags=NO_WINDOW)
    listing.unlink(missing_ok=True)
    if done.returncode != 0:
        raise RuntimeError("ffmpeg could not join the voice passages:\n" + (done.stderr or "")[-400:])
    return out_mp3


def worker(job_file):
    """Runs inside .venv-qwen: load the model once and speak every passage of the job."""
    import numpy
    import soundfile
    import torch
    from qwen_tts import Qwen3TTSModel
    job = json.loads(Path(job_file).read_text(encoding="utf-8"))
    cuda = torch.cuda.is_available()
    print("QWEN device", f"the graphics card ({torch.cuda.get_device_name(0)})" if cuda
          else "the processor (slow: no NVIDIA graphics card found)", flush=True)
    model = Qwen3TTSModel.from_pretrained(job["model"], device_map="cuda:0" if cuda else "cpu",
                                          dtype=torch.bfloat16 if cuda else torch.float32)
    for part in job["parts"]:
        extra = {"instruct": job["instruct"]} if job["instruct"] else {}
        wavs, rate = model.generate_custom_voice(text=part["text"], language="English",
                                                 speaker=job["speaker"], **extra)
        audio = numpy.concatenate([numpy.asarray(wavs[0], dtype=numpy.float32),
                                   numpy.zeros(int(rate * job["pause"]), dtype=numpy.float32)])
        out = Path(part["out"])
        partial = out.with_suffix(".partial.wav")
        soundfile.write(str(partial), audio, rate)
        partial.replace(out)
        print("QWEN done", out.name, flush=True)


if __name__ == "__main__":
    try:
        worker(sys.argv[1])
    except Exception as error:   # one line the studio can show; the traceback goes to the session log
        import traceback
        traceback.print_exc()
        print("QWEN error", str(error).replace("\n", " ")[:300], flush=True)
        sys.exit(1)
