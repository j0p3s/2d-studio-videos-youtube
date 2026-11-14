"""Fill in YouTube details the script model left out.

The script step asks the model for a META block (description, tags, thumbnail text). Small local
models often skip it or return broken JSON, which left the upload page empty. complete_meta keeps
every usable value the model gave and builds the rest from the title and narration.
"""
import re

from thumb_text import drawable

_STOP = set("""a an and are as at be but by can do does for from get got had has have how if in into is it its
just more most no not of on one or our out so than that the their them then there these they this to up was we
what when which who why will with without you your yours guarantees guarantee""".split())
_MAX_TAG_CHARS = 450


def _words(text):
    return re.findall(r"[A-Za-z0-9][A-Za-z0-9'-]*", drawable(text))


def _content(text):
    return [w for w in _words(text) if w.lower() not in _STOP]


def _sentences(text):
    flat = " ".join(drawable(text).split())
    return [s.strip() for s in re.split(r"(?<=[.!?])\s+", flat) if s.strip()]


def thumbnail_text(title):
    """Two to four strong words from the title, e.g. '3-MINUTE HABIT HACK'."""
    words = _content(title)[:4]
    if len(words) < 2:
        words = _words(title)[:3]
    return " ".join(words).upper()


def tags_from(title, narration="", niche=""):
    seen, tags, used = set(), [], 0
    words = _content(title)
    phrases = [" ".join(words[i:i + 2]) for i in range(len(words) - 1)]
    candidates = [drawable(title).lower().rstrip("."), *phrases, *words,
                  *(_content(niche)), *(_content(narration))[:6], "self improvement", "motivation", "habits"]
    for cand in candidates:
        cand = cand.strip().lower()
        if len(cand) < 3 or cand in seen or used + len(cand) > _MAX_TAG_CHARS:
            continue
        seen.add(cand)
        tags.append(cand)
        used += len(cand) + 1
        if len(tags) >= 15:
            break
    return tags


def description_from(title, narration, tags, shorts=False):
    sents = _sentences(narration)
    hook = " ".join(sents[:2])[:300]
    close = (f"{drawable(title)}. Watch to the end, then try it tomorrow and tell us how it went in the comments."
             if title else "Watch to the end and tell us how it went in the comments.")
    tagged = ["#" + re.sub(r"[^A-Za-z0-9]", "", t.title()) for t in tags if re.sub(r"[^A-Za-z0-9]", "", t)]
    hashtags = list(dict.fromkeys(tagged))[:4]
    if shorts and "#Shorts" not in hashtags:
        hashtags.append("#Shorts")
    return "\n\n".join(p for p in (hook, close, " ".join(hashtags)) if p)


def _blank(value):
    return value is None or value == "" or value == [] or value == {}


def complete_meta(meta, title, narration, niche="", shorts=False):
    """Return meta with every missing field filled; usable model values are kept as they are."""
    meta = dict(meta) if isinstance(meta, dict) else {}
    meta["title"] = drawable(meta.get("title") or title)
    if _blank(meta.get("thumbnail_text")):
        meta["thumbnail_text"] = thumbnail_text(meta["title"])
    tags = meta.get("tags")
    if isinstance(tags, str):
        tags = [t.strip() for t in tags.split(",") if t.strip()]
    if not isinstance(tags, list) or not [t for t in tags if str(t).strip()]:
        tags = tags_from(meta["title"], narration, niche)
    meta["tags"] = [drawable(t) for t in tags if str(t).strip()]
    if _blank(meta.get("description")) or not str(meta["description"]).strip():
        meta["description"] = description_from(meta["title"], narration, meta["tags"], shorts)
    return meta
