"""Small bbox geometry helpers shared by layout.py and reading_order.py —
both need "is this element inside a detected table region" for a different
purpose (excluding table cells from column-detection candidates, and from
the body-line reading-order stream), so it lives in one place."""

from cozypdfs.conversion.types import BBox


def inside_any(bbox: BBox, containers: list[BBox], tolerance: float = 2.0) -> bool:
    for container in containers:
        if (
            bbox.x0 >= container.x0 - tolerance
            and bbox.x1 <= container.x1 + tolerance
            and bbox.y0 >= container.y0 - tolerance
            and bbox.y1 <= container.y1 + tolerance
        ):
            return True
    return False
