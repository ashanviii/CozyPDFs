"""The Document Intermediate Representation (DIR): the canonical model of a
book's content, produced by the conversion pipeline's semantic reconstruction
stage. EPUB, and everything the reader renders, is generated *from* this —
the DIR is the source of truth, not the EPUB file.

Stored as a versioned JSON artifact via StorageBackend (Book.dir_storage_key,
Book.dir_version), not normalized into database rows — the database holds
application state and metadata, not document content. If real usage later
demands per-block queries (search, analytics), a dedicated index can be
built from this artifact without changing its shape.

Deliberately format-agnostic: nothing here assumes the source was a PDF.
A future EPUB-upload path would populate the same DIR via a different,
simpler ingestion stage, and the reader would not need to change.
"""

from enum import StrEnum

from pydantic import BaseModel, Field

DIR_SCHEMA_VERSION = 2


class BlockType(StrEnum):
    PARAGRAPH = "paragraph"
    HEADING = "heading"
    LIST = "list"
    QUOTE = "quote"
    IMAGE = "image"
    TABLE = "table"
    EQUATION = "equation"
    FIGURE = "figure"
    FOOTNOTE = "footnote"
    CAPTION = "caption"


class Sentence(BaseModel):
    """Sentence-level span within a block's content, for future TTS
    word/sentence-sync highlighting."""

    id: str
    char_start: int
    char_end: int


class Block(BaseModel):
    """One reconstructed content unit. `id` is stable across regenerations
    of the same book and is what reading positions, bookmarks, and search
    results anchor to — see the reader locator scheme (chapterId + blockId +
    characterOffset).
    """

    id: str
    type: BlockType
    order: int
    content: str
    confidence: float = 1.0
    preserve_as_image: bool = False
    asset_id: str | None = None
    sentences: list[Sentence] = Field(default_factory=list)

    # Added in schema v2 for the PDF reconstruction pipeline (Phase 2A):
    level: int | None = None
    """Heading hierarchy depth (1 = title/H1, 2 = H2, ...). Only meaningful
    for BlockType.HEADING; None otherwise."""

    source_page: int | None = None
    """The 1-indexed source PDF page this block was reconstructed from —
    provenance for debugging/citations/reprocessing, never a reading
    boundary. A block never spans this field across pages; a paragraph
    that continues across a PDF page break keeps the page it started on."""


class Chapter(BaseModel):
    id: str
    title: str | None = None
    order: int
    blocks: list[Block] = Field(default_factory=list)


class Asset(BaseModel):
    """A rendered/extracted image (a real figure, or a preserved-as-image
    table/equation/diagram region)."""

    id: str
    storage_key: str
    width: int | None = None
    height: int | None = None
    alt_text: str | None = None


class DIRMeta(BaseModel):
    title: str | None = None
    author: str | None = None
    language: str | None = None
    source_type: str = "pdf"


class DIRDocument(BaseModel):
    schema_version: int = DIR_SCHEMA_VERSION
    meta: DIRMeta
    chapters: list[Chapter] = Field(default_factory=list)
    assets: list[Asset] = Field(default_factory=list)
