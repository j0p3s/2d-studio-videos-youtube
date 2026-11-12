import io
import json
import os
import tempfile
import unittest
import zipfile
from pathlib import Path

import openart_provider as oa
import shots_video as sv
from ai_providers import OPENART, PROVIDERS, TEXT_PROVIDERS, cli_command, run_agent


class FakeCLI:
    """Stands in for the openart binary: records every command and writes the file -o asks for."""
    def __init__(self):
        self.calls, self.fail_flags, self.logged_in, self.credits = [], set(), True, True

    def __call__(self, cmd):
        self.calls.append(cmd)
        args = cmd[1:]
        if not self.logged_in:
            return 1, "error: not logged in. Run `openart login` first."
        if args[:2] == ["account", "--json"]:
            return 0, 'Checking…\n{"email": "me@example.com", "plan": "pro", "credits": 1234}\n'
        if args[:3] == ["model", "list", "--json"]:
            return 0, '{"items": [{"id": "nano-banana-2"}, {"id": "kling-3-omni"}]}'
        if args[0] == "generate":
            for flag in self.fail_flags:
                if flag in args:
                    return 2, f'Error: unknown flag: {flag}\nUsage: openart generate {args[1]} [flags]'
            if not self.credits:
                return 1, "error: insufficient credits for this generation"
            out = Path(args[args.index("-o") + 1])
            out.mkdir(parents=True, exist_ok=True)
            name = "result.png" if args[1] == "image" else "result.mp4"
            (out / name).write_bytes(b"media")
            return 0, json.dumps({"id": "gen-1", "status": "completed",
                                  "outputs": [{"url": f"https://cdn.openart.ai/{name}"}]})
        return 1, "unknown command"


class ProviderTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.tools = Path(self.tmp.name) / ".tools"
        self.tools.mkdir()
        self.exe = self.tools / ("openart.exe" if os.name == "nt" else "openart")
        self.exe.write_text("#!/bin/sh\n")
        self.exe.chmod(0o755)
        self.env = {"PATH": str(self.tools), "LOCALAPPDATA": str(Path(self.tmp.name) / "local")}
        self.exe = Path(oa.executable(self.env))  # Windows PATHEXT may uppercase .EXE
        self.cli = FakeCLI()

    def tearDown(self):
        self.tmp.cleanup()

    def test_binary_is_found_in_tools_or_the_official_folder_and_missing_is_explained(self):
        self.assertEqual(oa.executable(self.env), str(self.exe))
        self.exe.unlink()
        self.assertIsNone(oa.executable(self.env))
        official = Path(self.env["LOCALAPPDATA"]) / "Programs" / "openart" / "bin" / "openart.exe"
        official.parent.mkdir(parents=True)
        official.write_bytes(b"")
        self.assertEqual(oa.executable(self.env), str(official))
        with self.assertRaisesRegex(RuntimeError, "Setup → Install OpenArt"):
            oa.command({"PATH": ""}, "login")

    def test_image_and_video_commands_match_the_cli_reference(self):
        out = Path(self.tmp.name) / "shot"
        still = oa.generate(self.cli, self.env, "image", "a red fox", out, model="", aspect="9:16")
        self.assertEqual(still, out / "result.png")
        self.assertEqual(self.cli.calls[-1], [str(self.exe), "generate", "image", "a red fox", "--model",
                                              oa.DEFAULT_IMAGE_MODEL, "--json", "-o", str(out),
                                              "--aspect-ratio", "9:16", "--timeout", oa.IMAGE_TIMEOUT])
        clip = oa.generate(self.cli, self.env, "video", "slow push-in", out / "v", model="pixverseV6", image=still,
                           aspect="16:9", resolution="1080p")
        self.assertEqual(clip.name, "result.mp4")
        self.assertEqual(self.cli.calls[-1][1:], ["generate", "video", "slow push-in", "--model", "pixverseV6", "--json",
                                                  "-o", str(out / "v"), "--image", str(still), "--aspect-ratio", "16:9",
                                                  "--resolution", "1080p", "--timeout", oa.VIDEO_TIMEOUT])

    def test_a_flag_the_cli_rejects_is_dropped_and_the_call_retried(self):
        self.cli.fail_flags = {"--aspect-ratio", "--timeout"}
        oa.generate(self.cli, self.env, "image", "x", Path(self.tmp.name) / "a", model="m", aspect="16:9")
        self.assertEqual(len(self.cli.calls), 3)
        self.assertNotIn("--aspect-ratio", self.cli.calls[-1])
        self.assertNotIn("--timeout", self.cli.calls[-1])
        self.cli.fail_flags = {"--model"}   # a real error is not retried
        with self.assertRaisesRegex(RuntimeError, "OpenArt CLI failed .*generate image, model m"):
            oa.generate(self.cli, self.env, "image", "x", Path(self.tmp.name) / "b", model="m")

    def test_kling_omni_pixel_resolutions_use_quality_tiers(self):
        for resolution, tier in (("720p", "std"), ("1080p", "pro"), ("2160p", "4k"),
                                 ("std", "std"), ("pro", "pro"), ("4k", "4k")):
            with self.subTest(resolution=resolution):
                oa.generate(self.cli, self.env, "video", "x", Path(self.tmp.name) / resolution,
                            model="kling-3-omni", resolution=resolution)
                cmd = self.cli.calls[-1]
                self.assertEqual(cmd[cmd.index("--resolution") + 1], tier)

    def test_model_validation_error_retries_only_the_rejected_optional_field(self):
        def run(cmd):
            if "--resolution" in cmd:
                self.cli.calls.append(cmd)
                return 1, 'error: resolution: Invalid option: expected one of "std"|"pro"|"4k"'
            return self.cli(cmd)

        oa.generate(run, self.env, "video", "x", Path(self.tmp.name) / "retry",
                    model="another-model", resolution="1080p", aspect="16:9")
        self.assertEqual(len(self.cli.calls), 2)
        self.assertIn("1080p", self.cli.calls[0])
        self.assertNotIn("--resolution", self.cli.calls[-1])
        self.assertIn("--aspect-ratio", self.cli.calls[-1])
        self.assertFalse(oa._rejected_flag('error: prompt: Invalid option', "--resolution"))

    def test_sign_in_and_credit_problems_are_explained(self):
        self.assertEqual(oa.account(self.cli, self.env)["credits"], 1234)
        self.assertEqual([m["id"] for m in oa.models(self.cli, self.env)], ["nano-banana-2", "kling-3-omni"])
        self.cli.credits = False
        with self.assertRaisesRegex(RuntimeError, "no credits left.*finished shots are kept"):
            oa.generate(self.cli, self.env, "image", "x", Path(self.tmp.name) / "c", model="m")
        self.cli.logged_in = False
        with self.assertRaisesRegex(RuntimeError, "not signed in.*Sign in: OpenArt"):
            oa.account(self.cli, self.env)

    def test_json_and_result_urls_are_read_around_progress_lines(self):
        self.assertEqual(oa.json_output("working…\n{\"a\": [1]}\ndone"), {"a": [1]})
        self.assertEqual(oa.result_url('{"data": {"outputs": [{"url": "https://cdn.openart.ai/x.mp4"}]}}'),
                         "https://cdn.openart.ai/x.mp4")
        self.assertEqual(oa.result_url("Result: https://cdn.openart.ai/y.png (12 credits)"), "https://cdn.openart.ai/y.png")
        self.assertIsNone(oa.result_url("nothing here"))

    def test_installer_picks_the_right_release_asset_and_extracts_the_binary(self):
        self.assertTrue(oa.release_asset_name("Windows", "AMD64").match("openart_0.3.0_windows_amd64.zip"))
        self.assertTrue(oa.release_asset_name("Darwin", "arm64").match("openart_0.3.0_darwin_arm64.tar.gz"))
        self.assertFalse(oa.release_asset_name("Linux", "x86_64").match("openart_0.3.0_linux_arm64.tar.gz"))
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as z:
            z.writestr("openart_0.3.0_windows_amd64/openart.exe", b"MZ-binary")
        release = {"tag_name": "v0.3.0", "assets": [
            {"name": "checksums.txt", "browser_download_url": "https://x/c"},
            {"name": "openart_0.3.0_windows_amd64.zip", "browser_download_url": "https://x/win.zip"}]}

        def fetch(url):
            return json.dumps(release).encode() if url == oa.RELEASES_API else buf.getvalue()
        logs = []
        target = oa.install(self.tools, logs.append, system="Windows", machine="AMD64", fetch=fetch)
        self.assertEqual((target.name, target.read_bytes()), ("openart.exe", b"MZ-binary"))
        self.assertFalse((self.tools / "openart_0.3.0_windows_amd64.zip").exists())
        self.assertIn("v0.3.0", logs[0])
        with self.assertRaisesRegex(RuntimeError, "no build for this computer"):
            oa.install(self.tools, logs.append, system="Linux", machine="x86_64", fetch=fetch)

    def test_openart_is_an_animation_only_provider(self):
        self.assertIn(OPENART, PROVIDERS)
        self.assertNotIn(OPENART, TEXT_PROVIDERS)
        with self.assertRaisesRegex(RuntimeError, "not text"):
            run_agent(OPENART, "write a script", None, cwd=".", env=self.env)
        with self.assertRaisesRegex(RuntimeError, "started by the studio"):
            run_agent(OPENART, "animate", None, cwd=".", env=self.env, animation=True)
        with self.assertRaisesRegex(RuntimeError, "no command-line agent"):
            cli_command(OPENART, self.env)


class VideoBuildTests(unittest.TestCase):
    def test_slices_cover_the_voiceover_and_clip_seconds_are_bounded(self):
        self.assertEqual(sv.slices(10, 6), [(0, 5.0), (5.0, 10.0)])
        self.assertEqual(sv.slices(5, 6), [(0, 5.0)])
        bounds = sv.slices(600.4, 6)
        self.assertEqual(len(bounds), 101)
        self.assertEqual((bounds[0][0], bounds[-1][1]), (0, 600.4))
        self.assertEqual([sv.clip_seconds(v) for v in ("", "abc", "1", "7.5", "99", None)], [6, 6, 3, 7.5, 20, 6])
        self.assertEqual(sv.frame_size("16:9", "1080p"), (1920, 1080))
        self.assertEqual(sv.frame_size("9:16", "720p"), (720, 1280))

    def test_narration_is_spread_over_the_shots(self):
        lines = sv.narration_for("one two three four five six", sv.slices(6, 3), 6)
        self.assertEqual(lines, ["one two three", "four five six"])
        prompt = sv.plan_prompt("My video", sv.slices(6, 3), lines, "warm colours", "16:9")
        self.assertIn('1. [0.0s-3.0s] "one two three"', prompt)
        self.assertIn("warm colours", prompt)

    def test_plan_parsing_fills_gaps_and_rejects_junk(self):
        shots = sv.parse_plan('Here you go:\n[{"n": 2, "image": "B", "motion": "pan"}, {"n": 1, "image": "A"}]\nthanks', 3)
        self.assertEqual(shots, [("A", "slow push-in"), ("B", "pan"), ("B", "pan")])
        self.assertEqual(sv.parse_plan('[{"image": "X", "motion": "orbit"}]', 2), [("X", "orbit"), ("X", "orbit")])
        with self.assertRaisesRegex(RuntimeError, "did not return a JSON shot list"):
            sv.parse_plan("no json here", 2)
        with self.assertRaisesRegex(RuntimeError, "no usable shot prompts"):
            sv.parse_plan('[{"n": 1}]', 1)

    def test_ffmpeg_commands_cut_every_shot_to_its_length(self):
        clip = sv.ffmpeg_clip("c.mp4", "s.mp4", 5.5, (1920, 1080))
        self.assertIn("tpad=stop_mode=clone:stop_duration=5.500", clip[clip.index("-vf") + 1])
        self.assertEqual(clip[clip.index("-t") + 1], "5.500")
        still = sv.ffmpeg_still("a.jpg", "s.mp4", 2, (1080, 1920))
        self.assertEqual(still[still.index("-frames:v") + 1], "48")
        self.assertIn("zoompan=z='min(1+0.0010*on,1.25)'", still[still.index("-vf") + 1])
        mux = sv.ffmpeg_mux("v.mp4", "voice.mp3", "out.mp4", music="song.mp3")
        self.assertIn("amix=inputs=2:duration=first", mux[mux.index("-filter_complex") + 1])
        self.assertNotIn("-filter_complex", sv.ffmpeg_mux("v.mp4", "voice.mp3", "out.mp4"))
        self.assertEqual(sv.concat_list([r"C:\x\it's.mp4"]), "file 'C:/x/it'\\''s.mp4'\n")

    def test_build_reuses_finished_shots_and_replans_on_new_settings(self):
        calls = {"ask": 0, "image": [], "video": [], "run": []}

        def make_still(prompt, aspect, dest):
            calls["image"].append((prompt, aspect))
            Path(dest).mkdir(parents=True, exist_ok=True)
            f = Path(dest) / "result.png"
            f.write_bytes(b"png")
            return f

        def make_clip(prompt, still, aspect, resolution, dest):
            calls["video"].append((prompt, Path(still).name, resolution))
            Path(dest).mkdir(parents=True, exist_ok=True)
            f = Path(dest) / "result.mp4"
            f.write_bytes(b"mp4")
            return f

        def ask(prompt):
            calls["ask"] += 1
            return '[{"n":1,"image":"img one","motion":"pan"},{"n":2,"image":"img two","motion":"orbit"}]'

        def run(cmd):
            calls["run"].append(cmd)
            Path(cmd[-1]).write_bytes(b"mp4")
            return 0, ""
        with tempfile.TemporaryDirectory() as tmp:
            voice = Path(tmp) / "voice.mp3"
            voice.write_bytes(b"mp3")
            build = sv.ShotsBuild(Path(tmp) / "proj", folder="openart", make_still=make_still, make_clip=make_clip,
                                  ask=ask, run=run, progress=lambda f, t: None, check=lambda: None, log=lambda t: None)
            common = dict(voice=voice, duration=10, narration="hello there everyone", title="My Video: Part 1",
                          aspect="16:9", resolution="720p", seconds=6, motion=True, music="song.mp3")
            final = build.execute(**common)
            self.assertEqual(final.name, "My-Video-Part-1.mp4")
            self.assertEqual(calls["image"], [("img one", "16:9"), ("img two", "16:9")])
            self.assertEqual(calls["video"], [("pan", "shot_001.png", "720p"), ("orbit", "shot_002.png", "720p")])
            self.assertEqual(sorted(p.name for p in (Path(tmp) / "proj" / "openart").iterdir()),
                             ["plan.json", "segments", "shot_001.mp4", "shot_001.png", "shot_002.mp4", "shot_002.png",
                              "video_silent.mp4"])
            self.assertEqual([c[0] for c in calls["run"]], ["ffmpeg"] * 4)   # 2 cuts, concat, mux
            self.assertIn("-stream_loop", calls["run"][-1])
            # Same voiceover again (after a stop or an empty balance): nothing is generated twice.
            build.execute(**common)
            self.assertEqual((calls["ask"], len(calls["image"]), len(calls["video"])), (1, 2, 2))
            # A different shot length is a new plan.
            build.execute(**dict(common, seconds=3, motion=False))
            self.assertEqual((calls["ask"], len(calls["image"]), len(calls["video"])), (2, 6, 2))
            self.assertIn("zoompan", " ".join(calls["run"][-3]))   # last cut before concat and mux


if __name__ == "__main__":
    unittest.main()
