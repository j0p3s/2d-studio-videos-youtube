import tempfile
import time
import unittest
from pathlib import Path

import duplicate_check as dc


class FakeRequest:
    def __init__(self, data):
        self.data = data

    def execute(self):
        return self.data


class FakeService:
    def __init__(self, channel_items, pages):
        self.channel_items, self.pages, self.calls = channel_items, pages, []

    def channels(self):
        outer = self

        class C:
            def list(self, **kw):
                return FakeRequest({"items": outer.channel_items})
        return C()

    def playlistItems(self):
        outer = self

        class P:
            def list(self, **kw):
                outer.calls.append(kw.get("pageToken"))
                return FakeRequest(outer.pages[kw.get("pageToken")])
        return P()


UPLOADS = [{"contentDetails": {"relatedPlaylists": {"uploads": "UU1"}}}]


def page(titles, nxt=None):
    data = {"items": [{"snippet": {"title": t}} for t in titles]}
    if nxt:
        data["nextPageToken"] = nxt
    return data


class SimilarityTests(unittest.TestCase):
    def test_changed_number_is_the_same_video(self):
        self.assertIsNotNone(dc.find_duplicate("The 3-Minute Habit Hack That Guarantees Discipline",
                                               ["The 5-Minute Habit Hack That Guarantees Discipline"]))

    def test_cut_short_slug_matches_full_title(self):
        self.assertIsNotNone(dc.find_duplicate("The 5-Minute Habit Hack That Guarantees Discipline",
                                               ["the 5 minute habit hack that guarantees"]))

    def test_different_topics_do_not_match(self):
        self.assertIsNone(dc.find_duplicate("Why Cold Showers Rewire Your Brain",
                                            ["The 5-Minute Habit Hack That Guarantees Discipline",
                                             "What If The Moon Disappeared"]))

    def test_empty_titles_never_match(self):
        self.assertEqual(dc.similarity("", "anything"), 0.0)
        self.assertIsNone(dc.find_duplicate("", [""]))

    def test_filter_drops_repeats_and_in_batch_duplicates(self):
        ideas = [{"title": "5 Habits Of Calm People"}, {"title": "Why Sleep Beats Coffee"},
                 {"title": "Why Sleep Beats Coffee Every Time"}]
        kept, dropped = dc.filter_ideas(ideas, ["7 Habits Of Calm People"])
        self.assertEqual([i["title"] for i in kept], ["Why Sleep Beats Coffee"])
        self.assertEqual(len(dropped), 2)
        self.assertEqual(dropped[0][1], "7 Habits Of Calm People")


class SourcesTests(unittest.TestCase):
    def test_local_titles_strip_timestamp_and_skip_other_folders(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "the-5-minute-habit-hack-11131502").mkdir()
            time.sleep(0.02)
            (root / "calm-mornings-11140120").mkdir()
            (root / "scratch").mkdir()
            (root / "notes-11131502.txt").write_text("x")
            self.assertEqual(dc.local_titles(root, root / "missing"),
                             ["calm mornings", "the 5 minute habit hack"])

    def test_youtube_titles_follow_pages_and_skip_placeholders(self):
        svc = FakeService(UPLOADS, {None: page(["A", "Private video"], "n2"), "n2": page(["B"])})
        self.assertEqual(dc.youtube_titles(svc), ["A", "B"])
        self.assertEqual(svc.calls, [None, "n2"])

    def test_channel_without_uploads(self):
        self.assertEqual(dc.youtube_titles(FakeService([], {})), [])

    def test_collect_survives_youtube_failure(self):
        def broken():
            raise RuntimeError("not signed in")
        logged = []
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "calm-mornings-11140120").mkdir()
            titles, notes = dc.collect([tmp], broken, logged.append)
        self.assertEqual(titles, ["calm mornings"])
        self.assertIn("YouTube not checked", notes)
        self.assertTrue(logged)

    def test_collect_puts_channel_titles_first_without_repeats(self):
        svc = FakeService(UPLOADS, {None: page(["calm mornings"])})
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "calm-mornings-11140120").mkdir()
            titles, notes = dc.collect([tmp], lambda: svc)
        self.assertEqual(titles, ["calm mornings"])
        self.assertEqual(notes, ["1 YouTube videos", "0 local projects"])

    def test_prompt_line_is_empty_without_titles_and_capped(self):
        self.assertEqual(dc.prompt_line([]), "")
        line = dc.prompt_line([f"t{i}" for i in range(100)], max_titles=5)
        self.assertIn("t4", line)
        self.assertNotIn("t5", line)


if __name__ == "__main__":
    unittest.main()
