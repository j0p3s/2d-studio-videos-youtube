"""Credit-saving OpenArt defaults shared by manual builds and Auto."""
from shots_video import clip_seconds, parallel_shots, plan_key, slices


RETENTION_BRIEF = """Audience retention and honest packaging:
Open with a specific surprising situation, conflict or question in the first 1-3 seconds;
skip greetings, channel introductions and generic claims. Deliver the title's promise.
Build short cause-and-effect beats with concrete examples, escalating stakes and regular
payoffs; resolve the opening question before the ending. Remove repeated ideas and filler.
For Shorts, use one clear idea with an immediate hook and a complete payoff. For long
videos, vary the examples and pace without padding the requested length. Write natural,
easy-to-speak narration. Titles and thumbnail text should be specific, complementary and
truthful; never invent facts, sources, statistics or promises to increase clicks.
"""


def migrate_defaults(settings):
    settings.setdefault("openart_save_credits", True)
    return settings


def build_options(settings, *, shorts=False, saved=None, voice=None, duration=None, aspect=None):
    economy = bool(settings.get("openart_save_credits", True))
    options = dict(economy=economy, seconds=(6 if shorts else 12) if economy else
                   clip_seconds(settings.get("openart_clip_seconds")),
                   motion=False if economy else bool(settings.get("openart_motion", True)),
                   parallel=parallel_shots(settings.get("openart_parallel_shots")), resuming=False)
    # An existing compatible plan wins over new defaults. Never discard paid media
    # just because the app was updated or the credit-saving switch changed.
    if economy and isinstance(saved, dict) and voice and duration is not None and aspect:
        try:
            seconds = clip_seconds(saved["seconds"])
            motion = saved["motion"]
            shots = saved["shots"]
            if (isinstance(motion, bool) and isinstance(shots, list)
                    and len(shots) == len(slices(duration, seconds))
                    and all(isinstance(s, (list, tuple)) and len(s) == 2
                            and all(isinstance(p, str) and p.strip() for p in s) for s in shots)
                    and saved.get("key") == plan_key(voice, duration, seconds, aspect, motion)):
                options.update(seconds=seconds, motion=motion, resuming=True)
        except (KeyError, TypeError, ValueError):
            pass
    return options
