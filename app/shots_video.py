"""Build a video from AI-generated shots: slice the voiceover into shots, ask the script AI for
one image prompt and one camera-motion prompt per shot, generate the stills (and optionally a
short clip from each still) with the selected provider, then cut them to the narration with
FFmpeg. No GrowKaz kit, Whisper or agent is involved.

Files are the truth here too: every still and clip is saved under <project>/<folder>/ and a
second run (after a failure, a cancel or an empty credit balance) reuses what already exists.
"""
import hashlib
import json
import math
import re
import shutil
import threading
from concurrent.futures import ThreadPoolExecutor, wait, FIRST_COMPLETED
from pathlib import Path

DEFAULT_CLIP_SECONDS = 6
MIN_CLIP_SECONDS, MAX_CLIP_SECONDS = 3, 20
MAX_SHOTS = 150
FPS = 24
DEFAULT_PARALLEL_SHOTS = 3
MAX_PARALLEL_SHOTS = 4
RESOLUTIONS = {"720p": 720, "1080p": 1080, "1440p": 1440, "2160p": 2160}


def parallel_shots(value=None):
    try:
        return max(1, min(MAX_PARALLEL_SHOTS, int(value)))
    except (ValueError, TypeError, OverflowError):
        return DEFAULT_PARALLEL_SHOTS


def clip_seconds(value):
    try:
        seconds = float(str(value).strip() or DEFAULT_CLIP_SECONDS)
    except ValueError:
        seconds = DEFAULT_CLIP_SECONDS
    return max(MIN_CLIP_SECONDS, min(MAX_CLIP_SECONDS, seconds))


def frame_size(aspect, resolution):
    short = RESOLUTIONS.get(resolution, 1080)
    long = int(round(short * 16 / 9 / 2)) * 2
    return (long, short) if aspect != "9:16" else (short, long)


def slices(duration, seconds):
    """Equal time slices covering the whole voiceover; the last one absorbs the remainder."""
    duration = max(0.5, float(duration))
    n = max(1, min(MAX_SHOTS, int(math.ceil(duration / seconds))))
    step = duration / n
    return [(round(i * step, 3), round(duration if i == n - 1 else (i + 1) * step, 3)) for i in range(n)]


def narration_for(narration, bounds, duration):
    """The words spoken during each slice, estimated from character position (no timestamps needed)."""
    words = narration.split()
    total = sum(len(w) + 1 for w in words) or 1
    out, pos = [], 0.0
    timed = []
    for w in words:
        timed.append((pos / total * duration, w))
        pos += len(w) + 1
    for start, end in bounds:
        out.append(" ".join(w for t, w in timed if start <= t < end or (end == duration and t >= start)))
    return out


def plan_prompt(title, bounds, lines, look, aspect):
    shots = "\n".join(f'{i + 1}. [{a:.1f}s-{b:.1f}s] "{text or "(silence)"}"' for i, ((a, b), text) in enumerate(zip(bounds, lines)))
    return f"""You are the art director of a faceless YouTube video made from AI-generated shots.
Video title: {title}
Frame: {aspect}. Visual style notes from me: {look or 'clean, cinematic, consistent lighting and palette across all shots'}.

Below are the shots, with the exact narration spoken during each one. For EVERY shot write:
- "image": a detailed English text-to-image prompt (subject, setting, lighting, lens, mood). Keep one consistent
  world, palette and character design across all shots. No text, letters, logos or watermarks in the picture.
  Faceless channel: show characters from behind, in silhouette, or in wide shots, never a close-up face.
- "motion": one short English sentence of camera movement for an image-to-video model
  (e.g. "slow push-in", "gentle pan left", "handheld drift", "orbit right"), no new objects.

Shots:
{shots}

Answer with ONLY a JSON array, one object per shot, in order, like:
[{{"n": 1, "image": "...", "motion": "..."}}, ...]"""


def parse_plan(text, n):
    """The AI's JSON turned into exactly n (image, motion) pairs; short answers reuse the previous shot."""
    a, b = text.find("["), text.rfind("]")
    if a < 0 or b <= a:
        raise RuntimeError("The script AI did not return a JSON shot list:\n" + text[:400])
    try:
        items = json.loads(text[a:b + 1])
    except ValueError as e:
        raise RuntimeError(f"The script AI returned broken JSON for the shot list ({e}).")
    by_n, loose = {}, []
    for item in items:
        if not isinstance(item, dict) or not str(item.get("image", "")).strip():
            continue
        entry = (str(item["image"]).strip(), str(item.get("motion") or "slow push-in").strip())
        try:
            by_n[int(item.get("n"))] = entry
        except (TypeError, ValueError):
            loose.append(entry)
    shots, last = [], None
    for i in range(1, n + 1):
        entry = by_n.get(i) or (loose.pop(0) if loose else None) or last
        if entry is None:
            raise RuntimeError("The script AI returned no usable shot prompts.")
        shots.append(entry)
        last = entry
    return shots


def plan_key(voice, duration, seconds, aspect, motion):
    stamp = f"{Path(voice).name}|{duration:.2f}|{seconds}|{aspect}|{int(bool(motion))}"
    return hashlib.sha1(stamp.encode("utf-8")).hexdigest()[:12]


def ffmpeg_still(image, out, seconds, size, zoom_in=True):
    """A Ken Burns segment from one still: slow zoom in (or out) over exactly `seconds`."""
    w, h = size
    frames = max(1, int(round(seconds * FPS)))
    zoom = (f"min(1+0.0010*on,1.25)" if zoom_in else f"max(1.25-0.0010*on,1)")
    vf = (f"scale={w * 2}:{h * 2}:force_original_aspect_ratio=increase,crop={w * 2}:{h * 2},"
          f"zoompan=z='{zoom}':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d={frames}:s={w}x{h}:fps={FPS},"
          f"format=yuv420p")
    return ["ffmpeg", "-y", "-loglevel", "error", "-i", str(image), "-vf", vf, "-frames:v", str(frames),
            "-r", str(FPS), "-an", "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", str(out)]


def ffmpeg_clip(clip, out, seconds, size):
    """Cut or hold (freeze the last frame) a generated clip to exactly `seconds`."""
    w, h = size
    vf = (f"scale={w}:{h}:force_original_aspect_ratio=increase,crop={w}:{h},fps={FPS},"
          f"tpad=stop_mode=clone:stop_duration={seconds:.3f},format=yuv420p")
    return ["ffmpeg", "-y", "-loglevel", "error", "-i", str(clip), "-vf", vf, "-t", f"{seconds:.3f}",
            "-an", "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", str(out)]


def ffmpeg_concat(list_file, out):
    return ["ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", str(list_file),
            "-c", "copy", str(out)]


def ffmpeg_mux(video, voice, out, music=None, music_volume=0.12):
    """Voiceover (and an optional looped, quiet music track) under the silent video."""
    cmd = ["ffmpeg", "-y", "-loglevel", "error", "-i", str(video), "-i", str(voice)]
    if music:
        cmd += ["-stream_loop", "-1", "-i", str(music), "-filter_complex",
                f"[2:a]volume={music_volume}[m];[1:a][m]amix=inputs=2:duration=first:dropout_transition=2[a]",
                "-map", "0:v", "-map", "[a]"]
    else:
        cmd += ["-map", "0:v", "-map", "1:a"]
    return cmd + ["-c:v", "copy", "-c:a", "aac", "-b:a", "192k", "-shortest", str(out)]


def concat_list(segments):
    return "".join("file '" + str(p).replace("\\", "/").replace("'", r"'\''") + "'\n" for p in segments)


def existing(folder, stem, kinds):
    """A finished shot file from an earlier run, whatever extension the provider gave it."""
    return next((p for p in sorted(folder.glob(stem + ".*")) if p.suffix.lower() in kinds), None)


STILL_TYPES = (".png", ".jpg", ".jpeg", ".webp")
CLIP_TYPES = (".mp4", ".webm", ".mov")


class ShotsBuild:
    """One video build. The provider is two callables: make_still(prompt, aspect, dest_dir) and
    make_clip(prompt, still, aspect, resolution, dest_dir), each returning the file it made.
    `ask(prompt)` is the script AI, `run(cmd)` runs FFmpeg and returns (exit code, output),
    `progress(fraction, text)` and `check()` come from the GUI job."""

    def __init__(self, project, *, folder, make_still, make_clip, ask, run, progress, check, log=print):
        self.project = Path(project)
        self.dir = self.project / folder
        self.make_still, self.make_clip = make_still, make_clip
        self.ask, self.run, self.progress, self.check, self.log = ask, run, progress, check, log

    def execute(self, *, voice, duration, narration, title, aspect, resolution, look="", seconds=DEFAULT_CLIP_SECONDS,
                motion=True, music=None, out_name=None, parallel=1):
        seconds = clip_seconds(seconds)
        out_name = out_name or title or "video"
        bounds = slices(duration, seconds)
        key = plan_key(voice, duration, seconds, aspect, motion)
        plan_file = self.dir / "plan.json"
        plan = None
        if plan_file.exists():
            try:
                saved = json.loads(plan_file.read_text(encoding="utf-8"))
                if saved.get("key") == key and len(saved.get("shots", [])) == len(bounds):
                    plan = [tuple(s) for s in saved["shots"]]
                    self.log(f"Reusing the shot plan and the finished shots from the last run.")
            except (ValueError, TypeError, KeyError):
                plan = None
        if plan is None:
            if self.dir.exists():
                shutil.rmtree(self.dir, ignore_errors=True)
            self.dir.mkdir(parents=True, exist_ok=True)
            self.progress(0.02, f"planning {len(bounds)} shots with the script AI")
            lines = narration_for(narration, bounds, duration)
            answer = self.ask(plan_prompt(title, bounds, lines, look, aspect))
            plan = parse_plan(answer, len(bounds))
            plan_file.write_text(json.dumps({"key": key, "voice": str(voice), "duration": duration, "seconds": seconds,
                                             "aspect": aspect, "motion": bool(motion), "shots": plan}, indent=1),
                                 encoding="utf-8")
        self.log(f"{len(plan)} shots of ~{seconds:g}s · {'stills + AI motion' if motion else 'stills with Ken Burns'}"
                 f" · {aspect} {resolution}")
        size = frame_size(aspect, resolution)
        n = len(plan)
        segments = []
        seg_dir = self.dir / "segments"
        seg_dir.mkdir(exist_ok=True)
        stop = threading.Event()
        errors, error_lock = [], threading.Lock()

        def check():
            self.check()
            if stop.is_set():
                raise RuntimeError("Shot generation stopped after another shot failed.")

        def generate_shot(i):
            check()
            image_prompt, motion_prompt = plan[i - 1]
            stem = f"shot_{i:03d}"
            still = existing(self.dir, stem, STILL_TYPES)
            if still is None:
                check()
                made = self.make_still(image_prompt, aspect, self.dir / (stem + "_image"))
                still = Path(shutil.move(str(made), str(self.dir / (stem + Path(made).suffix.lower()))))
                shutil.rmtree(self.dir / (stem + "_image"), ignore_errors=True)
                self.log(f"🖼 shot {i}/{n}: {image_prompt[:110]}")
            clip = existing(self.dir, stem, CLIP_TYPES) if motion else None
            if motion and clip is None:
                check()
                made = self.make_clip(motion_prompt, still, aspect, resolution, self.dir / (stem + "_video"))
                clip = Path(shutil.move(str(made), str(self.dir / (stem + Path(made).suffix.lower()))))
                shutil.rmtree(self.dir / (stem + "_video"), ignore_errors=True)
                self.log(f"🎥 shot {i}/{n}: {motion_prompt[:110]}")
            return still, clip

        def guarded_generate(i):
            try:
                return generate_shot(i)
            except BaseException as error:
                with error_lock:
                    if not errors:
                        errors.append(error)
                stop.set()
                raise

        # Submit only a bounded window. On failure no further shots are scheduled;
        # in-flight calls finish and save their media for the next run.
        workers = min(n, parallel_shots(parallel))
        self.log(f"Generating up to {workers} shots in parallel.")
        media, pending, next_shot = {}, {}, 1
        with ThreadPoolExecutor(max_workers=workers, thread_name_prefix="openart-shot") as pool:
            try:
                while next_shot <= n or pending:
                    self.check()
                    while next_shot <= n and len(pending) < workers and not stop.is_set():
                        pending[pool.submit(guarded_generate, next_shot)] = next_shot
                        next_shot += 1
                    done, _ = wait(pending, timeout=0.2, return_when=FIRST_COMPLETED)
                    for future in done:
                        i = pending.pop(future)
                        media[i] = future.result()
                    self.progress(min(0.70, 0.05 + 0.65 * len(media) / n),
                                  f"generating shots: {len(media)}/{n} ready, {len(pending)} active")
            except BaseException:
                stop.set()
                for future in pending:
                    future.cancel()
                if errors:
                    raise errors[0]
                raise

        # Encode locally in sequence to avoid saturating the CPU and keep timeline order.
        for i, (start, end) in enumerate(bounds, 1):
            self.check()
            still, clip = media[i]
            seg = seg_dir / f"seg_{i:03d}.mp4"
            self.progress(0.70 + 0.15 * (i - 1) / n, f"shot {i}/{n}: cutting to {end - start:.1f}s")
            cmd = (ffmpeg_clip(clip, seg, end - start, size) if motion
                   else ffmpeg_still(still, seg, end - start, size, zoom_in=i % 2 == 1))
            rc, output = self.run(cmd)
            if rc or not seg.exists():
                raise RuntimeError(f"FFmpeg could not build shot {i}: {output[-800:]}")
            segments.append(seg)
        self.check()
        self.progress(0.88, "joining the shots")
        list_file = seg_dir / "concat.txt"
        list_file.write_text(concat_list(segments), encoding="utf-8")
        silent = self.dir / "video_silent.mp4"
        rc, output = self.run(ffmpeg_concat(list_file, silent))
        if rc or not silent.exists():
            raise RuntimeError(f"FFmpeg could not join the shots: {output[-800:]}")
        self.progress(0.94, "adding the voiceover" + (" and music" if music else ""))
        out_dir = self.project / "out"
        out_dir.mkdir(parents=True, exist_ok=True)
        final = out_dir / ((re.sub(r"[^A-Za-z0-9._-]+", "-", out_name).strip("-") or "video") + ".mp4")
        rc, output = self.run(ffmpeg_mux(silent, voice, final, music))
        if rc or not final.exists():
            raise RuntimeError(f"FFmpeg could not mix the final video: {output[-800:]}")
        self.progress(0.99, "final MP4 written")
        return final
