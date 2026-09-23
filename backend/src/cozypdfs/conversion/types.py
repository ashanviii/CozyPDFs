"""Internal working types for the conversion pipeline. Distinct from the
public DIR schema (cozypdfs.dir.schema) — these are per-stage intermediate
representations that never leave this package; the DIR is assembled from
them only at the very end (see assembly.py).
"""

from dataclasses import dataclass
from enum import StrEnum


@dataclass(frozen=True)
class BBox:
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


@dataclass
class Span:
    text: str
    size: float
    font: str
    bold: bool
    italic: bool
    bbox: BBox


@dataclass
class Line:
    """One visual line of text (PyMuPDF's line granularity, flattened out
    of its own block grouping — paragraph merging is this pipeline's own
    job, not trusted to however PyMuPDF happened to group lines; see
    paragraphs.py)."""

    spans: list[Span]
    bbox: BBox
    page_number: int  # 1-indexed

    @property
    def text(self) -> str:
        return "".join(s.text for s in self.spans)

    @property
    def size(self) -> float:
        if not self.spans:
            return 0.0
        return max(self.spans, key=lambda s: len(s.text)).size

    @property
    def bold(self) -> bool:
        return bool(self.spans) and all(s.bold for s in self.spans)


@dataclass
class RawImage:
    bbox: BBox
    page_number: int
    xref: int  # PyMuPDF image identity — used to detect a repeated/decorative image


@dataclass
class PageContent:
    page_number: int
    width: float
    height: float
    lines: list[Line]
    images: list[RawImage]


class LineRole(StrEnum):
    BODY = "body"
    HEADING = "heading"
    LIST_ITEM = "list_item"
    EQUATION = "equation"
    FOOTNOTE = "footnote"
    HEADER = "header"  # repeated page furniture, top of page — excluded from reading order
    FOOTER = "footer"  # repeated page furniture, bottom of page — excluded from reading order
    PAGE_NUMBER = "page_number"  # excluded from reading order


@dataclass
class ClassifiedLine:
    line: Line
    role: LineRole
    heading_level: int | None = None
    list_marker: str | None = None
    list_indent: float = 0.0


@dataclass
class ColumnBand:
    x0: float
    x1: float


@dataclass
class TableRegion:
    bbox: BBox
    page_number: int
    rows: list[list[str]]
    confidence: float


@dataclass
class PageLayout:
    page_number: int
    width: float
    height: float
    columns: list[ColumnBand]
    classified_lines: list[ClassifiedLine]
    images: list[RawImage]


@dataclass
class LayoutResult:
    pages: list[PageLayout]
    dominant_body_size: float


# --- Ordered, pre-DIR representation -----------------------------------

OrderedItem = ClassifiedLine | RawImage | TableRegion


@dataclass
class PreBlock:
    """Everything needed to build a DIR Block, plus a transient asset
    payload for anything not yet uploaded to storage. `order_hint` is this
    block's position in the fully-resolved reading order — assembly.py
    trusts it completely rather than re-deriving order from geometry."""

    type: str  # cozypdfs.dir.schema.BlockType value
    content: str
    page_number: int
    order_hint: int
    confidence: float = 1.0
    preserve_as_image: bool = False
    level: int | None = None
    asset_bytes: bytes | None = None
    asset_size: tuple[int, int] | None = None
    asset_alt: str | None = None
