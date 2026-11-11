import tempfile
import unittest
from pathlib import Path

import session_log


class SessionLogTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.path = Path(self.folder.name) / "studio.log"

    def tearDown(self):
        session_log.start(Path(self.folder.name) / "other.log")
        session_log._file.close()
        session_log._file = None
        self.folder.cleanup()

    def read(self):
        return self.path.read_text(encoding="utf-8")

    def test_each_start_replaces_the_previous_session(self):
        session_log.start(self.path)
        session_log.write("INFO", "first session")
        session_log.start(self.path)
        session_log.write("INFO", "second session")
        self.assertNotIn("first session", self.read())
        self.assertIn("INFO  second session", self.read())

    def test_secrets_are_masked(self):
        session_log.start(self.path, {"GEMINI_API_KEY": "my-private-key-123", "PATH": "C:/Windows/System32"})
        session_log.write("OUT", "sent my-private-key-123 and AIzaSyA1234567890abcdefghijklmn to C:/Windows/System32")
        text = self.read()
        self.assertNotIn("my-private-key-123", text)
        self.assertNotIn("AIzaSy", text)
        self.assertIn("sent *** and *** to C:/Windows/System32", text)

    def test_repeated_line_is_written_once_and_errors_keep_the_traceback(self):
        session_log.start(self.path)
        session_log.write("OUT", "rendering")
        session_log.write("OUT", "rendering")
        try:
            raise ValueError("bad model")
        except ValueError:
            session_log.error("Animate failed")
        text = self.read()
        self.assertEqual(text.count("rendering"), 1)
        self.assertIn("ERROR Animate failed", text)
        self.assertIn("ValueError: bad model", text)


if __name__ == "__main__":
    unittest.main()
