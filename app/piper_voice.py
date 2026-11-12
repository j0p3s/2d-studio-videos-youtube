"""Voiceover with Piper: a neural voice that runs on this PC, so it works with no internet.

Each voice is one model file (60-120 MB) downloaded once into the studio's own cache.
"""
import os
import subprocess
import tempfile
import wave
from pathlib import Path

NO_WINDOW = 0x08000000 if os.name == "nt" else 0
ENGINE = "Piper (offline)"
VOICES = ["en_US-ryan-high", "en_US-lessac-high", "en_US-hfc_female-medium", "en_US-amy-medium",
          "en_US-joe-medium", "en_GB-alan-medium"]
DEFAULT_VOICE = "en_US-joe-medium"


def piper_voice(saved):
    return saved if saved in VOICES else DEFAULT_VOICE


def migrate_voice(settings):
    # The default voice changed from ryan-high to joe-medium. Move every installation to it once;
    # a voice chosen after that is kept.
    if settings.get("piper_voice_default") != DEFAULT_VOICE:
        settings["piper_voice"] = DEFAULT_VOICE
        settings["piper_voice_default"] = DEFAULT_VOICE
    return settings


def length_scale(percent):
    """Edge-style speed in percent (+20 = faster) to Piper's length scale (below 1 = faster)."""
    return round(1 / (1 + max(-50, min(100, percent)) / 100), 3)


def model_path(voice, folder):
    return Path(folder) / f"{voice}.onnx"


def installed(voice, folder):
    model = model_path(voice, folder)
    return model.is_file() and model.stat().st_size > 1_000_000 and Path(str(model) + ".json").is_file()


def download(voice, folder):
    """Download one voice into folder (needs internet once)."""
    from piper.download_voices import download_voice
    Path(folder).mkdir(parents=True, exist_ok=True)
    try:
        download_voice(voice, Path(folder))
    except Exception as error:
        for leftover in (model_path(voice, folder), Path(str(model_path(voice, folder)) + ".json")):
            leftover.unlink(missing_ok=True)
        raise RuntimeError(f'The Piper voice "{voice}" is not downloaded yet and the download failed ({error}). '
                           "Connect to the internet once and try again.") from error
    if not installed(voice, folder):
        raise RuntimeError(f'The Piper voice "{voice}" did not download completely. Try again.')


def speak(text, out_mp3, *, voice=DEFAULT_VOICE, rate=0, folder, ffmpeg="ffmpeg", env=None):
    """Speak text into out_mp3 with a Piper voice. Returns out_mp3."""
    from piper import PiperVoice, SynthesisConfig
    out_mp3 = Path(out_mp3)
    if not installed(voice, folder):
        download(voice, folder)
    model = PiperVoice.load(model_path(voice, folder))
    with tempfile.TemporaryDirectory() as temp:
        wav = Path(temp) / "narration.wav"
        with wave.open(str(wav), "wb") as target:
            model.synthesize_wav(text, target, SynthesisConfig(length_scale=length_scale(rate)))
        done = subprocess.run([ffmpeg, "-y", "-v", "error", "-i", str(wav), "-c:a", "libmp3lame", "-b:a", "192k",
                               str(out_mp3)], capture_output=True, text=True, env=env, creationflags=NO_WINDOW)
        if done.returncode != 0:
            raise RuntimeError("ffmpeg could not convert the voiceover:\n" + (done.stderr or "")[-400:])
    return out_mp3
