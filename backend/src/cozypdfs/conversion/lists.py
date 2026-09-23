"""List reconstruction: groups consecutive LIST_ITEM lines (already
detected by classify.py) into one semantic list block, serialized as an
HTML fragment — consistent with how every other block stores `content`
(see dir.schema.Block). Nesting is inferred from left-indentation depth,
capped at two levels: an ambiguous indent jump collapses to the nearest
valid depth rather than inventing a deeper hierarchy than the source
plausibly has.
"""

from cozypdfs.conversion.types import ClassifiedLine

_MAX_NEST_DEPTH = 2
_NEST_INDENT_STEP = 12.0


def build_list_html(items: list[ClassifiedLine]) -> str:
    if not items:
        return "<ul></ul>"

    base_indent = min(item.list_indent for item in items)
    ordered = bool(items[0].list_marker and items[0].list_marker[:1].isdigit())

    entries = [
        (_depth(item.list_indent, base_indent), _strip_marker(item.line.text.strip(), item.list_marker))
        for item in items
    ]
    tree = _build_tree(entries)
    return _render(tree, ordered)


def _depth(indent: float, base_indent: float) -> int:
    return min(max(round((indent - base_indent) / _NEST_INDENT_STEP), 0), _MAX_NEST_DEPTH)


def _build_tree(entries: list[tuple[int, str]]) -> list[dict]:
    root: list[dict] = []
    stack: list[list[dict]] = [root]

    for depth, text in entries:
        while depth + 1 > len(stack):
            if not stack[-1]:
                break
            stack.append(stack[-1][-1].setdefault("children", []))
        while depth + 1 < len(stack):
            stack.pop()
        stack[-1].append({"text": text, "children": []})

    return root


def _render(nodes: list[dict], ordered: bool) -> str:
    tag = "ol" if ordered else "ul"
    parts = [f"<{tag}>"]
    for node in nodes:
        parts.append(f"<li>{_escape(node['text'])}")
        if node["children"]:
            parts.append(_render(node["children"], ordered))
        parts.append("</li>")
    parts.append(f"</{tag}>")
    return "".join(parts)


def _strip_marker(text: str, marker: str | None) -> str:
    if marker and text.startswith(marker):
        return text[len(marker) :].strip()
    return text


def _escape(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
