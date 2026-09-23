"""The end-to-end conversion pipeline.

Wires the eight stages together purely through the `interfaces` protocols,
so any stage can be swapped later (a different PDF backend, an OCR-based
analyzer for scanned books, a different EPUB packager) without touching
the others. This is also the one place that threads a progress callback
through every stage, so a future upload UI can show "Analyzing your
book... Reconstructing chapters... Building your EPUB..." without any
stage needing to know a UI exists.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from . import debug as debug_dump
from .analysis import PyMuPdfAnalyzer
from .epub import DefaultEpubGenerator, DefaultEpubValidator, ValidationResult
from .exceptions import EpubValidationError
from .interfaces import (
    ArtifactRemover,
    EpubGenerator,
    EpubValidator,
    LayoutAnalyzer,
    ParagraphReconstructor,
    PdfAnalyzer,
    ReadingOrderResolver,
    StructureEngine,
)
from .layout import (
    DefaultLayoutAnalyzer,
    DefaultReadingOrderResolver,
    compute_document_stats,
)
from .models import Book
from .reconstruction import (
    DefaultArtifactRemover,
    DefaultParagraphReconstructor,
    DefaultStructureEngine,
)

ProgressCallback = Callable[[str, str], None]


@dataclass(slots=True)
class ConversionResult:
    book: Book
    epub_path: Path
    validation: ValidationResult


class ConversionPipeline:
    """Orchestrates PDF -> structured document -> EPUB, stage by stage.

    Every dependency defaults to this project's implementation but can be
    overridden -- the pipeline itself only ever calls through the
    `interfaces` protocols, never a concrete class directly.
    """

    def __init__(
        self,
        pdf_analyzer: PdfAnalyzer | None = None,
        layout_analyzer: LayoutAnalyzer | None = None,
        reading_order_resolver: ReadingOrderResolver | None = None,
        artifact_remover: ArtifactRemover | None = None,
        paragraph_reconstructor: ParagraphReconstructor | None = None,
        structure_engine: StructureEngine | None = None,
        epub_generator: EpubGenerator | None = None,
        epub_validator: EpubValidator | None = None,
    ) -> None:
        self.pdf_analyzer = pdf_analyzer or PyMuPdfAnalyzer()
        self.layout_analyzer = layout_analyzer or DefaultLayoutAnalyzer()
        self.reading_order_resolver = reading_order_resolver or DefaultReadingOrderResolver()
        self.artifact_remover = artifact_remover or DefaultArtifactRemover()
        self.paragraph_reconstructor = paragraph_reconstructor or DefaultParagraphReconstructor()
        self.structure_engine = structure_engine or DefaultStructureEngine()
        self.epub_generator = epub_generator or DefaultEpubGenerator()
        self.epub_validator = epub_validator or DefaultEpubValidator()

    def convert(
        self,
        pdf_path: Path,
        output_path: Path,
        *,
        title: str | None = None,
        author: str | None = None,
        on_progress: ProgressCallback | None = None,
        debug_dir: Path | None = None,
    ) -> ConversionResult:
        """Run the full pipeline.

        `debug_dir`, if given, receives a numbered JSON dump of every
        stage's actual output -- raw extraction, layout regions, reading
        order, what artifact removal dropped, paragraph candidates, and
        the final structured Book -- so a wrong paragraph can be traced to
        the exact stage that produced it instead of guessed at. See
        `debug.py`.
        """

        def report(stage: str, message: str) -> None:
            if on_progress is not None:
                on_progress(stage, message)

        pdf_path = Path(pdf_path)
        debug_dir = Path(debug_dir) if debug_dir is not None else None

        report("analyze", "Analyzing your book...")
        raw_doc = self.pdf_analyzer.analyze(pdf_path)
        stats = compute_document_stats(raw_doc)
        if debug_dir:
            debug_dump.dump_raw_document(raw_doc, debug_dir / "01_raw_extraction.json")

        report("layout", "Reading the page layout...")
        layouts = self.layout_analyzer.analyze(raw_doc, stats)
        if debug_dir:
            debug_dump.dump_page_layouts(layouts, debug_dir / "02_layout_regions.json")

        report("reading_order", "Determining reading order...")
        ordered = self.reading_order_resolver.resolve(layouts)
        if debug_dir:
            debug_dump.dump_regions(ordered, debug_dir / "03_reading_order.json")

        report("artifacts", "Removing page numbers and running headers...")
        cleaned = self.artifact_remover.remove(ordered)
        if debug_dir:
            debug_dump.dump_removed_artifacts(
                ordered, cleaned, debug_dir / "04_removed_artifacts.json"
            )

        report("paragraphs", "Reconstructing paragraphs...")
        candidates = self.paragraph_reconstructor.reconstruct(cleaned, stats)
        if debug_dir:
            debug_dump.dump_paragraph_candidates(
                candidates, debug_dir / "05_paragraph_candidates.json"
            )

        report("structure", "Reconstructing chapters...")
        default_title = _default_title(pdf_path)
        book = self.structure_engine.build(candidates, stats, default_title)
        if title:
            book.metadata.title = title
        if author:
            book.metadata.author = author
        if debug_dir:
            debug_dump.dump_book(book, debug_dir / "06_structured_book.json")

        report("epub", "Building your EPUB...")
        epub_path = self.epub_generator.generate(book, Path(output_path))

        report("validate", "Validating your EPUB...")
        validation = self.epub_validator.validate(epub_path)
        if debug_dir:
            debug_dump.dump_validation(validation, debug_dir / "07_validation.json")
        if not validation.is_valid:
            raise EpubValidationError(validation.errors)

        report("done", "Your book is ready.")
        return ConversionResult(book=book, epub_path=epub_path, validation=validation)


def _default_title(pdf_path: Path) -> str:
    cleaned = pdf_path.stem.replace("_", " ").replace("-", " ").strip()
    return cleaned or "Untitled"
