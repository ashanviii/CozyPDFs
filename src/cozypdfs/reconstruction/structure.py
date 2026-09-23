"""Stage 6: semantic document reconstruction.

Turns the flat stream of `ParagraphCandidate`s into the final `Book`:
chapters are split out at recognized chapter headings (see `chapters.py`),
and every remaining candidate is classified into a concrete semantic block
-- paragraph, dialogue, blockquote, epigraph, scene break, heading, or
image -- using the signals paragraph reconstruction attached (indentation,
centering, quote-opening characters, font size) rather than any raw
coordinate.

This is the boundary the architecture is built around: everything this
function returns (`Book`) is geometry-free. The EPUB generator downstream
is not allowed to see a bounding box, a font size, or a page number -- only
what kind of thing each block *is*.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from . import chapters as chapters_mod
from .scene_breaks import looks_like_scene_break
from ..models import (
    Blockquote,
    Block,
    Book,
    BookMetadata,
    Chapter,
    ChapterKind,
    DocumentStats,
    Epigraph,
    Footnote,
    Heading,
    ImageAsset,
    ImageBlock,
    Paragraph,
    ParagraphCandidate,
    ParagraphVariant,
    Poem,
    RoughKind,
    Run,
    SceneBreak,
)

_COVER_AREA_RATIO = 0.5
_BY_LINE_RE = re.compile(r"^by\s+(.+)$", re.IGNORECASE)
_AUTHOR_LINE_MAX_LEN = 60
_TITLE_MAX_LEN = 200
_CAPTION_MAX_LEN = 200
_DEAR_SALUTATION_RE = re.compile(r"^dear\s+[A-Z]", re.IGNORECASE)
_FOOTNOTE_LEADING_RE = re.compile(r"^\s*([0-9]{1,3}|[*†‡])[.\)]?\s+")
_POEM_MIN_LINES = 2
_POEM_SHORT_LINE_THRESHOLD = 0.5


@dataclass(slots=True)
class _ChapterDraft:
    kind: ChapterKind
    number: str | None
    title: str | None
    candidates: list[ParagraphCandidate] = field(default_factory=list)


class DefaultStructureEngine:
    """`StructureEngine` implementation."""

    def build(
        self,
        candidates: list[ParagraphCandidate],
        stats: DocumentStats,
        default_title: str,
    ) -> Book:
        cover, candidates = _extract_cover(candidates, stats)
        front_matter, drafts = _group_by_chapter(candidates)
        title, author, remaining_front_matter = _extract_title_author(
            front_matter, default_title
        )

        chapters: list[Chapter] = []
        used_ids: set[str] = set()

        fm_blocks = _classify_blocks(remaining_front_matter)
        if fm_blocks:
            chapters.append(
                Chapter(
                    id=_unique_id("front-matter", used_ids),
                    title=None,
                    number=None,
                    kind=ChapterKind.FRONT_MATTER,
                    blocks=fm_blocks,
                )
            )

        for idx, draft in enumerate(drafts, start=1):
            chapters.append(
                Chapter(
                    id=_unique_id(_chapter_id_base(draft, idx), used_ids),
                    title=draft.title,
                    number=draft.number,
                    kind=draft.kind,
                    blocks=_classify_blocks(draft.candidates),
                )
            )

        return Book(
            metadata=BookMetadata(title=title, author=author), chapters=chapters, cover=cover
        )


def _extract_cover(
    candidates: list[ParagraphCandidate], stats: DocumentStats
) -> tuple[ImageAsset | None, list[ParagraphCandidate]]:
    page_area = stats.page_width * stats.page_height
    if page_area <= 0:
        return None, candidates
    for i, c in enumerate(candidates):
        if c.rough_kind == RoughKind.IMAGE and c.image is not None and 0 in c.source_pages:
            area = c.image.bbox.width * c.image.bbox.height
            if area / page_area >= _COVER_AREA_RATIO:
                asset = _make_image_asset(c.image, "cover")
                return asset, candidates[:i] + candidates[i + 1 :]
    return None, candidates


def _group_by_chapter(
    candidates: list[ParagraphCandidate],
) -> tuple[list[ParagraphCandidate], list[_ChapterDraft]]:
    front_matter: list[ParagraphCandidate] = []
    drafts: list[_ChapterDraft] = []
    current: _ChapterDraft | None = None

    for c in candidates:
        if c.rough_kind == RoughKind.HEADING_CANDIDATE:
            info = chapters_mod.classify_heading(c.text)
            if info is not None:
                current = _ChapterDraft(kind=info.kind, number=info.number, title=info.title)
                drafts.append(current)
                continue
        (current.candidates if current is not None else front_matter).append(c)

    return front_matter, drafts


def _extract_title_author(
    front_matter: list[ParagraphCandidate], default_title: str
) -> tuple[str, str | None, list[ParagraphCandidate]]:
    text_candidates = [
        c for c in front_matter if c.rough_kind != RoughKind.IMAGE and c.text.strip()
    ]
    if not text_candidates:
        return default_title, None, front_matter

    title_cand = max(text_candidates, key=lambda c: c.max_font_size)
    title_text = title_cand.text.strip()
    if not title_text or len(title_text) > _TITLE_MAX_LEN:
        return default_title, None, front_matter

    author: str | None = None
    author_cand: ParagraphCandidate | None = None
    idx = text_candidates.index(title_cand)
    for c in text_candidates[idx + 1 :]:
        t = c.text.strip()
        if m := _BY_LINE_RE.match(t):
            author, author_cand = m.group(1).strip(), c
            break
        if 0 < len(t) <= _AUTHOR_LINE_MAX_LEN:
            author, author_cand = t, c
            break

    excluded = {id(title_cand)}
    if author_cand is not None:
        excluded.add(id(author_cand))
    remaining = [c for c in front_matter if id(c) not in excluded]
    return title_text, author, remaining


def _classify_blocks(candidates: list[ParagraphCandidate]) -> list[Block]:
    blocks: list[Block] = []
    i, n = 0, len(candidates)

    while i < n:
        c = candidates[i]

        if c.rough_kind == RoughKind.IMAGE:
            block, consumed = _make_image_block(candidates, i)
            blocks.append(block)
            i += consumed
            continue

        if c.rough_kind == RoughKind.HEADING_CANDIDATE:
            blocks.append(Heading(runs=c.runs, level=2))
            i += 1
            continue

        if c.rough_kind == RoughKind.FOOTNOTE:
            blocks.append(_make_footnote_block(c))
            i += 1
            continue

        text = c.text.strip()
        if looks_like_scene_break(text):
            blocks.append(SceneBreak(marker=text or "•"))
            i += 1
            continue

        if _looks_like_poem(c):
            block, consumed = _make_poem_block(candidates, i)
            blocks.append(block)
            i += consumed
            continue

        if c.block_indented:
            block, consumed = _make_quote_block(candidates, i, is_first=not blocks)
            blocks.append(block)
            i += consumed
            continue

        variant = ParagraphVariant.NORMAL
        if c.starts_with_quote:
            variant = ParagraphVariant.DIALOGUE
        elif _DEAR_SALUTATION_RE.match(text):
            variant = ParagraphVariant.LETTER
        blocks.append(Paragraph(runs=c.runs, variant=variant))
        i += 1

    return blocks


def _make_image_block(candidates: list[ParagraphCandidate], i: int) -> tuple[Block, int]:
    c = candidates[i]
    asset = _make_image_asset(c.image, f"img-{i}")
    caption_runs = []
    consumed = 1
    if i + 1 < len(candidates):
        nxt = candidates[i + 1]
        if (
            nxt.rough_kind == RoughKind.BODY
            and nxt.centered
            and len(nxt.text.strip()) <= _CAPTION_MAX_LEN
        ):
            caption_runs = nxt.runs
            consumed = 2
    alt_text = "".join(r.text for r in caption_runs).strip()[:150]
    return ImageBlock(asset=asset, caption=caption_runs, alt_text=alt_text), consumed


def _make_quote_block(
    candidates: list[ParagraphCandidate], i: int, is_first: bool
) -> tuple[Block, int]:
    c = candidates[i]
    consumed = 1
    attribution = None
    if i + 1 < len(candidates):
        nxt = candidates[i + 1]
        nxt_text = nxt.text.strip()
        if nxt.rough_kind == RoughKind.BODY and _looks_like_attribution(nxt_text):
            attribution = nxt_text.lstrip("—-").strip()
            consumed = 2
    if is_first:
        return Epigraph(runs=c.runs, attribution=attribution), consumed
    return Blockquote(runs=c.runs, attribution=attribution), consumed


def _looks_like_poem(c: ParagraphCandidate) -> bool:
    return len(c.line_groups) >= _POEM_MIN_LINES and c.short_line_fraction >= _POEM_SHORT_LINE_THRESHOLD


def _make_poem_block(candidates: list[ParagraphCandidate], i: int) -> tuple[Block, int]:
    c = candidates[i]
    consumed = 1
    attribution = None
    if i + 1 < len(candidates):
        nxt = candidates[i + 1]
        nxt_text = nxt.text.strip()
        if nxt.rough_kind == RoughKind.BODY and _looks_like_attribution(nxt_text):
            attribution = nxt_text.lstrip("—-").strip()
            consumed = 2
    return Poem(lines=c.line_groups, attribution=attribution), consumed


def _make_footnote_block(c: ParagraphCandidate) -> Block:
    match = _FOOTNOTE_LEADING_RE.match(c.text)
    if match:
        return Footnote(marker=match.group(1), runs=_strip_leading_text(c.runs, match.end()))
    return Footnote(marker="*", runs=c.runs)


def _strip_leading_text(runs: list[Run], n: int) -> list[Run]:
    """Drop the first `n` characters of text across a run list, keeping styling."""
    result: list[Run] = []
    remaining = n
    for r in runs:
        if remaining <= 0:
            result.append(r)
        elif len(r.text) <= remaining:
            remaining -= len(r.text)
        else:
            result.append(
                Run(
                    text=r.text[remaining:], italic=r.italic, bold=r.bold,
                    superscript=r.superscript, footnote_ref=r.footnote_ref,
                )
            )
            remaining = 0
    return result


def _make_image_asset(image, id_prefix: str) -> ImageAsset:
    return ImageAsset(
        id=id_prefix,
        data=image.data,
        mime_type=image.mime_type,
        width=image.width,
        height=image.height,
    )


def _looks_like_attribution(text: str) -> bool:
    return bool(text) and text[0] in "—-" and len(text) <= 80


def _chapter_id_base(draft: _ChapterDraft, idx: int) -> str:
    if draft.kind == ChapterKind.PROLOGUE:
        return "prologue"
    if draft.kind == ChapterKind.EPILOGUE:
        return "epilogue"
    if draft.number:
        return f"chapter-{draft.number}"
    return f"chapter-{idx}"


def _unique_id(base: str, used: set[str]) -> str:
    candidate, n = base, 2
    while candidate in used:
        candidate = f"{base}-{n}"
        n += 1
    used.add(candidate)
    return candidate
