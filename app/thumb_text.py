"""Thumbnail text that the title fonts can draw.

AI-written titles often carry typographic characters (non-breaking hyphen, narrow spaces,
zero-width marks) that Impact and Arial Bold have no glyph for, which shows as an empty square.
"""

_REPLACE = {
    # hyphens and dashes
    "‐": "-", "‑": "-", "‒": "-", "–": "-", "—": "-", "―": "-",
    "−": "-", "­": "", "﹘": "-", "﹣": "-", "－": "-",
    # quotes
    "‘": "'", "’": "'", "‚": "'", "‛": "'", "′": "'",
    "“": '"', "”": '"', "„": '"', "‟": '"', "″": '"',
    # other punctuation
    "…": "...", "•": "-", "⁄": "/",
    # zero-width marks
    "​": "", "‌": "", "‍": "", "⁠": "", "﻿": "",
}
_SPACES = "               　"
_TABLE = str.maketrans({**_REPLACE, **{c: " " for c in _SPACES}})


def drawable(text):
    """Return text with typographic look-alikes replaced by plain characters, spaces collapsed."""
    return " ".join(str(text or "").translate(_TABLE).split())
