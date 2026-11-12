"""Thumbnail helpers: text that the title fonts can draw, and a safe preview image swap.

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


def set_label_image(label, image, text):
    """Show an image (or none) on a CustomTkinter label.

    After image=None CustomTkinter leaves the old Tk image name on its inner label. Once that image
    is freed, every later change fails with: image "pyimage1" doesn't exist. Clear the name first.
    """
    inner = getattr(label, "_label", None)
    if inner is not None:
        try:
            inner.configure(image="")
        except Exception:
            pass
    label.configure(image=image, text=text)


def drawable(text):
    """Return text with typographic look-alikes replaced by plain characters, spaces collapsed."""
    return " ".join(str(text or "").translate(_TABLE).split())
