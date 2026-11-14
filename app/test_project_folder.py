import tempfile
import unittest
from pathlib import Path

from project_folder import project_folder


class ProjectFolderTest(unittest.TestCase):
    def test_prefers_the_studio_project_then_video_then_work(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            studio, work = root / "studio", root / "work"
            (work / "a").mkdir(parents=True)
            state = {"slug": "a"}
            self.assertEqual(project_folder(studio, work, state), work / "a")
            (studio / "projects" / "a" / "out").mkdir(parents=True)
            self.assertEqual(project_folder(studio, work, state), studio / "projects" / "a")

    def test_uses_the_folder_above_out_for_a_video_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "elsewhere" / "p" / "out").mkdir(parents=True)
            state = {"slug": "gone", "video": str(root / "elsewhere/p/out/v.mp4")}
            self.assertEqual(project_folder(root / "s", root / "w", state), root / "elsewhere" / "p")

    def test_none_when_nothing_exists(self):
        self.assertIsNone(project_folder("nope", "nope", {"slug": "x"}))
        self.assertIsNone(project_folder("nope", "nope", None))


if __name__ == "__main__":
    unittest.main()
