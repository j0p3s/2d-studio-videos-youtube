"""Pick a good thumbnail frame instead of a fixed position in the video.

A fixed 35% landed on a dark text-only shot. Frames are sampled, scored for contrast, sharpness and
vivid subject colour (a lit character, a bright prop) and the best one wins. Title cards, fades and
near-black frames score low.
"""
import subprocess
import tempfile
from pathlib import Path

SAMPLES = 24
SIZE = (108, 192)


def frame_score(img):
    """Higher is a better thumbnail. img: PIL image."""
    from PIL import ImageFilter, ImageStat
    small = img.convert("RGB").resize(SIZE)
    gray = small.convert("L")
    stat = ImageStat.Stat(gray)
    mean, std = stat.mean[0], stat.stddev[0]
    if mean < 14:                       # black or almost black
        return 0.0
    edges = ImageStat.Stat(gray.filter(ImageFilter.FIND_EDGES)).mean[0]
    hsv = small.convert("HSV")
    w, h = SIZE
    centre = hsv.crop((int(w * .15), int(h * .12), int(w * .85), int(h * .78)))
    px = centre.tobytes()
    vivid = sum(1 for i in range(0, len(px), 3) if px[i + 1] > 110 and px[i + 2] > 140) / max(1, len(px) // 3)
    brightness = 1 - abs(mean - 95) / 95   # mid-bright is best, too dark or washed out is not
    return (min(std, 60) / 60 * 0.30 + min(edges, 14) / 14 * 0.25 + min(vivid, 0.2) / 0.2 * 0.30
            + max(brightness, 0) * 0.15)


def best_time(video, duration, ffmpeg="ffmpeg", samples=SAMPLES, env=None, creationflags=0):
    """Seconds into the video of the best-scoring frame, ignoring the first and last 8%."""
    from PIL import Image
    if duration <= 1:
        return duration / 2
    lo, hi = duration * 0.08, duration * 0.92
    with tempfile.TemporaryDirectory() as tmp:
        step = (hi - lo) / samples
        subprocess.run([ffmpeg, "-y", "-v", "error", "-ss", f"{lo:.2f}", "-t", f"{hi - lo:.2f}", "-i", str(video),
                        "-vf", f"fps=1/{step:.4f},scale={SIZE[0]}:{SIZE[1]}", str(Path(tmp) / "f_%03d.png")],
                       capture_output=True, env=env, creationflags=creationflags, check=False)
        scored = []
        for i, path in enumerate(sorted(Path(tmp).glob("f_*.png"))):
            with Image.open(path) as img:
                scored.append((frame_score(img), lo + step * i + step / 2))
    if not scored:
        raise RuntimeError("No frames could be read from the video")
    return max(scored)[1]
