"""Exceptions raised by the cozypdfs conversion pipeline."""

from __future__ import annotations


class CozyPdfsError(Exception):
    """Base class for all pipeline errors."""


class PdfAnalysisError(CozyPdfsError):
    """The PDF could not be opened or parsed.

    Raised for corrupt files, encrypted files without a usable password,
    zero-page documents, or any other condition that makes the input
    unsafe or impossible to analyze. Never lets an underlying parser
    exception (which may include internal paths or memory details) escape
    directly to the caller.
    """


class EmptyDocumentError(PdfAnalysisError):
    """The PDF analyzed successfully but contains no extractable content."""


class EpubGenerationError(CozyPdfsError):
    """The reconstructed Book could not be packaged into a valid EPUB."""


class EpubValidationError(CozyPdfsError):
    """The generated EPUB failed structural or safety validation."""

    def __init__(self, errors: list[str]):
        self.errors = errors
        super().__init__("EPUB failed validation:\n" + "\n".join(f"  - {e}" for e in errors))
