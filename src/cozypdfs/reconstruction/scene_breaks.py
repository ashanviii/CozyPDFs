"""Scene-break marker detection.

A scene break ("* * *", a centered bullet, a lone "~") is short, made only
of a handful of symbol characters, and visually isolated -- but the amount
of whitespace a PDF actually leaves around one is inconsistent enough that
relying purely on vertical-gap heuristics misses cases where the break
sits close to the surrounding paragraphs. Because the marker text itself
is so distinctive, it is instead recognized directly, in two places that
must agree: `paragraphs.py` uses it to isolate such a line into its own
paragraph candidate immediately (rather than letting it merge into a
neighbor), and `structure.py` uses the same check to classify the
resulting candidate as a `SceneBreak` block.
"""

from __future__ import annotations

import re

_SCENE_BREAK_RE = re.compile(r"^[\*•·#~\-—\s]+$")
_MAX_SYMBOL_LEN = 7


def looks_like_scene_break(text: str) -> bool:
    stripped = text.strip()
    if not stripped or len(stripped.replace(" ", "")) > _MAX_SYMBOL_LEN:
        return False
    return bool(_SCENE_BREAK_RE.match(stripped))
