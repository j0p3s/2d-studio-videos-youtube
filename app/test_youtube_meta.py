import unittest

from youtube_meta import complete_meta, thumbnail_text, tags_from

TITLE = "The 3‑Minute Habit Hack That Guarantees Morning Discipline"
NARRATION = ("What if the secret to waking up early is just 3 minutes? Imagine slipping out of bed feeling "
             "energized before your coffee even brews. Tomorrow your future self will thank you.")


class CompleteMetaTest(unittest.TestCase):
    def test_empty_meta_gets_every_field(self):
        meta = complete_meta({}, TITLE, NARRATION, "Discipline & Habits", shorts=True)
        self.assertTrue(meta["description"].strip())
        self.assertGreaterEqual(len(meta["tags"]), 5)
        self.assertTrue(meta["thumbnail_text"])
        self.assertIn("#Shorts", meta["description"])
        self.assertIn("What if the secret", meta["description"])

    def test_title_is_made_drawable(self):
        meta = complete_meta({}, TITLE, NARRATION)
        self.assertNotIn("‑", meta["title"])
        self.assertEqual(thumbnail_text(TITLE), "3-MINUTE HABIT HACK MORNING")

    def test_model_values_are_kept(self):
        given = {"title": "My Title", "tags": ["a b c", "second"], "description": "Mine.", "thumbnail_text": "WAKE UP"}
        meta = complete_meta(given, TITLE, NARRATION)
        self.assertEqual(meta["description"], "Mine.")
        self.assertEqual(meta["tags"], ["a b c", "second"])
        self.assertEqual(meta["thumbnail_text"], "WAKE UP")
        self.assertEqual(meta["title"], "My Title")

    def test_partial_meta_only_fills_the_gaps(self):
        meta = complete_meta({"tags": "habit, discipline", "description": "  "}, TITLE, NARRATION)
        self.assertEqual(meta["tags"], ["habit", "discipline"])
        self.assertIn("Tomorrow", meta["description"] + NARRATION)
        self.assertTrue(meta["description"].strip())

    def test_non_dict_meta_and_empty_narration(self):
        meta = complete_meta(None, TITLE, "")
        self.assertTrue(meta["description"].strip())
        self.assertTrue(meta["tags"])

    def test_tags_are_unique_and_within_youtube_limit(self):
        tags = tags_from(TITLE, NARRATION * 20, "Self Improvement")
        self.assertEqual(len(tags), len(set(tags)))
        self.assertLessEqual(sum(len(t) + 1 for t in tags), 500)


if __name__ == "__main__":
    unittest.main()
