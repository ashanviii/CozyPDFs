"""The internal reader artifact: a versioned, DIR-derived representation
that sits between the canonical DIR (Phase 2A) and any consumer that wants
to *render* a book — EPUB export today, a future live reader in Phase 2C.

DIR remains the source of truth. This schema never introduces a new
semantic decision — every block type, heading level, confidence value, and
preservation flag here is copied straight from DIR. What this stage adds is
purely structural: a nested section/navigation hierarchy derived from DIR's
existing heading levels, and figure/caption pairs merged into one unit
(see reader_artifact/build.py) — exactly the two things Phase 2B's brief
calls for, nothing else.

Represents semantic reading content only — never PDF pages or coordinates.
"""

from enum import StrEnum

from pydantic import BaseModel, Field

READER_ARTIFACT_SCHEMA_VERSION = 1


class ReaderBlockType(StrEnum):
    """Mirrors cozypdfs.dir.schema.BlockType. CAPTION is deliberately
    absent — a DIR caption block is merged into the `caption` field of the
    visual block it followed, never emitted as its own reader block (see
    build.py); HEADING blocks at level >= 2 likewise become ReaderSection
    titles rather than blocks. Both still appear here only if a defensive
    fallback keeps one as ordinary content (an orphaned caption, or a
    heading with no level Phase 2A could assign)."""

    PARAGRAPH = "paragraph"
    HEADING = "heading"
    LIST = "list"
    QUOTE = "quote"
    IMAGE = "image"
    TABLE = "table"
    EQUATION = "equation"
    FIGURE = "figure"
    FOOTNOTE = "footnote"


class ReaderAsset(BaseModel):
    """A materialized visual asset. `filename` is deterministic and
    derived from the DIR asset id — never a temporary filesystem path —
    so the same DIR always names its assets the same way."""

    id: str
    filename: str
    media_type: str
    width: int | None = None
    height: int | None = None
    alt_text: str | None = None


class ReaderBlock(BaseModel):
    id: str
    type: ReaderBlockType
    order: int
    content: str
    level: int | None = None
    preserve_as_image: bool = False
    asset_id: str | None = None
    caption: str | None = None
    """Plain text, merged in from a DIR CAPTION block that immediately
    followed this one — see build.py. None if DIR had no such caption."""
    confidence: float = 1.0
    source_page: int | None = None


class ReaderSection(BaseModel):
    """One node of the section/navigation tree. A DIR chapter becomes a
    level-1 section; a HEADING block of level >= 2 inside it becomes a
    nested child section that groups the blocks following it — a direct
    materialization of the hierarchy DIR's heading levels already imply,
    not a new interpretation of structure DIR didn't establish."""

    id: str
    title: str | None = None
    level: int
    blocks: list[ReaderBlock] = Field(default_factory=list)
    children: list["ReaderSection"] = Field(default_factory=list)


class NavigationItem(BaseModel):
    """A lightweight projection of a ReaderSection (id/title/level/children
    only) — built *from* the section tree (see build.py's
    `_build_navigation`), never derived independently, per Phase 2B's
    requirement that navigation and content share one structure."""

    section_id: str
    title: str
    level: int
    children: list["NavigationItem"] = Field(default_factory=list)


class ReaderMeta(BaseModel):
    title: str | None = None
    author: str | None = None
    language: str | None = None
    source_type: str = "pdf"


class ReaderArtifact(BaseModel):
    schema_version: int = READER_ARTIFACT_SCHEMA_VERSION
    book_id: str
    dir_schema_version: int
    """Provenance: which DIR schema version this artifact was derived
    from, so a future schema migration can tell old artifacts apart."""
    meta: ReaderMeta
    sections: list[ReaderSection] = Field(default_factory=list)
    assets: list[ReaderAsset] = Field(default_factory=list)
    navigation: list[NavigationItem] = Field(default_factory=list)
