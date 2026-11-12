import json
import os
import sys
import tempfile
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch

import shots_video as sv
from parallel_commands import CommandGroup


class ParallelShotsTests(unittest.TestCase):
    def fixture(self, tmp, make_still, make_clip=None, check=lambda: None):
        root = Path(tmp)
        voice = root / "voice.mp3"
        voice.write_bytes(b"voice")
        self.commands, self.progress = [], []

        def run(cmd):
            self.commands.append(cmd)
            Path(cmd[-1]).write_bytes(b"video")
            return 0, ""

        build = sv.ShotsBuild(root, folder="openart", make_still=make_still, make_clip=make_clip,
                              ask=lambda _: json.dumps([{"n": i, "image": str(i), "motion": str(i)}
                                                        for i in range(1, 5)]),
                              run=run, progress=lambda f, t: self.progress.append(f), check=check,
                              log=lambda _: None)
        args = dict(voice=voice, duration=12, narration="story", title="test", aspect="16:9",
                    resolution="720p", seconds=3, parallel=2, motion=False)
        return build, args

    def media(self, dest, suffix):
        Path(dest).mkdir(parents=True, exist_ok=True)
        out = Path(dest) / ("result" + suffix)
        out.write_bytes(b"media")
        return out

    def test_bounded_overlap_dependencies_order_and_resume(self):
        lock, barrier = threading.Lock(), threading.Barrier(2)
        active, peak, images, clips = 0, 0, [], []
        second_finished = threading.Event()

        def still(prompt, aspect, dest):
            nonlocal active, peak
            with lock:
                active += 1
                peak = max(peak, active)
                images.append(prompt)
            if prompt in ("1", "2"):
                barrier.wait(timeout=5)
                if prompt == "1":
                    self.assertTrue(second_finished.wait(5))
                else:
                    second_finished.set()
            result = self.media(dest, ".png")
            with lock:
                active -= 1
            return result

        def clip(prompt, still, aspect, resolution, dest):
            self.assertTrue(Path(still).is_file())
            clips.append(prompt)
            return self.media(dest, ".mp4")

        with tempfile.TemporaryDirectory() as tmp:
            build, args = self.fixture(tmp, still, clip)
            build.execute(**dict(args, motion=True))
            self.assertEqual(peak, 2)
            self.assertCountEqual(images, ["1", "2", "3", "4"])
            self.assertCountEqual(clips, images)
            cuts = self.commands[:4]
            self.assertEqual([Path(cmd[-1]).name for cmd in cuts], [f"seg_{i:03d}.mp4" for i in range(1, 5)])
            listing = (Path(tmp) / "openart/segments/concat.txt").read_text()
            self.assertLess(listing.index("seg_001"), listing.index("seg_002"))
            self.assertEqual(self.progress, sorted(self.progress))
            build.execute(**dict(args, motion=True, parallel=1))
            self.assertEqual(len(images), 4)
            self.assertEqual(len(clips), 4)

    def test_failure_stops_new_submissions_and_saves_inflight_images_for_resume(self):
        barrier, failed = threading.Barrier(2), threading.Event()
        calls = []

        def still(prompt, aspect, dest):
            calls.append(prompt)
            if prompt in ("1", "2"):
                barrier.wait(timeout=5)
                if prompt == "1":
                    failed.set()
                    raise RuntimeError("insufficient credits")
                self.assertTrue(failed.wait(5))
            return self.media(dest, ".png")

        with tempfile.TemporaryDirectory() as tmp:
            build, args = self.fixture(tmp, still)
            with self.assertRaisesRegex(RuntimeError, "insufficient credits"):
                build.execute(**args)
            self.assertCountEqual(calls, ["1", "2"])
            self.assertTrue((Path(tmp) / "openart/shot_002.png").exists())
            self.assertEqual(self.commands, [])
            calls.clear()
            build.make_still = lambda p, a, d: (calls.append(p), self.media(d, ".png"))[1]
            build.execute(**args)
            self.assertCountEqual(calls, ["1", "3", "4"])

    def test_cancel_preserves_stills_and_does_not_start_motion_or_more_shots(self):
        cancelled, barrier = threading.Event(), threading.Barrier(2)
        images, clips = [], []

        def check():
            if cancelled.is_set():
                raise RuntimeError("Stopped.")

        def still(prompt, aspect, dest):
            images.append(prompt)
            barrier.wait(timeout=5)
            cancelled.set()
            return self.media(dest, ".png")

        with tempfile.TemporaryDirectory() as tmp:
            build, args = self.fixture(tmp, still, lambda *a: clips.append(a), check)
            with self.assertRaisesRegex(RuntimeError, "Stopped"):
                build.execute(**dict(args, motion=True))
            self.assertCountEqual(images, ["1", "2"])
            self.assertEqual(clips, [])
            self.assertTrue((Path(tmp) / "openart/shot_001.png").exists())
            self.assertTrue((Path(tmp) / "openart/shot_002.png").exists())

    def test_worker_limits(self):
        self.assertEqual([sv.parallel_shots(v) for v in (None, "", "bad", 0, 1, "3", 99)],
                         [3, 3, 3, 1, 1, 3, 4])


class CommandGroupTests(unittest.TestCase):
    def test_concurrent_output_is_separate_and_stop_terminates_every_process(self):
        ready, lock, count = threading.Event(), threading.Lock(), 0

        def log(tag, text):
            nonlocal count
            if tag == "OUT":
                with lock:
                    count += 1
                    if count == 2:
                        ready.set()

        group = CommandGroup(os.environ.copy(), log=log)
        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [pool.submit(group.run, [sys.executable, "-u", "-c",
                        f"import time; print('{marker}', flush=True); time.sleep(60)"], tempfile.gettempdir())
                       for marker in ("one", "two")]
            try:
                self.assertTrue(ready.wait(10), "both commands should run concurrently")
            finally:
                group.stop()
            results = [f.result(timeout=10) for f in futures]
        self.assertEqual([text for rc, text in results], ["one", "two"])
        self.assertTrue(all(rc != 0 for rc, text in results))
        self.assertEqual(group._processes, set())
        with patch("parallel_commands.subprocess.Popen") as popen:
            with self.assertRaisesRegex(RuntimeError, "Stopped"):
                group.run(["unused"], ".", check=lambda: (_ for _ in ()).throw(RuntimeError("Stopped.")))
            popen.assert_not_called()


if __name__ == "__main__":
    unittest.main()
