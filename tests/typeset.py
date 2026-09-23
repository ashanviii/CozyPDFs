"""A small, generic plain-text-to-PDF typesetter.

Not part of the product. This exists purely to turn real public-domain
book text into a realistic test PDF: real word-wrapping (via reportlab's
`stringWidth`, not hand-placed lines), a running header, page-number
footers, and `_word_`-style italic markers (the plain-text convention
Project Gutenberg uses) converted into actual italic spans -- so the
reconstruction pipeline is exercised against genuine prose rather than a
hand-crafted fixture.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from reportlab.lib.pagesizes import LETTER
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.pdfgen import canvas

PAGE_WIDTH, PAGE_HEIGHT = LETTER
MARGIN_LEFT = 90
MARGIN_RIGHT = 90
MAX_WIDTH = PAGE_WIDTH - MARGIN_LEFT - MARGIN_RIGHT
BODY_SIZE = 11
LEADING = 15
INDENT = 18
TOP_START = PAGE_HEIGHT - 130
BOTTOM_LIMIT = 90

FONT_REGULAR = "Times-Roman"
FONT_ITALIC = "Times-Italic"
FONT_BOLD = "Times-Bold"

_ITALIC_RE = re.compile(r"_([^_]+)_")


@dataclass
class Token:
    text: str
    italic: bool
    glue: bool = False  # True: no space before this token (mid-word style change)


def tokenize(text: str) -> list[Token]:
    """Split `text` into style runs, preserving exact word adjacency.

    Splitting on whitespace first (not on the italic markers first) is what
    keeps "_her_." glued as "her" + "." with no inserted space -- the two
    style runs came from one whitespace-delimited word in the source.
    """
    tokens: list[Token] = []
    for word in text.split():
        tokens.extend(_split_word_styles(word))
    return tokens


def _split_word_styles(word: str) -> list[Token]:
    tokens: list[Token] = []
    first = True
    for part in re.split(r"(_[^_]*_)", word):
        if not part:
            continue
        if part.startswith("_") and part.endswith("_") and len(part) >= 2:
            content, italic = part[1:-1], True
        else:
            content, italic = part, False
        if content:
            tokens.append(Token(content, italic, glue=not first))
            first = False
    return tokens


def flow(tokens: list[Token], max_width: float, size: float = BODY_SIZE) -> list[list[Token]]:
    lines: list[list[Token]] = []
    current: list[Token] = []
    width = 0.0
    space_w = stringWidth(" ", FONT_REGULAR, size)
    for tok in tokens:
        font = FONT_ITALIC if tok.italic else FONT_REGULAR
        w = stringWidth(tok.text, font, size)
        extra = space_w if (current and not tok.glue) else 0.0
        if current and not tok.glue and width + extra + w > max_width:
            lines.append(current)
            current, width = [], 0.0
            extra = 0.0
        current.append(tok)
        width += extra + w
    if current:
        lines.append(current)
    return lines


class BookTypesetter:
    def __init__(self, path: Path, header_text: str):
        self.c = canvas.Canvas(str(path), pagesize=LETTER)
        self.header_text = header_text
        self.page_num = 0
        self.y = TOP_START
        self._new_page()

    def save(self) -> None:
        self._draw_footer()
        self.c.save()

    def _new_page(self) -> None:
        if self.page_num > 0:
            self._draw_footer()
            self.c.showPage()
        self.page_num += 1
        self.y = TOP_START
        self.c.setFont(FONT_REGULAR, 9)
        self.c.drawCentredString(PAGE_WIDTH / 2, PAGE_HEIGHT - 40, self.header_text)

    def _draw_footer(self) -> None:
        self.c.setFont(FONT_REGULAR, 9)
        self.c.drawCentredString(PAGE_WIDTH / 2, 40, str(self.page_num))

    def _ensure_space(self, needed: float = LEADING) -> None:
        if self.y - needed < BOTTOM_LIMIT:
            self._new_page()

    def heading(self, text: str) -> None:
        self._ensure_space(60)
        self.c.setFont(FONT_BOLD, 16)
        self.c.drawCentredString(PAGE_WIDTH / 2, self.y, text)
        self.y -= 40

    def paragraph(self, text: str, indent_first: bool = True) -> None:
        tokens = tokenize(text)
        if not tokens:
            return
        width = MAX_WIDTH - INDENT if indent_first else MAX_WIDTH
        lines = flow(tokens, width)
        for i, line_tokens in enumerate(lines):
            self._ensure_space()
            x = MARGIN_LEFT + (INDENT if i == 0 and indent_first else 0)
            self._draw_line(line_tokens, x)
            self.y -= LEADING
        self.y -= LEADING * 0.5

    def _draw_line(self, tokens: list[Token], x: float) -> None:
        cursor = x
        last = len(tokens) - 1
        for i, tok in enumerate(tokens):
            font = FONT_ITALIC if tok.italic else FONT_REGULAR
            self.c.setFont(font, BODY_SIZE)
            next_is_glued = i < last and tokens[i + 1].glue
            text = tok.text if (i == last or next_is_glued) else tok.text + " "
            self.c.drawString(cursor, self.y, text)
            cursor += stringWidth(text, font, BODY_SIZE)
