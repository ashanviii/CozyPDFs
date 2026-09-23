"""Stage: DIR validation. Structural sanity checks run before a book is
marked ready — catches an assembly bug or a pathological input here rather
than in the reader. Deliberately only checks structural well-formedness
(no dangling asset references, no out-of-range confidence, no empty
content on a non-preserved block) — it has no opinion on reconstruction
*quality*, which is what the golden-output tests are for.
"""

from dataclasses import dataclass

from cozypdfs.dir.schema import DIRDocument


class DIRValidationError(Exception):
    pass


@dataclass
class ValidationIssue:
    message: str


def validate(document: DIRDocument) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    asset_ids = {asset.id for asset in document.assets}
    seen_block_ids: set[str] = set()
    total_blocks = 0

    if not document.chapters:
        issues.append(ValidationIssue("document has no chapters"))

    for chapter in document.chapters:
        for block in chapter.blocks:
            total_blocks += 1

            if block.id in seen_block_ids:
                issues.append(ValidationIssue(f"duplicate block id {block.id!r}"))
            seen_block_ids.add(block.id)

            if not 0.0 <= block.confidence <= 1.0:
                issues.append(
                    ValidationIssue(f"block {block.id} has out-of-range confidence {block.confidence}")
                )

            if block.asset_id and block.asset_id not in asset_ids:
                issues.append(
                    ValidationIssue(f"block {block.id} references missing asset {block.asset_id!r}")
                )

            if block.preserve_as_image and not block.asset_id:
                issues.append(ValidationIssue(f"block {block.id} is preserve_as_image but has no asset_id"))

            if not block.preserve_as_image and not block.content.strip():
                issues.append(ValidationIssue(f"block {block.id} has no content and is not image-preserved"))

    if total_blocks == 0:
        issues.append(ValidationIssue("document has no blocks at all"))

    return issues


def validate_or_raise(document: DIRDocument) -> None:
    issues = validate(document)
    if issues:
        raise DIRValidationError("; ".join(issue.message for issue in issues))
