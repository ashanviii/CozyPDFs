"""The intermediate and semantic document models for the cozypdfs pipeline.

There are three layers, and data only ever flows forward through them:

1. Raw layer (``Raw*``) -- a faithful, geometry-aware transcription of what is
   physically on each PDF page: blocks, lines, spans, fonts, images, with
   bounding boxes in PDF coordinate space. Produced by the PDF analyzer.

2. Layout layer (``LayoutRegion`` / ``PageLayout``) -- the raw blocks
   classified by role (body text, header, footer, page number, heading
   candidate, image) and grouped into columns. Still geometry-aware.

3. Semantic layer (``Book`` / ``Chapter`` / the ``Block`` union) -- the
   reconstructed book, expressed purely in terms of what things *are*
   (a paragraph, a heading, a quote, a scene break) rather than where they
   sat on a page. This is the ONLY layer the EPUB generator is allowed to
   see. It carries no coordinates, no page dimensions, no font sizes -- the
   reader controls all of that.

A fourth, transitional type -- ``ParagraphCandidate`` -- carries a handful of
geometric *signals* (relative font size, boldness, indentation, centering)
forward from the layout layer into semantic classification, without carrying
raw coordinates all the way into the Book model.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path


# ---------------------------------------------------------------------------
# Geometry primitives (raw / layout layers only -- never appear in Book)
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class BBox:
    """Axis-aligned bounding box in PDF page coordinate space (points)."""

    x0: float
    y0: float
    x1: float
    y1: float

    @property
    def width(self) -> float:
        return self.x1 - self.x0

    @property
    def height(self) -> float:
        return self.y1 - self.y0

    @property
    def center_x(self) -> float:
        return (self.x0 + self.x1) / 2

    def union(self, other: "BBox") -> "BBox":
        return BBox(
            min(self.x0, other.x0),
            min(self.y0, other.y0),
            max(self.x1, other.x1),
            max(self.y1, other.y1),
        )


# ---------------------------------------------------------------------------
# Raw layer -- output of the PDF analyzer
# ---------------------------------------------------------------------------


@dataclass(slots=True)
class RawSpan:
    """A run of text with uniform font attributes, as PyMuPDF reports it."""

    text: str
    bbox: BBox
    font_name: str
    font_size: float
    italic: bool
    bold: bool
    superscript: bool
    color: int


@dataclass(slots=True)
class RawLine:
    bbox: BBox
    spans: list[RawSpan] = field(default_factory=list)

    @property
    def text(self) -> str:
        return "".join(s.text for s in self.spans)


class RawBlockType(str, Enum):
    TEXT = "text"
    IMAGE = "image"


@dataclass(slots=True)
class RawImageData:
    bbox: BBox
    data: bytes
    mime_type: str
    width: int
    height: int


@dataclass(slots=True)
class RawBlock:
    bbox: BBox
    block_type: RawBlockType
    lines: list[RawLine] = field(default_factory=list)
    image: RawImageData | None = None


@dataclass(slots=True)
class RawPage:
    index: int
    width: float
    height: float
    blocks: list[RawBlock] = field(default_factory=list)


@dataclass(slots=True)
class RawDocument:
    source_path: Path
    page_count: int
    pages: list[RawPage] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Layout layer -- output of the layout analyzer + reading-order resolver
# ---------------------------------------------------------------------------


class RegionType(str, Enum):
    BODY_TEXT = "body_text"
    HEADING_CANDIDATE = "heading_candidate"
    HEADER = "header"
    FOOTER = "footer"
    PAGE_NUMBER = "page_number"
    IMAGE = "image"
    FOOTNOTE = "footnote"
    WHITESPACE = "whitespace"


@dataclass(slots=True)
class LayoutRegion:
    page_index: int
    block: RawBlock
    region_type: RegionType
    column_index: int = 0


@dataclass(slots=True)
class PageLayout:
    page_index: int
    width: float
    height: float
    regions: list[LayoutRegion] = field(default_factory=list)
    column_count: int = 1


@dataclass(slots=True)
class DocumentStats:
    """Document-wide font statistics used to classify regions and blocks.

    Computed once from the raw document so that "this font is large" can be
    judged relative to *this book's* body text, not an absolute point size.
    """

    body_font_size: float
    max_font_size: float
    page_width: float
    page_height: float


# ---------------------------------------------------------------------------
# Transitional layer -- output of paragraph reconstruction
# ---------------------------------------------------------------------------


class RoughKind(str, Enum):
    """A coarse guess carried forward for the structure engine to refine."""

    BODY = "body"
    HEADING_CANDIDATE = "heading_candidate"
    IMAGE = "image"
    FOOTNOTE = "footnote"


@dataclass(slots=True)
class Run:
    """A run of text with semantic (not visual) styling."""

    text: str
    italic: bool = False
    bold: bool = False
    superscript: bool = False
    subscript: bool = False
    footnote_ref: str | None = None


@dataclass(slots=True)
class ParagraphCandidate:
    """A reconstructed paragraph, not yet classified into a semantic Block.

    Carries forward geometric *signals* (not coordinates) so the structure
    engine can decide what this is without needing raw geometry again.
    """

    runs: list[Run]
    rough_kind: RoughKind
    source_pages: list[int]
    max_font_size: float = 0.0
    avg_font_size: float = 0.0
    bold_fraction: float = 0.0
    centered: bool = False
    indented: bool = False
    block_indented: bool = False
    starts_with_quote: bool = False
    is_all_caps: bool = False
    image: RawImageData | None = None
    # Per-line run groups and the fraction of internal (non-final) lines
    # that end well short of the body's usual right margin -- i.e. lines
    # broken by the author, not by column-width wrapping. High values are
    # the signature of verse: prose almost never breaks a line early
    # except its very last one.
    line_groups: list[list[Run]] = field(default_factory=list)
    short_line_fraction: float = 0.0

    @property
    def text(self) -> str:
        return "".join(r.text for r in self.runs)


# ---------------------------------------------------------------------------
# Semantic layer -- the Book Structure. The ONLY thing the EPUB generator
# is allowed to consume. No coordinates, no page dimensions, no font sizes.
# ---------------------------------------------------------------------------


class BlockKind(str, Enum):
    PARAGRAPH = "paragraph"
    HEADING = "heading"
    BLOCKQUOTE = "blockquote"
    EPIGRAPH = "epigraph"
    SCENE_BREAK = "scene_break"
    IMAGE = "image"
    LIST = "list"
    TABLE = "table"
    EQUATION = "equation"


class ParagraphVariant(str, Enum):
    NORMAL = "normal"
    DIALOGUE = "dialogue"
    LETTER = "letter"
    DIARY = "diary"


@dataclass(slots=True)
class Block:
    """Base class for all semantic block types. Carries no geometry."""


@dataclass(slots=True)
class Paragraph(Block):
    runs: list[Run]
    variant: ParagraphVariant = ParagraphVariant.NORMAL


@dataclass(slots=True)
class Heading(Block):
    runs: list[Run]
    level: int = 1


@dataclass(slots=True)
class Blockquote(Block):
    runs: list[Run]
    attribution: str | None = None


@dataclass(slots=True)
class Epigraph(Block):
    runs: list[Run]
    attribution: str | None = None


@dataclass(slots=True)
class SceneBreak(Block):
    marker: str = "•"


@dataclass(slots=True)
class Footnote(Block):
    """A footnote's own content, placed where it occurred in the flow.

    `marker` is the note's label (e.g. "1", "*") as printed, used to link
    back from the `Run.footnote_ref` that referenced it. Phase 1 only
    isolates already-distinct footnote-shaped blocks (see `layout/regions.py`)
    -- it does not attempt sophisticated footnote/endnote renumbering.
    """

    marker: str
    runs: list[Run] = field(default_factory=list)


@dataclass(slots=True)
class Poem(Block):
    """Verse: line breaks are authored, not column-width wrapping artifacts.

    Unlike `Paragraph`, each inner list in `lines` is rendered as its own
    line (`<br/>`-separated within one block) rather than reflowed --
    that's the one place this pipeline deliberately preserves a PDF line
    break, because for verse the line break *is* semantic content.
    """

    lines: list[list[Run]] = field(default_factory=list)
    attribution: str | None = None


@dataclass(slots=True)
class ImageAsset:
    id: str
    data: bytes
    mime_type: str
    width: int
    height: int


@dataclass(slots=True)
class ImageBlock(Block):
    asset: ImageAsset
    caption: list[Run] = field(default_factory=list)
    alt_text: str = ""


# Future-proofing stubs. Not populated by the phase-1 novel heuristics, but
# defined now so adding table/equation/list support later doesn't require
# reshaping the Book model or the EPUB generator's dispatch.


@dataclass(slots=True)
class ListBlock(Block):
    items: list[list[Run]]
    ordered: bool = False


@dataclass(slots=True)
class TableBlock(Block):
    rows: list[list[list[Run]]]
    header_row: bool = False


@dataclass(slots=True)
class EquationBlock(Block):
    """An equation, preserved rather than reconstructed.

    Per the fidelity-first rule: never rewritten, never approximated, never
    sent through an LLM. If reliable MathML/LaTeX extraction is available
    it is stored; otherwise ``asset`` holds a visual (image) fallback.
    """

    asset: ImageAsset | None = None
    latex: str | None = None
    mathml: str | None = None


class ChapterKind(str, Enum):
    FRONT_MATTER = "front_matter"
    CHAPTER = "chapter"
    PROLOGUE = "prologue"
    EPILOGUE = "epilogue"
    BACK_MATTER = "back_matter"


@dataclass(slots=True)
class Chapter:
    id: str
    title: str | None
    number: str | None
    kind: ChapterKind
    blocks: list[Block] = field(default_factory=list)


@dataclass(slots=True)
class BookMetadata:
    title: str
    author: str | None = None
    language: str = "en"


@dataclass(slots=True)
class Book:
    metadata: BookMetadata
    chapters: list[Chapter] = field(default_factory=list)
    cover: ImageAsset | None = None
