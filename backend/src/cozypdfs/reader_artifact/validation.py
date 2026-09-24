"""Structural validation of a ReaderArtifact. Pydantic already guarantees
schema validity (types, required fields); this checks the invariants it
can't express: unique ids, in-order blocks, valid asset/navigation
references, and that a table/image block actually carries what its type
promises.
"""

from dataclasses import dataclass

from cozypdfs.reader_artifact.schema import (
    NavigationItem,
    ReaderArtifact,
    ReaderBlockType,
    ReaderSection,
)


class ReaderArtifactValidationError(Exception):
    pass


@dataclass
class ValidationIssue:
    message: str


def validate(artifact: ReaderArtifact) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    asset_ids = {asset.id for asset in artifact.assets}
    seen_block_ids: set[str] = set()
    seen_section_ids: set[str] = set()

    if not artifact.sections:
        issues.append(ValidationIssue("reader artifact has no sections"))

    for section in artifact.sections:
        _walk_section(section, asset_ids, seen_block_ids, seen_section_ids, issues)

    for item in artifact.navigation:
        _walk_navigation(item, seen_section_ids, issues)

    return issues


def _walk_section(
    section: ReaderSection,
    asset_ids: set[str],
    seen_block_ids: set[str],
    seen_section_ids: set[str],
    issues: list[ValidationIssue],
) -> None:
    if section.id in seen_section_ids:
        issues.append(ValidationIssue(f"duplicate section id {section.id!r}"))
    seen_section_ids.add(section.id)

    previous_order: int | None = None
    for block in section.blocks:
        if block.id in seen_block_ids:
            issues.append(ValidationIssue(f"duplicate block id {block.id!r}"))
        seen_block_ids.add(block.id)

        if previous_order is not None and block.order < previous_order:
            issues.append(ValidationIssue(f"block {block.id!r} is out of order in section {section.id!r}"))
        previous_order = block.order

        if not 0.0 <= block.confidence <= 1.0:
            issues.append(ValidationIssue(f"block {block.id!r} has out-of-range confidence {block.confidence}"))

        if block.asset_id and block.asset_id not in asset_ids:
            issues.append(ValidationIssue(f"block {block.id!r} references missing asset {block.asset_id!r}"))

        if block.preserve_as_image and not block.asset_id:
            issues.append(ValidationIssue(f"block {block.id!r} is preserve_as_image without an asset_id"))

        if block.type == ReaderBlockType.TABLE and not block.preserve_as_image and "<table" not in block.content.lower():
            issues.append(ValidationIssue(f"table block {block.id!r} has no <table> content"))

        if not block.preserve_as_image and not block.content.strip():
            issues.append(ValidationIssue(f"block {block.id!r} has no content and is not image-preserved"))

    for child in section.children:
        _walk_section(child, asset_ids, seen_block_ids, seen_section_ids, issues)


def _walk_navigation(item: NavigationItem, section_ids: set[str], issues: list[ValidationIssue]) -> None:
    if item.section_id not in section_ids:
        issues.append(ValidationIssue(f"navigation references missing section {item.section_id!r}"))
    for child in item.children:
        _walk_navigation(child, section_ids, issues)


def validate_or_raise(artifact: ReaderArtifact) -> None:
    issues = validate(artifact)
    if issues:
        raise ReaderArtifactValidationError("; ".join(issue.message for issue in issues))
