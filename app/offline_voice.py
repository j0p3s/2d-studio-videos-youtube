"""Voiceover with the voices built into Windows (no internet, nothing to install).

They sound more robotic than the online Edge voices; this is the fallback for offline work.
"""
import os
import subprocess
import tempfile
from pathlib import Path

NO_WINDOW = 0x08000000 if os.name == "nt" else 0

_SCRIPT = r"""
$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Speech
$s = New-Object System.Speech.Synthesis.SpeechSynthesizer
$voices = @($s.GetInstalledVoices() | Where-Object { $_.Enabled } | ForEach-Object { $_.VoiceInfo })
if ($env:STUDIO_VOICE_LIST) { $voices | ForEach-Object { $_.Name + '|' + $_.Culture.Name }; exit 0 }
$pick = $voices | Where-Object { $_.Name -eq $env:STUDIO_VOICE_NAME } | Select-Object -First 1
if (-not $pick) { $pick = $voices | Where-Object { $_.Culture.Name -like 'en*' } | Select-Object -First 1 }
if (-not $pick) { throw 'No English Windows voice is installed. Add one in Windows Settings > Time & language > Speech.' }
$s.SelectVoice($pick.Name)
$s.Rate = [int]$env:STUDIO_VOICE_RATE
$s.SetOutputToWaveFile($env:STUDIO_VOICE_OUT)
$s.Speak([IO.File]::ReadAllText($env:STUDIO_VOICE_TEXT, [Text.Encoding]::UTF8))
$s.Dispose()
"""


def sapi_rate(percent):
    """Edge-style speed in percent (-50..+50) to the Windows scale (-10..+10)."""
    return max(-10, min(10, round(percent / 5)))


def _powershell(extra):
    env = dict(os.environ)
    env.update(extra)
    return subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass",
                           "-Command", _SCRIPT], env=env, capture_output=True, text=True,
                          encoding="utf-8", errors="replace", creationflags=NO_WINDOW)


def voices():
    """Installed Windows voices as (name, culture) pairs; empty when none can be listed."""
    try:
        result = _powershell({"STUDIO_VOICE_LIST": "1"})
    except OSError:
        return []
    return [tuple(line.split("|", 1)) for line in result.stdout.splitlines() if "|" in line]


def speak(text, out_mp3, *, rate=0, voice="", ffmpeg="ffmpeg", env=None):
    """Speak text into out_mp3 with a Windows voice. Returns out_mp3."""
    out_mp3 = Path(out_mp3)
    with tempfile.TemporaryDirectory() as folder:
        source, wav = Path(folder) / "narration.txt", Path(folder) / "narration.wav"
        source.write_text(text, encoding="utf-8")
        result = _powershell({"STUDIO_VOICE_TEXT": str(source), "STUDIO_VOICE_OUT": str(wav),
                              "STUDIO_VOICE_RATE": str(sapi_rate(rate)), "STUDIO_VOICE_NAME": voice})
        if result.returncode != 0 or not wav.is_file() or wav.stat().st_size < 1000:
            raise RuntimeError("The Windows voice failed: " + (result.stderr or result.stdout or "no audio").strip()[-400:])
        done = subprocess.run([ffmpeg, "-y", "-v", "error", "-i", str(wav), "-c:a", "libmp3lame", "-b:a", "192k",
                               str(out_mp3)], capture_output=True, text=True, env=env, creationflags=NO_WINDOW)
        if done.returncode != 0:
            raise RuntimeError("ffmpeg could not convert the voiceover:\n" + (done.stderr or "")[-400:])
    return out_mp3
