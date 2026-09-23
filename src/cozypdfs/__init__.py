"""cozypdfs: turn a novel PDF into a clean, reflowable, Kindle-style EPUB.

Public entry point: `ConversionPipeline`. See `models.py` for the document
model and `interfaces.py` for the stage boundaries the pipeline is built
around.
"""

from .exceptions import (
    CozyPdfsError,
    EmptyDocumentError,
    EpubGenerationError,
    EpubValidationError,
    PdfAnalysisError,
)
from .models import Book, BookMetadata, Chapter
from .pipeline import ConversionPipeline, ConversionResult

__all__ = [
    "Book",
    "BookMetadata",
    "Chapter",
    "ConversionPipeline",
    "ConversionResult",
    "CozyPdfsError",
    "EmptyDocumentError",
    "EpubGenerationError",
    "EpubValidationError",
    "PdfAnalysisError",
]
