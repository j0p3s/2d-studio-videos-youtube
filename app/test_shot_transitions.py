import hashlib
import json
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import shots_video as sv
from shot_transitions import layout


class TransitionTimingTests(unittest.TestCase):
    def test_handles_preserve_duration_for_one_many_short_and_fractional_scenes(self):
        for duration, seconds in ((.5, 6), (6, 3), (9.17, 3), (480, 12), (600.4, 6), (4000, 6)):
            with self.subTest(duration=duration):
                bounds = sv.slices(duration, seconds)
                scenes, fade = layout(bounds)
                total = sum(s["end"] - s["start"] for s in scenes) + (len(scenes) - 1) * fade
                self.assertEqual(total, round(duration * sv.FPS))
                self.assertTrue(all(s["end"] > s["start"] for s in scenes))
                self.assertEqual(fade % 2, 0)
                self.assertLessEqual(fade / sv.FPS, .5)
                elapsed = 0
                for i, scene in enumerate(scenes[:-1]):
                    elapsed += scene["end"] - scene["start"]
                    self.assertEqual(elapsed + fade // 2, round(bounds[i][1] * sv.FPS))
                    elapsed += fade

    def test_video_duration_prefers_stream_and_rejects_invalid_media(self):
        self.assertEqual(sv.media_duration('{"streams":[{"duration":"2.5"}],"format":{"duration":"3"}}'), 2.5)
        self.assertEqual(sv.media_duration('{"streams":[{"duration":"N/A"}],"format":{"duration":"3"}}'), 3)
        for output in ("broken", "{}", '{"streams":[{"duration":"NaN"}]}',
                       '{"format":{"duration":"0"}}', '{"format":{"duration":"Infinity"}}'):
            with self.subTest(output=output), self.assertRaisesRegex(RuntimeError, "cached clip is kept"):
                sv.media_duration(output)


@unittest.skipUnless(shutil.which("ffmpeg") and shutil.which("ffprobe"), "FFmpeg is required for media validation")
class RealTransitionTests(unittest.TestCase):
    def run_cmd(self, cmd, binary=False):
        result = subprocess.run(cmd, capture_output=True, creationflags=0x08000000 if os.name == "nt" else 0)
        if result.returncode:
            self.fail(result.stderr.decode(errors="replace"))
        return result.stdout if binary else result.stdout.decode()

    def build(self, root, duration, motion):
        voice = root / "voice.wav"
        self.run_cmd(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", "sine=frequency=440:sample_rate=24000",
                      "-t", str(duration), str(voice)])
        generated = []

        def still(prompt, aspect, dest):
            generated.append(prompt)
            Path(dest).mkdir()
            out = Path(dest) / "result.png"
            self.run_cmd(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i",
                          f"color=c={prompt}:s=160x90", "-frames:v", "1", str(out)])
            return out

        def clip(prompt, image, aspect, resolution, dest):
            generated.append("clip")
            Path(dest).mkdir()
            out = Path(dest) / "result.mp4"
            self.run_cmd(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", "testsrc2=s=160x90:r=24",
                          "-t", "1.5", "-an", "-c:v", "libx264", "-pix_fmt", "yuv420p", str(out)])
            return out

        def run(cmd):
            return 0, self.run_cmd(cmd)

        build = sv.ShotsBuild(root, folder="openart", make_still=still, make_clip=clip,
                              ask=lambda _: json.dumps([{"image": c, "motion": "pan"} for c in ("red", "blue", "green")]),
                              run=run, progress=lambda *a: None, check=lambda: None, log=lambda _: None)
        args = dict(voice=voice, duration=duration, narration="story", title="test", aspect="16:9",
                    resolution="1080p", seconds=3, motion=motion, reframe=True)
        with patch("shots_video.frame_size", return_value=(160, 90)):
            final = build.execute(**args)
        return build, args, final, generated

    def probe(self, file):
        return json.loads(self.run_cmd(["ffprobe", "-v", "error", "-show_streams", "-show_format", "-of", "json", str(file)]))

    def test_real_dissolve_has_blended_frames_and_unchanged_duration_and_reuses_images(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            build, args, final, generated = self.build(root, 6, False)
            data = self.probe(final)
            video = next(s for s in data["streams"] if s["codec_type"] == "video")
            audio = next(s for s in data["streams"] if s["codec_type"] == "audio")
            self.assertEqual(int(video["nb_frames"]), 144)
            self.assertAlmostEqual(float(video["duration"]), 6, places=2)
            self.assertLess(abs(float(audio["duration"]) - 6), .1)
            pixel = self.run_cmd(["ffmpeg", "-v", "error", "-ss", "3", "-i", str(final), "-frames:v", "1",
                                  "-vf", "scale=1:1", "-pix_fmt", "rgb24", "-f", "rawvideo", "-"], binary=True)
            self.assertGreater(pixel[0], 30)  # red and blue are both present at the boundary
            self.assertGreater(pixel[2], 30)
            self.assertLess(pixel[1], 30)
            with patch("shots_video.frame_size", return_value=(160, 90)):
                build.execute(**args)
            self.assertEqual(generated, ["red", "blue"])

    def test_real_short_clips_keep_moving_and_fractional_audio_stays_aligned(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _, _, final, generated = self.build(root, 9.17, True)
            data = self.probe(final)
            video = next(s for s in data["streams"] if s["codec_type"] == "video")
            audio = next(s for s in data["streams"] if s["codec_type"] == "audio")
            self.assertEqual(int(video["nb_frames"]), round(9.17 * sv.FPS))
            self.assertLess(abs(float(video["duration"]) - float(audio["duration"])), .1)
            raw = root / "openart/segments/seg_001.mp4"
            stream = self.run_cmd(["ffmpeg", "-v", "error", "-ss", "2", "-i", str(raw), "-t", "1",
                                   "-pix_fmt", "rgb24", "-f", "rawvideo", "-"], binary=True)
            size = 160 * 90 * 3
            hashes = {hashlib.md5(stream[i:i + size]).digest() for i in range(0, len(stream), size)}
            self.assertGreater(len(hashes), 5, "the end of a short source must keep moving rather than freeze")
            self.assertEqual(generated.count("clip"), 4)


if __name__ == "__main__":
    unittest.main()
