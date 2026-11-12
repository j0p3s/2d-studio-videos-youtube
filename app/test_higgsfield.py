import json
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import higgsfield_provider as hf
import higgsfield_video as hv
from ai_providers import HIGGSFIELD, PROVIDERS, TEXT_PROVIDERS, cli_command, run_agent


class FakeHiggsfield(BaseHTTPRequestHandler):
    """The API as the official SDKs use it: POST an endpoint, poll /requests/<id>/status."""
    seen = []
    polls = {}
    flaky_left = 0
    outcome = "completed"

    def log_message(self, *args):
        pass

    def _send(self, body, status=200, raw=None):
        data = raw if raw is not None else json.dumps(body).encode()
        self.send_response(status)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _base(self):
        return f"http://127.0.0.1:{self.server.server_port}"

    def do_POST(self):
        length = int(self.headers.get("Content-Length") or 0)
        payload = json.loads(self.rfile.read(length)) if length else {}
        FakeHiggsfield.seen.append((self.path, dict(self.headers), payload))
        if self.headers.get("Authorization") != "Key id-1:secret-1" and not self.path.startswith("/upload/"):
            return self._send({"detail": "Invalid API key"}, 401)
        if FakeHiggsfield.flaky_left:
            FakeHiggsfield.flaky_left -= 1
            return self._send({"detail": "busy"}, 503)
        if self.path == "/files/generate-upload-url":
            return self._send({"public_url": self._base() + "/cdn/ref.jpg", "upload_url": self._base() + "/upload/ref.jpg"})
        if self.path.startswith("/requests/") and self.path.endswith("/cancel"):
            return self._send({})
        if self.path in (hf.TEXT_TO_IMAGE, hf.IMAGE_TO_VIDEO):
            if payload.get("prompt") == "broke":
                return self._send({"detail": "Insufficient credits"}, 402)
            rid = f"req-{len(self.seen)}"
            FakeHiggsfield.polls[rid] = {"kind": "image" if self.path == hf.TEXT_TO_IMAGE else "video", "n": 0}
            return self._send({"request_id": rid, "status_url": f"{self._base()}/requests/{rid}/status",
                               "cancel_url": f"{self._base()}/requests/{rid}/cancel"})
        self._send({"detail": "no such endpoint"}, 404)

    def do_PUT(self):
        length = int(self.headers.get("Content-Length") or 0)
        FakeHiggsfield.seen.append((self.path, dict(self.headers), self.rfile.read(length)))
        self._send({})

    def do_GET(self):
        if self.headers.get("Authorization") != "Key id-1:secret-1" and not self.path.startswith("/cdn/"):
            return self._send({"detail": "Invalid API key"}, 401)
        if self.path == hf.MOTIONS:
            return self._send([{"id": "m1", "name": "Zoom In"}, {"id": "m2", "name": "Orbit"}])
        if self.path.startswith("/cdn/"):
            return self._send(None, raw=b"MEDIA-BYTES")
        if self.path.startswith("/requests/"):
            rid = self.path.split("/")[2]
            job = FakeHiggsfield.polls[rid]
            job["n"] += 1
            if job["n"] == 1:
                return self._send({"status": "queued", "request_id": rid})
            if job["n"] == 2:
                return self._send({"status": "in_progress", "request_id": rid})
            body = {"status": FakeHiggsfield.outcome, "request_id": rid}
            if FakeHiggsfield.outcome == "completed":
                body["images" if job["kind"] == "image" else "video"] = (
                    [{"url": self._base() + "/cdn/still.jpg"}] if job["kind"] == "image"
                    else {"url": self._base() + "/cdn/clip.mp4"})
            elif FakeHiggsfield.outcome == "failed":
                body["error"] = "model crashed"
            return self._send(body)
        self._send({"detail": "no such endpoint"}, 404)


class ProviderTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), FakeHiggsfield)
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()
        cls.env = {"HIGGSFIELD_API_KEY": "id-1:secret-1",
                   "HIGGSFIELD_BASE_URL": f"http://127.0.0.1:{cls.server.server_port}"}
        hf.POLL_SECONDS, hf.RETRY_DELAY = 0.01, 0.0

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()

    def setUp(self):
        FakeHiggsfield.seen.clear()
        FakeHiggsfield.polls.clear()
        FakeHiggsfield.flaky_left, FakeHiggsfield.outcome = 0, "completed"

    def test_credentials_come_from_the_env_file_or_the_sdk_variables(self):
        self.assertEqual(hf.credentials({"HIGGSFIELD_API_KEY": " a:b "}), "a:b")
        self.assertEqual(hf.credentials({"HF_KEY": "c:d"}), "c:d")
        self.assertEqual(hf.credentials({"HF_API_KEY": "e", "HF_API_SECRET": "f"}), "e:f")
        with self.assertRaisesRegex(RuntimeError, "HIGGSFIELD_API_KEY=key-id:key-secret"):
            hf.credentials({})
        with self.assertRaisesRegex(RuntimeError, "joined with a colon"):
            hf.credentials({"HIGGSFIELD_API_KEY": "no-colon"})
        self.assertFalse(hf.configured({}))
        self.assertTrue(hf.configured(self.env))

    def test_still_is_requested_polled_and_downloaded(self):
        statuses = []
        url = hf.text_to_image("a lake", "9:16", self.env, on_status=statuses.append)
        self.assertTrue(url.endswith("/cdn/still.jpg"))
        self.assertEqual(statuses, ["queued", "in_progress", "completed"])
        path, headers, payload = FakeHiggsfield.seen[0]
        self.assertEqual(path, hf.TEXT_TO_IMAGE)
        self.assertEqual(headers["Authorization"], "Key id-1:secret-1")
        self.assertEqual(payload, {"prompt": "a lake", "width_and_height": "1152x2048", "quality": "1080p",
                                   "batch_size": 1, "enhance_prompt": True})
        with tempfile.TemporaryDirectory() as tmp:
            saved = hf.download(url, Path(tmp) / "nested" / "still.jpg")
            self.assertEqual(saved.read_bytes(), b"MEDIA-BYTES")
            self.assertEqual([p.name for p in saved.parent.iterdir()], ["still.jpg"])   # no .part left behind

    def test_clip_uses_the_dop_model_with_the_uploaded_still(self):
        with tempfile.TemporaryDirectory() as tmp:
            still = Path(tmp) / "shot.jpg"
            still.write_bytes(b"JPEGDATA")
            public = hf.upload_file(still, self.env)
        self.assertTrue(public.endswith("/cdn/ref.jpg"))
        put = [s for s in FakeHiggsfield.seen if s[0] == "/upload/ref.jpg"][0]
        self.assertEqual((put[1]["Content-Type"], put[2]), ("image/jpeg", b"JPEGDATA"))
        url = hf.image_to_video(public, "slow push-in", self.env, model="")
        self.assertTrue(url.endswith("/cdn/clip.mp4"))
        payload = FakeHiggsfield.seen[-1][2]
        self.assertEqual(payload["model"], "dop-turbo")
        self.assertEqual(payload["input_images"], [{"type": "image_url", "image_url": public}])
        with self.assertRaisesRegex(RuntimeError, "Unknown Higgsfield video model 'kling'"):
            hf.image_to_video(public, "pan", self.env, model="kling")

    def test_server_hiccups_are_retried_and_real_errors_explained(self):
        FakeHiggsfield.flaky_left = 1
        self.assertTrue(hf.text_to_image("a lake", "16:9", self.env).endswith("/cdn/still.jpg"))
        self.assertEqual([s[0] for s in FakeHiggsfield.seen], [hf.TEXT_TO_IMAGE, hf.TEXT_TO_IMAGE])
        with self.assertRaisesRegex(RuntimeError, r"rejected the API key \(401\): Invalid API key"):
            hf.text_to_image("a lake", "16:9", dict(self.env, HIGGSFIELD_API_KEY="id-1:wrong"))
        with self.assertRaisesRegex(RuntimeError, "no credits left.*finished clips are kept"):
            hf.text_to_image("broke", "16:9", self.env)
        FakeHiggsfield.outcome = "nsfw"
        with self.assertRaisesRegex(RuntimeError, "NSFW"):
            hf.text_to_image("a lake", "16:9", self.env)
        FakeHiggsfield.outcome = "failed"
        with self.assertRaisesRegex(RuntimeError, "generation failed: model crashed"):
            hf.text_to_image("a lake", "16:9", self.env)
        self.assertEqual([m["name"] for m in hf.motions(self.env)], ["Zoom In", "Orbit"])

    def test_stop_cancels_the_queued_request(self):
        def stop():
            raise RuntimeError("Stopped.")
        with self.assertRaisesRegex(RuntimeError, "Stopped"):
            hf.generate(hf.TEXT_TO_IMAGE, {"prompt": "x"}, self.env, check=stop)
        self.assertTrue(FakeHiggsfield.seen[-1][0].endswith("/cancel"))

    def test_higgsfield_is_an_animation_only_provider(self):
        self.assertIn(HIGGSFIELD, PROVIDERS)
        self.assertNotIn(HIGGSFIELD, TEXT_PROVIDERS)
        with self.assertRaisesRegex(RuntimeError, "not text"):
            run_agent(HIGGSFIELD, "write a script", None, cwd=".", env=self.env)
        with self.assertRaisesRegex(RuntimeError, "started by the studio"):
            run_agent(HIGGSFIELD, "animate", None, cwd=".", env=self.env, animation=True, skill_dir=__file__.rsplit("/", 1)[0])
        with self.assertRaisesRegex(RuntimeError, "no command-line agent"):
            cli_command(HIGGSFIELD, self.env)


class VideoBuildTests(unittest.TestCase):
    def test_slices_cover_the_voiceover_and_clip_seconds_are_bounded(self):
        self.assertEqual(hv.slices(10, 6), [(0, 5.0), (5.0, 10.0)])
        self.assertEqual(hv.slices(5, 6), [(0, 5.0)])
        bounds = hv.slices(600.4, 6)
        self.assertEqual(len(bounds), 101)
        self.assertEqual((bounds[0][0], bounds[-1][1]), (0, 600.4))
        self.assertEqual([hv.clip_seconds(v) for v in ("", "abc", "1", "7.5", "99", None)], [6, 6, 3, 7.5, 20, 6])
        self.assertEqual(hv.frame_size("16:9", "1080p"), (1920, 1080))
        self.assertEqual(hv.frame_size("9:16", "720p"), (720, 1280))

    def test_narration_is_spread_over_the_shots(self):
        lines = hv.narration_for("one two three four five six", hv.slices(6, 3), 6)
        self.assertEqual(lines, ["one two three", "four five six"])
        prompt = hv.plan_prompt("My video", hv.slices(6, 3), lines, "warm colours", "16:9")
        self.assertIn('1. [0.0s-3.0s] "one two three"', prompt)
        self.assertIn("warm colours", prompt)

    def test_plan_parsing_fills_gaps_and_rejects_junk(self):
        shots = hv.parse_plan('Here you go:\n[{"n": 2, "image": "B", "motion": "pan"}, {"n": 1, "image": "A"}]\nthanks', 3)
        self.assertEqual(shots, [("A", "slow push-in"), ("B", "pan"), ("B", "pan")])
        self.assertEqual(hv.parse_plan('[{"image": "X", "motion": "orbit"}]', 2), [("X", "orbit"), ("X", "orbit")])
        with self.assertRaisesRegex(RuntimeError, "did not return a JSON shot list"):
            hv.parse_plan("no json here", 2)
        with self.assertRaisesRegex(RuntimeError, "no usable shot prompts"):
            hv.parse_plan('[{"n": 1}]', 1)

    def test_ffmpeg_commands_cut_every_shot_to_its_length(self):
        clip = hv.ffmpeg_clip("c.mp4", "s.mp4", 5.5, (1920, 1080))
        self.assertIn("tpad=stop_mode=clone:stop_duration=5.500", clip[clip.index("-vf") + 1])
        self.assertEqual(clip[clip.index("-t") + 1], "5.500")
        still = hv.ffmpeg_still("a.jpg", "s.mp4", 2, (1080, 1920))
        self.assertEqual(still[still.index("-frames:v") + 1], "48")
        self.assertIn("zoompan=z='min(1+0.0010*on,1.25)'", still[still.index("-vf") + 1])
        mux = hv.ffmpeg_mux("v.mp4", "voice.mp3", "out.mp4", music="song.mp3")
        self.assertIn("amix=inputs=2:duration=first", mux[mux.index("-filter_complex") + 1])
        self.assertNotIn("-filter_complex", hv.ffmpeg_mux("v.mp4", "voice.mp3", "out.mp4"))
        self.assertEqual(hv.concat_list([r"C:\x\it's.mp4"]), "file 'C:/x/it'\\''s.mp4'\n")

    def test_build_reuses_finished_shots_and_stops_cleanly(self):
        calls = {"ask": 0, "image": [], "video": [], "run": []}
        original = hf.text_to_image, hf.image_to_video, hf.upload_file, hf.download
        hf.text_to_image = lambda prompt, aspect, env, **kw: calls["image"].append(prompt) or "http://x/" + prompt
        hf.image_to_video = lambda url, prompt, env, **kw: calls["video"].append(prompt) or "http://x/clip"
        hf.upload_file = lambda path, env: "http://x/up"
        hf.download = lambda url, dest, env=None: Path(dest).write_bytes(b"x") or Path(dest)

        def ask(prompt):
            calls["ask"] += 1
            return '[{"n":1,"image":"img one","motion":"pan"},{"n":2,"image":"img two","motion":"orbit"}]'

        def run(cmd):
            calls["run"].append(cmd)
            Path(cmd[-1]).write_bytes(b"mp4")
            return 0, ""
        try:
            with tempfile.TemporaryDirectory() as tmp:
                voice = Path(tmp) / "voice.mp3"
                voice.write_bytes(b"mp3")
                build = hv.HiggsfieldBuild(Path(tmp) / "proj", {}, ask=ask, run=run, progress=lambda f, t: None,
                                           check=lambda: None, log=lambda t: None)
                common = dict(voice=voice, duration=10, narration="hello there everyone", title="My Video: Part 1",
                              aspect="16:9", resolution="720p", seconds=6, motion=True, music="song.mp3")
                final = build.execute(**common)
                self.assertEqual(final.name, "My-Video-Part-1.mp4")
                self.assertEqual((calls["ask"], calls["image"], calls["video"]),
                                 (1, ["img one", "img two"], ["pan", "orbit"]))
                self.assertEqual([c[0] for c in calls["run"]], ["ffmpeg"] * 4)   # 2 cuts, concat, mux
                self.assertIn("-stream_loop", calls["run"][-1])
                # Same voiceover again (after a stop or an empty balance): nothing is generated twice.
                build.execute(**common)
                self.assertEqual((calls["ask"], len(calls["image"]), len(calls["video"])), (1, 2, 2))
                # A different shot length is a new plan.
                build.execute(**dict(common, seconds=3, motion=False))
                self.assertEqual((calls["ask"], len(calls["image"]), len(calls["video"])), (2, 6, 2))
                self.assertIn("zoompan", " ".join(calls["run"][-3]))   # last cut before concat and mux
        finally:
            hf.text_to_image, hf.image_to_video, hf.upload_file, hf.download = original


if __name__ == "__main__":
    unittest.main()
