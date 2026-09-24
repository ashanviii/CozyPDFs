"""Top-level Phase 2B orchestration: DIRDocument -> (ReaderArtifact, EPUB
bytes), with storage-backed asset materialization and validation at both
stages. The counterpart to conversion/pipeline.py for the DIR -> EPUB half
of the pipeline — the only place here that touches StorageBackend; every
function beneath it (reader_artifact/build.py, epub/build.py, epub/xhtml.py)
works on pure in-memory data and never re-runs any Phase 2A decision.
"""

from cozypdfs.dir.schema import DIRDocument
from cozypdfs.epub import validation as epub_validation
from cozypdfs.epub.build import build_epub
from cozypdfs.reader_artifact import validation as reader_artifact_validation
from cozypdfs.reader_artifact.build import derive_reader_artifact
from cozypdfs.reader_artifact.schema import ReaderArtifact
from cozypdfs.storage.base import StorageBackend


class ReaderArtifactPipelineError(Exception):
    pass


def build_reader_artifact_and_epub(
    document: DIRDocument, *, book_id: str, storage: StorageBackend
) -> tuple[ReaderArtifact, bytes]:
    artifact = derive_reader_artifact(document, book_id=book_id)

    issues = reader_artifact_validation.validate(artifact)
    if issues:
        raise ReaderArtifactPipelineError(
            "reader artifact validation failed: " + "; ".join(issue.message for issue in issues)
        )

    asset_storage_keys = {asset.id: asset.storage_key for asset in document.assets}
    epub_bytes = build_epub(artifact, storage=storage, asset_storage_keys=asset_storage_keys)

    epub_issues = epub_validation.validate(epub_bytes)
    if epub_issues:
        raise ReaderArtifactPipelineError(
            "EPUB validation failed: " + "; ".join(issue.message for issue in epub_issues)
        )

    return artifact, epub_bytes
