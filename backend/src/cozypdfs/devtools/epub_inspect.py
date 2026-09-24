"""Developer-only EPUB inspection: extracts a generated .epub (a zip of
XHTML + CSS + images, per the EPUB spec) to a plain directory so its
content documents can be opened directly in a browser. This is a standard,
honest way to inspect what an EPUB actually contains — an EPUB *is* static
XHTML/CSS/images; there is no separate "real" rendering an extract-and-view
step would be unfaithful to. It intentionally does not attempt pagination
or reader chrome — Phase 2B's own stylesheet is what a real EPUB reader
would apply, and that's exactly what this shows.

Usage: `uv run python -m cozypdfs.devtools.epub_inspect <epub-path> <out-dir>`
"""

import io
import sys
import zipfile
from pathlib import Path


def extract_epub(epub_bytes: bytes, output_dir: Path) -> list[str]:
    """Extracts every entry to `output_dir`, preserving the EPUB's own
    internal layout (EPUB/, META-INF/, mimetype), and returns the relative
    paths of every XHTML content document found — the files worth opening
    directly to inspect reading order and semantics."""
    output_dir.mkdir(parents=True, exist_ok=True)
    zf = zipfile.ZipFile(io.BytesIO(epub_bytes))
    zf.extractall(output_dir)

    return sorted(
        name
        for name in zf.namelist()
        if name.endswith((".xhtml", ".html")) and "nav" not in name.lower()
    )


def main() -> None:
    if len(sys.argv) < 3:
        print("usage: python -m cozypdfs.devtools.epub_inspect <epub-path> <out-dir>")
        raise SystemExit(1)

    epub_path = Path(sys.argv[1])
    out_dir = Path(sys.argv[2])

    content_files = extract_epub(epub_path.read_bytes(), out_dir)
    print(f"extracted to {out_dir}")
    print("content documents (open any directly in a browser):")
    for name in content_files:
        print(" ", out_dir / name)
    nav_candidates = [p for p in out_dir.rglob("nav.xhtml")]
    if nav_candidates:
        print("table of contents:", nav_candidates[0])


if __name__ == "__main__":
    main()
