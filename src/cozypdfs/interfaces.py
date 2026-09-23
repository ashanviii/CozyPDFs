"""Protocols for each pipeline stage.

Every stage of the PDF -> EPUB pipeline is defined here as a ``Protocol``
with a single entry point. `pipeline.ConversionPipeline` depends only on
these interfaces, not on concrete implementations -- so, for example, a
future OCR-based analyzer for scanned books can be swapped in for
`PdfAnalyzer` without touching anything downstream.

Two stages are sketched but intentionally not implemented in this phase:
`LibraryStore` and `Reader`. They exist so the pipeline's output shape
(a `Book` plus a validated EPUB file) is already what those future stages
will consume -- without building the UI now.
"""

from __future__ import annotations

from pathlib import Path
from typing import Protocol

from .models import (
    Book,
    DocumentStats,
    LayoutRegion,
    ParagraphCandidate,
    PageLayout,
    RawDocument,
)

ProgressCallback = "Callable[[str, str], None]"  # (stage_name, message) -> None


class PdfAnalyzer(Protocol):
    """Stage 1: PDF file -> raw, geometry-faithful document."""

    def analyze(self, pdf_path: Path) -> RawDocument: ...


class LayoutAnalyzer(Protocol):
    """Stage 2: raw document -> per-page layout regions (classified, columned)."""

    def analyze(self, doc: RawDocument, stats: DocumentStats) -> list[PageLayout]: ...


class ReadingOrderResolver(Protocol):
    """Stage 3: per-page layouts -> a single, document-wide reading sequence."""

    def resolve(self, layouts: list[PageLayout]) -> list[LayoutRegion]: ...


class ArtifactRemover(Protocol):
    """Stage 4: drop repeated running headers/footers/page numbers."""

    def remove(self, regions: list[LayoutRegion]) -> list[LayoutRegion]: ...


class ParagraphReconstructor(Protocol):
    """Stage 5: reading-ordered regions -> reconstructed paragraph candidates."""

    def reconstruct(
        self, regions: list[LayoutRegion], stats: DocumentStats
    ) -> list[ParagraphCandidate]: ...


class StructureEngine(Protocol):
    """Stage 6: paragraph candidates -> the final semantic Book structure."""

    def build(
        self,
        candidates: list[ParagraphCandidate],
        stats: DocumentStats,
        default_title: str,
    ) -> Book: ...


class EpubGenerator(Protocol):
    """Stage 7: Book structure -> a standards-compliant .epub file."""

    def generate(self, book: Book, output_path: Path) -> Path: ...


class ValidationResult(Protocol):
    is_valid: bool
    errors: list[str]
    warnings: list[str]


class EpubValidator(Protocol):
    """Stage 8: structural + safety validation of a generated EPUB."""

    def validate(self, epub_path: Path) -> ValidationResult: ...


class LibraryStore(Protocol):
    """Future stage: persist a converted book so the library UI can list it.

    Not implemented in this phase. Defined so the pipeline's output --
    a Book plus a validated EPUB path -- is already shaped as this stage's
    input.
    """

    def add(self, book: Book, epub_path: Path, source_pdf_path: Path) -> str: ...


class Reader(Protocol):
    """Future stage: render a Book/EPUB for reading.

    Not implemented in this phase. The reader is expected to consume only
    the generated EPUB (or the Book model directly) and to own all
    typography, pagination, and theming decisions itself.
    """

    def open(self, epub_path: Path) -> None: ...
