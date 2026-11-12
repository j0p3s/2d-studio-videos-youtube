import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from openart_defaults import migrate_defaults, build_options, RETENTION_BRIEF, DEFAULT_RESOLUTION
from shots_video import plan_key, slices, ffmpeg_still, ShotsBuild
from studio_gui import Studio, scriptforge_prompt


class EconomyDefaultsTests(unittest.TestCase):
    def test_defaults_apply_to_existing_settings_and_can_be_disabled(self):
        settings = {"openart_motion": True, "openart_clip_seconds": 6, "current": {"video": "paid.mp4"}}
        migrate_defaults(settings)
        self.assertTrue(settings["openart_save_credits"])
        self.assertEqual(settings["current"]["video"], "paid.mp4")
        long = build_options(settings)
        self.assertEqual((long["seconds"], long["motion"], long["parallel"]), (12, False, 3))
        self.assertEqual(build_options(settings, shorts=True)["seconds"], 6)
        settings["openart_save_credits"] = False
        migrate_defaults(settings)
        custom = build_options(settings)
        self.assertEqual((custom["seconds"], custom["motion"]), (6, True))

    def test_existing_paid_plan_resumes_and_invalid_or_unrelated_plans_do_not(self):
        saved = dict(key=plan_key("voice.mp3", 60, 6.0, "16:9", True), seconds=6.0, motion=True,
                     shots=[["image", "motion"] for _ in range(10)])
        common = dict(voice="voice.mp3", duration=60, aspect="16:9")
        options = build_options({}, saved=saved, **common)
        self.assertEqual((options["seconds"], options["motion"], options["resuming"]), (6, True, True))
        for bad in (None, [], {}, dict(saved, key="different"), dict(saved, shots=[None] * 10),
                    dict(saved, shots=[]), dict(saved, seconds="bad")):
            with self.subTest(saved=bad):
                self.assertFalse(build_options({}, saved=bad, **common)["resuming"])
        self.assertFalse(build_options({}, saved=saved, **dict(common, aspect="9:16"))["resuming"])
        self.assertFalse(build_options({"openart_save_credits": False}, saved=saved, **common)["resuming"])

    def test_eight_minute_build_generates_40_stills_and_no_paid_clips(self):
        images, commands = [], []
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            voice = root / "voice.mp3"
            voice.write_bytes(b"voice")

            def still(prompt, aspect, dest):
                images.append(prompt)
                Path(dest).mkdir()
                out = Path(dest) / "result.png"
                out.write_bytes(b"png")
                return out

            def run(cmd):
                commands.append(cmd)
                Path(cmd[-1]).write_bytes(b"video")
                return 0, ""

            options = build_options({})
            build = ShotsBuild(root, folder="openart", make_still=still,
                               make_clip=Mock(side_effect=AssertionError("paid video request")),
                               ask=lambda _: json.dumps([{"image": "scene", "motion": "pan"}] * 40),
                               run=run, progress=lambda *a: None, check=lambda: None, log=lambda _: None)
            args = dict(voice=voice, duration=480, narration="story", title="test", aspect="16:9",
                        resolution=DEFAULT_RESOLUTION, seconds=options["seconds"], motion=options["motion"],
                        parallel=options["parallel"], reframe=options["economy"])
            build.execute(**args)
            self.assertEqual(len(images), 40)
            self.assertIn("1280x720", commands[0][commands[0].index("-vf") + 1])
            self.assertIn("sin(2*PI", commands[0][commands[0].index("-vf") + 1])
            self.assertNotIn("floor(", commands[0][commands[0].index("-vf") + 1])
            build.execute(**args)
            self.assertEqual(len(images), 40)
            build.make_clip.assert_not_called()

    def test_auto_and_manual_use_same_openart_defaults(self):
        for auto in (False, True):
            with self.subTest(auto=auto), tempfile.TemporaryDirectory() as tmp:
                project = Path(tmp)
                app = SimpleNamespace(
                    settings={}, s={"voice": "voice.mp3", "script_file": "script.txt", "narration": "Story",
                                    "slug": "test", "title": "Title", "shorts": False},
                    _auto=auto, _video_prompt=Mock(), _openart_ready=Mock(), _voice_duration=lambda: 480,
                    _workdir=lambda: project, _openart_models=lambda: ("image-model", "video-model"),
                    opt_aspect=Mock(get=lambda: "16:9"), opt_res=Mock(), opt_music=Mock(get=lambda: "None"),
                    chk_capt=Mock(get=lambda: False), music_file=None, anim_log=Mock(), ent_look=Mock(),
                    log=Mock(), ask_ai=Mock(), prog=Mock(), check_cancel=Mock(), _openart_run=Mock(),
                    _video_done=Mock())
                app.opt_res.get.return_value = "720p"
                app.ent_look.get.return_value = "cinematic"
                app.run_job = lambda label, work, done: work()
                with patch("studio_gui.messagebox.askyesno", return_value=True), \
                        patch("studio_gui.openart_provider.account"), \
                        patch("studio_gui.shots_video.ShotsBuild") as build:
                    Studio._make_video_openart(app)
                args = build.return_value.execute.call_args.kwargs
                self.assertEqual((args["motion"], args["seconds"], args["parallel"], args["resolution"]),
                                 (False, 12, 3, "720p"))
                self.assertTrue(args["reframe"])
                app.opt_res.set.assert_called_once_with("720p")

    def test_retention_brief_is_added_to_script_and_visual_direction(self):
        self.assertIn(RETENTION_BRIEF, scriptforge_prompt())
        from shots_video import plan_prompt
        prompt = plan_prompt("Title", slices(12, 6), ["one", "two"], "", "16:9")
        self.assertIn("central conflict or question", prompt)
        self.assertIn("safe margins", prompt)
        command = ffmpeg_still("x.png", "out.mp4", 12, (1920, 1080), reframe=True)
        self.assertEqual(command[command.index("-frames:v") + 1], "288")


if __name__ == "__main__":
    unittest.main()
