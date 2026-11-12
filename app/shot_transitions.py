"""Frame-exact transition handles; only two scenes are decoded per dissolve."""


def layout(bounds, fps=24, seconds=0.4):
    frames = [max(1, round(end * fps) - round(start * fps)) for start, end in bounds]
    # Even handle length splits the overlap evenly around the original boundary.
    fade = 2 * min(max(0, round(seconds * fps / 2)), min(frames) // 4) if len(frames) > 1 else 0
    result = []
    for i, count in enumerate(frames):
        head = fade // 2 if i else 0
        tail = fade // 2 if i < len(frames) - 1 else 0
        result.append(dict(frames=count + head + tail, start=fade if head else 0,
                           end=count + head + tail - (fade if tail else 0)))
    return result, fade


def encode_args(out, frames, fps):
    return ["-an", "-frames:v", str(frames), "-r", str(fps), "-c:v", "libx264",
            "-preset", "veryfast", "-crf", "20", "-pix_fmt", "yuv420p", str(out)]


def core_command(source, out, start, end, fps=24):
    return ["ffmpeg", "-y", "-loglevel", "error", "-i", str(source), "-vf",
            f"trim=start_frame={start}:end_frame={end},setpts=PTS-STARTPTS"] + encode_args(out, end - start, fps)


def dissolve_command(left, right, out, left_frames, fade, fps=24):
    filters = (f"[0:v]trim=start_frame={left_frames-fade}:end_frame={left_frames},"
               "settb=AVTB,setpts=PTS-STARTPTS[a];"
               f"[1:v]trim=start_frame=0:end_frame={fade},settb=AVTB,setpts=PTS-STARTPTS[b];"
               f"[a][b]xfade=transition=fade:duration={fade/fps:.9f}:offset=0,format=yuv420p[v]")
    return ["ffmpeg", "-y", "-loglevel", "error", "-filter_complex_threads", "1",
            "-i", str(left), "-i", str(right), "-filter_complex", filters, "-map", "[v]"] + encode_args(out, fade, fps)
