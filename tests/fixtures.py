"""Builds a synthetic novel PDF as a deterministic test fixture.

Uses low-level canvas drawing (not a text-flow engine) so every line break,
hyphenation point, indentation, header/footer repetition, and cross-page
paragraph split is exactly where the test expects it -- this is what lets
`test_pipeline.py` assert on the *exact* reconstructed text rather than
just "did it not crash."

Layout: a title page, then two chapters covering four content pages,
exercising: multi-line paragraph joining, line-break hyphenation, a
paragraph spanning a page boundary, a scene break, a dialogue paragraph,
a repeated running header + page-number footer (to be stripped as
artifacts), and an inline italic run embedded mid-line.
"""

from __future__ import annotations

from pathlib import Path

from reportlab.lib.pagesizes import LETTER
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.pdfgen import canvas

PAGE_WIDTH, PAGE_HEIGHT = LETTER
BODY_FONT = "Helvetica"
BODY_SIZE = 11
LEADING = 15
LEFT_MARGIN = 90
INDENT = 108
CENTER_X = PAGE_WIDTH / 2

BOOK_TITLE = "The Quiet Harbor"
BOOK_AUTHOR = "Jordan Ashworth"
HEADER_TEXT = "THE QUIET HARBOR"


class _PageBuilder:
    def __init__(self, c: canvas.Canvas):
        self.c = c
        self.y = PAGE_HEIGHT - 130

    def header(self) -> None:
        self.c.setFont(BODY_FONT, 9)
        self.c.drawCentredString(CENTER_X, PAGE_HEIGHT - 40, HEADER_TEXT)
        self.c.setFont(BODY_FONT, BODY_SIZE)

    def footer(self, page_number: int) -> None:
        self.c.setFont(BODY_FONT, 9)
        self.c.drawCentredString(CENTER_X, 40, str(page_number))
        self.c.setFont(BODY_FONT, BODY_SIZE)

    def heading(self, text: str) -> None:
        self.c.setFont("Helvetica-Bold", 18)
        self.c.drawCentredString(CENTER_X, self.y, text)
        self.c.setFont(BODY_FONT, BODY_SIZE)
        self.y -= 40

    def paragraph(self, lines: list[str]) -> None:
        for i, line in enumerate(lines):
            x = INDENT if i == 0 else LEFT_MARGIN
            self.c.setFont(BODY_FONT, BODY_SIZE)
            self.c.drawString(x, self.y, line)
            self.y -= LEADING
        self.y -= LEADING * 0.6  # normal paragraph gap

    def scene_break(self) -> None:
        self.y -= LEADING  # extra whitespace before
        self.c.setFont(BODY_FONT, BODY_SIZE)
        self.c.drawCentredString(CENTER_X, self.y, "* * *")
        self.y -= LEADING * 2.2  # extra whitespace after

    def mixed_paragraph(self, first_line_parts: list[tuple[str, str]], rest: list[str]) -> None:
        x = LEFT_MARGIN
        for text, font in first_line_parts:
            self.c.setFont(font, BODY_SIZE)
            self.c.drawString(x, self.y, text)
            x += stringWidth(text, font, BODY_SIZE)
        self.y -= LEADING
        self.c.setFont(BODY_FONT, BODY_SIZE)
        for line in rest:
            self.c.drawString(LEFT_MARGIN, self.y, line)
            self.y -= LEADING
        self.y -= LEADING * 0.6

    def paragraph_start(self, lines: list[str]) -> None:
        """Like `paragraph`, but leaves no trailing gap -- for text that
        will continue on the next page."""
        for i, line in enumerate(lines):
            x = INDENT if i == 0 else LEFT_MARGIN
            self.c.drawString(x, self.y, line)
            self.y -= LEADING

    def paragraph_continue(self, lines: list[str]) -> None:
        """Continuation of a paragraph_start(), flush-left, no indent."""
        for line in lines:
            self.c.drawString(LEFT_MARGIN, self.y, line)
            self.y -= LEADING
        self.y -= LEADING * 0.6


def build_novel_pdf(path: Path) -> Path:
    c = canvas.Canvas(str(path), pagesize=LETTER)

    # Page 1: title page.
    c.setFont("Helvetica-Bold", 26)
    c.drawCentredString(CENTER_X, 620, BOOK_TITLE)
    c.setFont(BODY_FONT, 14)
    c.drawCentredString(CENTER_X, 580, f"by {BOOK_AUTHOR}")
    c.showPage()

    # Page 2: Chapter One, part 1.
    p = _PageBuilder(c)
    p.header()
    p.heading("CHAPTER ONE")
    p.paragraph([
        "The girl walked into the room and looked around, taking",
        "in the dust that had settled over every surface like a fine",
        "gray snow. Nothing here had moved in years, and the",
        "silence felt almost alive.",
    ])
    p.paragraph([
        "She moved further inside, noticing how the wallpaper had be-",
        "gun to peel away from the corners of the ceiling in long",
        "curling strips.",
    ])
    p.scene_break()
    p.paragraph([
        '"Is anyone there?" she called, her voice swallowed by the',
        "stillness of the house.",
    ])
    p.paragraph_start([
        "She took a step forward, and then another, feeling the old",
    ])
    p.footer(2)
    c.showPage()

    # Page 3: Chapter One, part 2 (paragraph continues from page 2).
    p = _PageBuilder(c)
    p.header()
    p.paragraph_continue([
        "floorboards creak beneath her weight with every movement.",
    ])
    p.paragraph([
        "By the time she reached the far side of the room, her eyes",
        "had adjusted enough to make out shapes in the gloom: a",
        "chair, a shattered mirror, a small wooden box left open on",
        "the table.",
    ])
    p.footer(3)
    c.showPage()

    # Page 4: Chapter Two.
    p = _PageBuilder(c)
    p.header()
    p.heading("CHAPTER TWO")
    p.mixed_paragraph(
        first_line_parts=[
            ("She whispered the word ", BODY_FONT),
            ("impossible", "Helvetica-Oblique"),
            (" and looked away.", BODY_FONT),
        ],
        rest=["No one answered her, of course. No one ever did."],
    )
    p.footer(4)
    c.showPage()

    c.save()
    return path
