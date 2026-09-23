"""Synthetic PDF builders for the golden reconstruction corpus. Each
function returns raw PDF bytes for one representative document. Built with
PyMuPDF directly (no external assets needed), deliberately keeping text
within realistic column widths and using distinct per-page content where
the reconstruction pipeline is specifically supposed to tell "repeated
furniture" apart from "genuine content that happens to recur near a page
edge" (see layout.py) — an earlier draft of these fixtures used templated
footnote text and PDF-Base14-incompatible Unicode symbols, which produced
misleading test failures caused by the fixtures, not the pipeline; the
lesson is preserved in these generators' choices.

`materialize()` writes every builder's output to a .pdf file on disk under
this directory — the actual "small deterministic test corpus" artifacts,
inspectable independently of the test suite.
"""

from pathlib import Path

import pymupdf

PAGE_WIDTH = 400.0
PAGE_HEIGHT = 600.0


def _page(doc: pymupdf.Document) -> pymupdf.Page:
    return doc.new_page(width=PAGE_WIDTH, height=PAGE_HEIGHT)


def build_single_column_prose() -> bytes:
    """A short two-chapter book: paragraphs that wrap across lines, one
    paragraph deliberately cut off mid-sentence at a page boundary (must
    re-merge into one paragraph) and one that cleanly ends a page right
    before a new chapter (must NOT merge with the next chapter's opening
    line)."""
    doc = pymupdf.open()

    page = _page(doc)
    page.insert_text((50, 50), "Chapter One", fontsize=20, fontname="hebo")
    page.insert_text((50, 90), "It was a bright cold day in the small village, and the", fontsize=11, fontname="helv")
    page.insert_text((50, 105), "clocks were striking thirteen in the town square below.", fontsize=11, fontname="helv")
    page.insert_text((50, 130), "Winston walked quickly through the narrow streets, his", fontsize=11, fontname="helv")
    page.insert_text((50, 145), "collar turned up against the wind that blew that morning.", fontsize=11, fontname="helv")
    # cut off mid-sentence right at the bottom of the page
    page.insert_text((50, 550), "He had almost reached the door when he noticed the", fontsize=11, fontname="helv")

    page = _page(doc)
    # continuation of the mid-sentence paragraph from the previous page
    page.insert_text((50, 50), "sign in the window had been changed overnight.", fontsize=11, fontname="helv")
    page.insert_text((50, 80), "A new paragraph begins here, safely separated by a gap.", fontsize=11, fontname="helv")

    page = _page(doc)
    page.insert_text((50, 50), "Chapter Two", fontsize=20, fontname="hebo")
    page.insert_text((50, 90), "The second chapter opens on an entirely different scene,", fontsize=11, fontname="helv")
    page.insert_text((50, 105), "far from the streets of the first chapter's opening pages.", fontsize=11, fontname="helv")

    return doc.tobytes()


def build_two_column() -> bytes:
    """A two-column article. Column text is deliberately short so it
    stays within its ~140pt column width — the reconstruction pipeline
    must read all of column 1 before any of column 2, never interleaved
    by y-position."""
    doc = pymupdf.open()
    page = _page(doc)
    page.insert_text((50, 50), "Research Notes", fontsize=18, fontname="hebo")

    left_lines = [
        "The first finding of this",
        "study concerns the effect",
        "of temperature on growth.",
        "",
        "A second observation was",
        "made during week three.",
    ]
    right_lines = [
        "The second section covers",
        "methodology used across",
        "all trial sites this year.",
        "",
        "Results are discussed in",
        "the following section.",
    ]
    y = 100
    for line in left_lines:
        if line:
            page.insert_text((50, y), line, fontsize=10, fontname="helv")
        y += 15 if line else 23

    y = 100
    for line in right_lines:
        if line:
            page.insert_text((210, y), line, fontsize=10, fontname="helv")
        y += 15 if line else 23

    return doc.tobytes()


def build_headers_and_page_numbers() -> bytes:
    """Five pages with a running header, a running footer-style page
    number, and unique body content — the header/page number must be
    stripped from the reconstructed content; the body text must survive
    in full."""
    doc = pymupdf.open()
    topics = [
        "the discovery of the ancient manuscript",
        "how the expedition crossed the northern pass",
        "the translation of the first three pages",
        "what the scholars found written in the margins",
        "the journey back to the capital city",
    ]
    for i, topic in enumerate(topics, start=1):
        page = _page(doc)
        page.insert_text((50, 25), "The Reconstruction Journal", fontsize=8, fontname="helv")
        page.insert_text((50, 100), f"This page discusses {topic}", fontsize=10, fontname="helv")
        page.insert_text((50, 115), "in more detail than the previous section allowed.", fontsize=10, fontname="helv")
        page.insert_text((190, 580), str(i), fontsize=8, fontname="helv")
    return doc.tobytes()


def build_footnotes() -> bytes:
    """Four pages, each with body text and a distinct footnote — footnotes
    must be kept (they are document content), even though they sit in the
    same bottom margin band a repeated footer would occupy."""
    doc = pymupdf.open()
    footnotes = [
        "1 Named for the river that borders the estate to the north.",
        "1 A term specific to the regional dialect of the period.",
        "1 See the appendix for the original correspondence.",
        "1 The society's records were lost in the fire of 1889.",
    ]
    for i, footnote in enumerate(footnotes, start=1):
        page = _page(doc)
        page.insert_text((50, 100), f"Body content unique to page {i} continues", fontsize=10, fontname="helv")
        page.insert_text((50, 115), "across this line before the page ends.", fontsize=10, fontname="helv")
        page.insert_text((50, 550), footnote, fontsize=7, fontname="helv")
    return doc.tobytes()


def build_tables() -> bytes:
    """One clean, bordered table (must reconstruct as a real semantic
    table) and one irregular table with a merged header and a missing
    cell (must fall back to a preserved image instead of a garbled
    reconstruction)."""
    doc = pymupdf.open()
    page = _page(doc)
    page.insert_text((50, 40), "Trial Results", fontsize=16, fontname="hebo")
    page.insert_text((50, 70), "The clean summary table below lists every participant.", fontsize=10, fontname="helv")

    x0, y0 = 50, 100
    col_w = [90, 60, 90]
    rows = [["Name", "Age", "Country"], ["John", "24", "India"], ["Sarah", "26", "UK"]]
    for r, row in enumerate(rows):
        x = x0
        for c, cell in enumerate(row):
            rect = pymupdf.Rect(x, y0 + r * 20, x + col_w[c], y0 + (r + 1) * 20)
            page.draw_rect(rect, color=(0, 0, 0), width=0.5)
            page.insert_textbox(rect, cell, fontsize=9, align=1)
            x += col_w[c]
    page.insert_text((50, 172), "Table 1: Participant summary", fontsize=8, fontname="helv")

    page.insert_text((50, 220), "A second, irregular table follows with a merged header.", fontsize=10, fontname="helv")
    x0, y0 = 50, 250
    page.draw_rect(pymupdf.Rect(x0, y0, x0 + 240, y0 + 20), color=(0, 0, 0), width=0.5)
    page.insert_textbox(pymupdf.Rect(x0, y0, x0 + 240, y0 + 20), "Merged wide header", fontsize=9, align=1)
    row2 = [("A", 60), ("", 60), ("C", 120)]
    x = x0
    for text, w in row2:
        rect = pymupdf.Rect(x, y0 + 20, x + w, y0 + 40)
        page.draw_rect(rect, color=(0, 0, 0), width=0.5)
        if text:
            page.insert_textbox(rect, text, fontsize=9, align=1)
        x += w
    row3 = [("1", 80), ("2", 160)]
    x = x0
    for text, w in row3:
        rect = pymupdf.Rect(x, y0 + 40, x + w, y0 + 60)
        page.draw_rect(rect, color=(0, 0, 0), width=0.5)
        page.insert_textbox(rect, text, fontsize=9, align=1)
        x += w

    return doc.tobytes()


def build_equations() -> bytes:
    """A paragraph, an equation-like line, and another paragraph — the
    equation must be preserved as an image; the surrounding prose must
    stay normal reflowable text, not be swallowed or treated as a
    caption."""
    doc = pymupdf.open()
    page = _page(doc)
    page.insert_text((50, 50), "Derivation", fontsize=16, fontname="hebo")
    page.insert_text((50, 90), "Consider a right triangle with legs of length x and y.", fontsize=10, fontname="helv")
    page.insert_text((50, 105), "The relationship between the sides is well known.", fontsize=10, fontname="helv")
    page.insert_text((50, 140), "x^2 + y^2 = z^2", fontsize=11, fontname="helv")
    page.insert_text((50, 175), "This result is attributed to the Pythagorean theorem", fontsize=10, fontname="helv")
    page.insert_text((50, 190), "and holds for any right triangle in the plane.", fontsize=10, fontname="helv")
    return doc.tobytes()


def _solid_pixmap(rgb: tuple[int, int, int], w: int = 100, h: int = 80) -> pymupdf.Pixmap:
    pix = pymupdf.Pixmap(pymupdf.csRGB, pymupdf.IRect(0, 0, w, h))
    pix.set_rect(pix.irect, rgb)
    return pix


def build_figures_with_captions() -> bytes:
    """Two figures, each with an adjacent caption that must stay
    associated with (and ordered right after) its figure."""
    doc = pymupdf.open()
    page = _page(doc)
    page.insert_text((50, 40), "Field Observations", fontsize=16, fontname="hebo")

    page.insert_image(pymupdf.Rect(50, 70, 150, 150), pixmap=_solid_pixmap((80, 140, 200)))
    page.insert_text((50, 165), "Figure 1: Site A under overcast conditions", fontsize=8, fontname="helv")

    page.insert_text((50, 200), "A short paragraph separates the two figures from each other.", fontsize=10, fontname="helv")

    page.insert_image(pymupdf.Rect(50, 230, 150, 310), pixmap=_solid_pixmap((200, 120, 60)))
    page.insert_text((50, 325), "Figure 2: Site B at midday", fontsize=8, fontname="helv")

    return doc.tobytes()


def build_complex_visual() -> bytes:
    """A larger, more detailed synthetic "diagram" — never OCR'd or
    converted to text, always a preserved visual asset, same as any other
    figure but exercising the map/diagram/chart end of the requirement."""
    doc = pymupdf.open()
    page = _page(doc)
    page.insert_text((50, 40), "Regional Overview", fontsize=16, fontname="hebo")
    page.insert_image(pymupdf.Rect(50, 70, 350, 320), pixmap=_solid_pixmap((90, 160, 90), w=300, h=250))
    page.insert_text((50, 335), "Map 1: Survey regions and boundary lines", fontsize=8, fontname="helv")
    return doc.tobytes()


def build_mixed_layout() -> bytes:
    """One page of single-column prose, one two-column page, one page
    with a table, and a final single-column page — the reconstruction
    must interpret each page's local layout correctly while keeping one
    continuous, correctly-ordered document overall."""
    doc = pymupdf.open()

    page = _page(doc)
    page.insert_text((50, 50), "Overview", fontsize=16, fontname="hebo")
    page.insert_text((50, 90), "This first section is ordinary single-column prose that", fontsize=10, fontname="helv")
    page.insert_text((50, 105), "introduces the topic before the layout changes.", fontsize=10, fontname="helv")

    page = _page(doc)
    page.insert_text((50, 50), "Left section line one", fontsize=10, fontname="helv")
    page.insert_text((50, 65), "stays on the left.", fontsize=10, fontname="helv")
    page.insert_text((210, 50), "Right section line one", fontsize=10, fontname="helv")
    page.insert_text((210, 65), "stays on the right.", fontsize=10, fontname="helv")

    page = _page(doc)
    page.insert_text((50, 50), "The following table summarizes the comparison.", fontsize=10, fontname="helv")
    x0, y0 = 50, 80
    col_w = [90, 90]
    rows = [["Metric", "Value"], ["Speed", "42"]]
    for r, row in enumerate(rows):
        x = x0
        for c, cell in enumerate(row):
            rect = pymupdf.Rect(x, y0 + r * 20, x + col_w[c], y0 + (r + 1) * 20)
            page.draw_rect(rect, color=(0, 0, 0), width=0.5)
            page.insert_textbox(rect, cell, fontsize=9, align=1)
            x += col_w[c]

    page = _page(doc)
    page.insert_text((50, 50), "Finally, the document returns to single-column prose", fontsize=10, fontname="helv")
    page.insert_text((50, 65), "to close out the discussion.", fontsize=10, fontname="helv")

    return doc.tobytes()


def build_three_column() -> bytes:
    """Three roughly-equal columns. Reading order must be column 1 in
    full, then column 2, then column 3 — never interleaved by row."""
    doc = pymupdf.open()
    page = _page(doc)
    page.insert_text((40, 40), "Three Column Report", fontsize=14, fontname="hebo")

    columns = [
        (40, ["Alpha section", "line one here.", "Second alpha", "sentence follows."]),
        (155, ["Beta section", "line one here.", "Second beta", "sentence follows."]),
        (270, ["Gamma section", "line one here.", "Second gamma", "sentence follows."]),
    ]
    for x, lines in columns:
        y = 80
        for line in lines:
            page.insert_text((x, y), line, fontsize=9, fontname="helv")
            y += 14

    return doc.tobytes()


def build_uneven_three_column() -> bytes:
    """Three columns of visibly different widths and different amounts of
    content — column widths and per-column line counts must not matter to
    the reading-order algorithm, only the geometry of the gutters."""
    doc = pymupdf.open()
    page = _page(doc)
    page.insert_text((30, 40), "Uneven Columns", fontsize=14, fontname="hebo")

    # narrow left column (short lines only)
    page.insert_text((30, 80), "Narrow col", fontsize=9, fontname="helv")
    page.insert_text((30, 94), "line one.", fontsize=9, fontname="helv")

    # wide middle column (longer lines, more of them)
    mid_lines = [
        "This is the wide middle column",
        "with more lines than the others,",
        "spanning a noticeably larger",
        "share of the page width here.",
    ]
    y = 80
    for line in mid_lines:
        page.insert_text((100, y), line, fontsize=9, fontname="helv")
        y += 14

    # medium right column
    page.insert_text((300, 80), "Right column", fontsize=9, fontname="helv")
    page.insert_text((300, 94), "has two lines", fontsize=9, fontname="helv")
    page.insert_text((300, 108), "of its own.", fontsize=9, fontname="helv")

    return doc.tobytes()


def build_mixed_column_counts() -> bytes:
    """Page 1 is single-column, page 2 is two-column, page 3 is
    three-column — the algorithm must decide independently per page
    rather than assuming one layout for the whole document."""
    doc = pymupdf.open()

    page = _page(doc)
    page.insert_text((50, 50), "Section A (one column)", fontsize=12, fontname="hebo")
    page.insert_text((50, 90), "This page is ordinary single-column prose", fontsize=10, fontname="helv")
    page.insert_text((50, 105), "with nothing unusual about its layout.", fontsize=10, fontname="helv")

    page = _page(doc)
    page.insert_text((50, 50), "Section B (two columns)", fontsize=12, fontname="hebo")
    page.insert_text((50, 90), "Left half line one", fontsize=10, fontname="helv")
    page.insert_text((50, 105), "left half line two.", fontsize=10, fontname="helv")
    page.insert_text((210, 90), "Right half line one", fontsize=10, fontname="helv")
    page.insert_text((210, 105), "right half line two.", fontsize=10, fontname="helv")

    page = _page(doc)
    page.insert_text((50, 50), "Section C (three columns)", fontsize=12, fontname="hebo")
    for x, label in [(40, "First"), (155, "Second"), (270, "Third")]:
        page.insert_text((x, 90), f"{label} col line one", fontsize=10, fontname="helv")
        page.insert_text((x, 105), f"{label} col line two.", fontsize=10, fontname="helv")

    return doc.tobytes()


def build_realistic_book_excerpt() -> bytes:
    """A longer, more natural multi-paragraph excerpt (original prose, not
    reproduced from any copyrighted source) — meant for a more convincing
    "does this actually read naturally top-to-bottom" visual check than
    the minimal single_column_prose fixture."""
    doc = pymupdf.open()

    page = _page(doc)
    page.insert_text((50, 50), "The Lighthouse Keeper", fontsize=18, fontname="hebo")
    paras = [
        [
            "Mara had kept the light for eleven winters, and in that time she had",
            "learned to read the weather the way other people read faces. A change",
            "in the wind before dawn meant fog by noon; a certain stillness in the",
            "gulls meant a storm was still two days off, gathering its strength",
            "somewhere past the horizon she could not see.",
        ],
        [
            "Tonight the stillness was wrong. She stood at the gallery rail long",
            "after the lamp had caught, watching the dark water for a shape that",
            "would not resolve itself into a wave or a rock or anything she had",
            "a name for.",
        ],
    ]
    y = 90
    for para in paras:
        for line in para:
            page.insert_text((50, y), line, fontsize=10, fontname="helv")
            y += 14
        y += 12

    page = _page(doc)
    paras2 = [
        [
            "By the time the sun came up she had convinced herself it was nothing,",
            "the way she convinced herself of a great many things that winter. The",
            "supply boat was not due for another eleven days, and the radio had",
            "been silent since Tuesday, which was not unusual and which she chose",
            "not to think about too closely.",
        ],
        [
            "She made coffee. She wound the clockwork that turned the lens. She",
            "wrote the night's weather in the log in her small, careful hand, the",
            "same hand she had used for eleven years, and if it shook slightly",
            "this morning she did not write that down.",
        ],
    ]
    y = 60
    for para in paras2:
        for line in para:
            page.insert_text((50, y), line, fontsize=10, fontname="helv")
            y += 14
        y += 12

    return doc.tobytes()


def build_difficult() -> bytes:
    """A deliberately awkward document: a three-way-ish column split that
    should safely fall back to single-flow reading order rather than
    interleave, a nearly-empty page, and content packed with very little
    separating whitespace between a heading, a list, and a table."""
    doc = pymupdf.open()

    # three-ish columns on one page -> ambiguous, must fall back to
    # single-flow rather than guess a column split.
    page = _page(doc)
    page.insert_text((50, 100), "colA line one", fontsize=10, fontname="helv")
    page.insert_text((160, 100), "colB line one", fontsize=10, fontname="helv")
    page.insert_text((270, 100), "colC line one", fontsize=10, fontname="helv")
    page.insert_text((50, 115), "colA line two", fontsize=10, fontname="helv")
    page.insert_text((160, 115), "colB line two", fontsize=10, fontname="helv")
    page.insert_text((270, 115), "colC line two", fontsize=10, fontname="helv")

    # a genuinely empty page — the pipeline must not crash on it
    _page(doc)

    # tightly packed heading + list + table
    page = _page(doc)
    page.insert_text((50, 50), "Summary", fontsize=16, fontname="hebo")
    page.insert_text((50, 80), "- first point", fontsize=10, fontname="helv")
    page.insert_text((50, 94), "- second point", fontsize=10, fontname="helv")
    x0, y0 = 50, 115
    col_w = [90, 90]
    for r, row in enumerate([["X", "Y"], ["1", "2"]]):
        x = x0
        for c, cell in enumerate(row):
            rect = pymupdf.Rect(x, y0 + r * 18, x + col_w[c], y0 + (r + 1) * 18)
            page.draw_rect(rect, color=(0, 0, 0), width=0.5)
            page.insert_textbox(rect, cell, fontsize=8, align=1)
            x += col_w[c]

    return doc.tobytes()


BUILDERS = {
    "single_column_prose": build_single_column_prose,
    "two_column": build_two_column,
    "headers_and_page_numbers": build_headers_and_page_numbers,
    "footnotes": build_footnotes,
    "tables": build_tables,
    "equations": build_equations,
    "figures_with_captions": build_figures_with_captions,
    "complex_visual": build_complex_visual,
    "mixed_layout": build_mixed_layout,
    "difficult": build_difficult,
    "three_column": build_three_column,
    "uneven_three_column": build_uneven_three_column,
    "mixed_column_counts": build_mixed_column_counts,
    "realistic_book_excerpt": build_realistic_book_excerpt,
}


def materialize(directory: Path | None = None) -> None:
    target = directory or Path(__file__).parent
    target.mkdir(parents=True, exist_ok=True)
    for name, builder in BUILDERS.items():
        (target / f"{name}.pdf").write_bytes(builder())


if __name__ == "__main__":
    materialize()
