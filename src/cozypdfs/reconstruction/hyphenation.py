"""Line-break hyphenation handling.

PDF line wrapping sometimes splits a word across a hyphen purely because of
column width, not because the author wrote a hyphenated compound. This
module makes that call with a simple, dependency-free signal: if the text
right after the hyphen continues in lowercase, it reads as the second half
of a split word ("some-" / "thing" -> "something"). Anything else -- the
next word starts uppercase, or what follows isn't a letter -- is treated as
a genuine hyphen and left alone. Silently joining "well-" / "Known" into
"wellKnown" would corrupt the text, and fidelity matters more here than
aggressively normalizing every case (see `models.ParagraphCandidate`).
"""

from __future__ import annotations

_HYPHEN_CHARS = "-‐‑"  # hyphen-minus, hyphen, non-breaking hyphen


def ends_with_breaking_hyphen(text: str) -> bool:
    """Whether `text` ends in a hyphen that looks like a line-wrap artifact."""
    stripped = text.rstrip()
    if len(stripped) < 2 or stripped[-1] not in _HYPHEN_CHARS:
        return False
    return stripped[-2].isalpha()


def should_dehyphenate(next_line_text: str) -> bool:
    """Whether the hyphen should be dropped and the words joined directly."""
    first_char = next_line_text[:1]
    return first_char.islower()
