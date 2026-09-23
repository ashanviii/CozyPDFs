import sys
import tempfile
from pathlib import Path

from cozypdfs.conversion.pipeline import reconstruct_pdf
from cozypdfs.storage.local import LocalDiskStorage

GOLDEN_DIR = Path("tests/golden_pdfs")

names = sys.argv[1:] or [p.stem for p in sorted(GOLDEN_DIR.glob("*.pdf"))]

with tempfile.TemporaryDirectory() as tmp:
    storage = LocalDiskStorage(Path(tmp) / "storage")
    for name in names:
        pdf_path = GOLDEN_DIR / f"{name}.pdf"
        print(f"\n===== {name} =====")
        data = pdf_path.read_bytes()
        try:
            doc = reconstruct_pdf(data, storage=storage, book_id=name, title=None, author=None)
        except Exception as exc:
            print("FAILED:", exc)
            continue
        for chapter in doc.chapters:
            print(f"-- chapter: {chapter.title!r} --")
            for block in chapter.blocks:
                print(f"  [{block.type}] :: {block.content}")
        print("assets:", [(a.id, a.width, a.height) for a in doc.assets])
