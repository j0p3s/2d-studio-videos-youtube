import unittest
from pathlib import Path

from thumb_text import drawable


class DrawableTest(unittest.TestCase):
    def test_non_breaking_hyphen_becomes_plain_hyphen(self):
        self.assertEqual(drawable("The 5\u2011Minute Habit Hack That Actually Works"),
                         "The 5-Minute Habit Hack That Actually Works")

    def test_dashes_quotes_spaces_and_hidden_marks(self):
        self.assertEqual(drawable("A\u2013B \u2014 \u201cWhy\u201d it\u2019s\u00a0here\u2026\u200b"),
                         'A-B - "Why" it\'s here...')

    def test_plain_text_and_empty_values(self):
        self.assertEqual(drawable("  STOP   SCROLLING! "), "STOP SCROLLING!")
        self.assertEqual(drawable(None), "")

    def test_title_fonts_have_every_glyph(self):
        fonts = [f for f in (Path(r"C:\Windows\Fonts\impact.ttf"), Path(r"C:\Windows\Fonts\arialbd.ttf")) if f.exists()]
        if not fonts:
            self.skipTest("title fonts are not installed")
        try:
            from PIL import ImageFont
        except ImportError:
            self.skipTest("Pillow is not installed")
        text = drawable("The 5\u2011Minute \u2014 \u201cHack\u201d\u2026").upper()
        for f in fonts:
            font = ImageFont.truetype(str(f), 80)
            square = bytes(font.getmask("\uffff"))  # the "no such character" box
            self.assertEqual(bytes(font.getmask("\u2011")), square, f"{f.name}: test assumption")
            self.assertEqual([c for c in text if c != " " and bytes(font.getmask(c)) == square], [], f.name)


if __name__ == "__main__":
    unittest.main()
