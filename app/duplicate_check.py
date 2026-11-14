"""Avoid making a video that repeats one the user already has.

Titles come from the user's own YouTube channel (read-only, never starts a sign-in) and from the local
project folders. They go into the idea prompt as a "do not repeat" list, and any idea that is still too
close to one of them is dropped afterwards.
"""
import difflib
import re
from pathlib import Path

STOPWORDS = frozenset(
    "a an and are as at be by do does for from how in is it its of on or that the this to why what who "
    "with without you your yours my our we they their will can just only ever never".split())
SLUG_SUFFIX = re.compile(r"-\d{8}$")   # projects are named <title-slug>-<MMDDHHMM>
THRESHOLD = 0.7


def tokens(title):
    """Meaningful words of a title. Every number counts the same, so '3-minute' and '5-minute' match."""
    words = re.findall(r"[a-z0-9]+", str(title or "").lower())
    return {"#" if w.isdigit() else w for w in words if w not in STOPWORDS}


def similarity(a, b):
    """0..1: how much two titles look like the same video."""
    ta, tb = tokens(a), tokens(b)
    if not ta or not tb:
        return 0.0
    shared = len(ta & tb)
    score = shared / len(ta | tb)
    small, large = (ta, tb) if len(ta) <= len(tb) else (tb, ta)
    if len(small) >= 3 and small <= large:   # a slug cut short is still the same video
        score = max(score, 0.9)
    text = difflib.SequenceMatcher(None, " ".join(sorted(ta)), " ".join(sorted(tb))).ratio()
    return max(score, text if text >= 0.85 else 0.0)


def find_duplicate(title, existing, threshold=THRESHOLD):
    """The closest existing title if it is at least `threshold` similar to `title`, else None."""
    best, best_score = None, 0.0
    for other in existing:
        score = similarity(title, other)
        if score > best_score:
            best, best_score = other, score
    return best if best_score >= threshold else None


def filter_ideas(ideas, existing, threshold=THRESHOLD):
    """Split ideas into (kept, dropped). dropped is a list of (idea, matching existing title)."""
    kept, dropped = [], []
    seen = list(existing)
    for idea in ideas or []:
        title = idea.get("title", "") if isinstance(idea, dict) else str(idea)
        match = find_duplicate(title, seen, threshold)
        if match is None:
            kept.append(idea)
            seen.append(title)   # two near-identical ideas in one batch also count as a repeat
        else:
            dropped.append((idea, match))
    return kept, dropped


def local_titles(*project_roots):
    """Titles of video projects already on disk, read from their folder names (newest first)."""
    folders = []
    for root in project_roots:
        root = Path(root)
        if not root.is_dir():
            continue
        for p in root.iterdir():
            if p.is_dir() and SLUG_SUFFIX.search(p.name):
                folders.append(p)
    folders.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    out, seen = [], set()
    for p in folders:
        title = SLUG_SUFFIX.sub("", p.name).replace("-", " ").strip()
        if title and title not in seen:
            seen.add(title)
            out.append(title)
    return out


def youtube_titles(service, limit=500):
    """Titles of every upload on the signed-in channel, private and unlisted included (newest first)."""
    channels = service.channels().list(part="contentDetails", mine=True).execute()
    items = channels.get("items") or []
    if not items:
        return []
    uploads = items[0]["contentDetails"]["relatedPlaylists"]["uploads"]
    titles, token = [], None
    while len(titles) < limit:
        resp = service.playlistItems().list(part="snippet", playlistId=uploads, maxResults=50,
                                            pageToken=token).execute()
        for item in resp.get("items", []):
            title = (item.get("snippet") or {}).get("title")
            if title and title not in ("Private video", "Deleted video"):
                titles.append(title)
        token = resp.get("nextPageToken")
        if not token:
            break
    return titles[:limit]


def collect(project_roots, get_service=None, log=None):
    """(titles, notes): channel titles first, then local ones. A failed YouTube read never stops the run."""
    log = log or (lambda *a: None)
    titles, notes = [], []
    if get_service is not None:
        try:
            service = get_service()
            remote = youtube_titles(service)
            titles += remote
            notes.append(f"{len(remote)} YouTube videos")
        except Exception as exc:   # not signed in, offline, quota: fall back to local projects only
            notes.append("YouTube not checked")
            log(f"Duplicate check could not read YouTube: {exc}")
    local = [t for t in local_titles(*project_roots) if t not in titles]
    titles += local
    notes.append(f"{len(local)} local projects")
    return titles, notes


def prompt_line(titles, max_titles=60, max_chars=90):
    """The 'do not repeat' sentence for the idea prompt, or '' when there is nothing to avoid."""
    short = [t[:max_chars] for t in titles[:max_titles]]
    if not short:
        return ""
    import json
    return ("These videos already exist on the user's channel or computer. Do not repeat them or make "
            f"close variations (same idea with a different number or wording): {json.dumps(short)}\n")
