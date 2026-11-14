import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from PIL import Image, ImageDraw

import thumb_pick


def dark_title():
    img = Image.new("RGB", (216, 384), (18, 40, 38))
    ImageDraw.Draw(img).rectangle((70, 180, 150, 200), fill=(255, 220, 40))
    return img


def lit_character():
    img = Image.new("RGB", (216, 384), (60, 70, 30))
    d = ImageDraw.Draw(img)
    d.rectangle((40, 40, 176, 200), fill=(190, 230, 40))
    d.rectangle((95, 150, 125, 330), fill=(240, 100, 30))
    d.ellipse((90, 110, 130, 150), fill=(20, 30, 30))
    return img


class FrameScoreTest(unittest.TestCase):
    def test_black_frame_scores_zero(self):
        self.assertEqual(thumb_pick.frame_score(Image.new("RGB", (216, 384), (2, 2, 2))), 0.0)

    def test_character_in_light_beats_dark_title_card(self):
        self.assertGreater(thumb_pick.frame_score(lit_character()), thumb_pick.frame_score(dark_title()) + 0.2)

    def test_flat_frame_scores_low(self):
        self.assertLess(thumb_pick.frame_score(Image.new("RGB", (216, 384), (90, 90, 90))), 0.2)


@unittest.skipUnless(shutil.which("ffmpeg"), "ffmpeg not installed")
class BestTimeTest(unittest.TestCase):
    def test_picks_the_vivid_second_half(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            for name, img in (("a", dark_title()), ("b", lit_character())):
                img.save(tmp / f"{name}.png")
            video = tmp / "v.mp4"
            subprocess.run(["ffmpeg", "-y", "-v", "error", "-loop", "1", "-t", "5", "-i", str(tmp / "a.png"),
                            "-loop", "1", "-t", "5", "-i", str(tmp / "b.png"),
                            "-filter_complex", "[0][1]concat=n=2:v=1[v]", "-map", "[v]", "-pix_fmt", "yuv420p",
                            "-r", "10", str(video)], check=True)
            self.assertGreater(thumb_pick.best_time(video, 10.0), 5.0)

    def test_unreadable_video_raises(self):
        with self.assertRaises(RuntimeError):
            thumb_pick.best_time(Path("missing.mp4"), 10.0)


if __name__ == "__main__":
    unittest.main()
