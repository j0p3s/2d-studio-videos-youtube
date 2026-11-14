"""Which folder holds the current video project, for the Open project folder button."""
from pathlib import Path


def project_folder(studio, work, state):
    """Studio project folder of the current video, else the folder of its MP4, else its work folder."""
    slug = (state or {}).get("slug") or ""
    candidates = []
    if slug:
        candidates.append(Path(studio) / "projects" / slug)
    video = (state or {}).get("video")
    if video:
        path = Path(video)
        candidates.append(path.parent.parent if path.parent.name.lower() == "out" else path.parent)
    if slug:
        candidates.append(Path(work) / slug)
    return next((p for p in candidates if p.is_dir()), None)
