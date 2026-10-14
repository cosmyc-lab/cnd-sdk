"""Small constructors shared by the 0.5 test modules."""

from uuid import uuid4

from cnd.core.nodes import Cell, ListItem, ParagraphNode
from cnd.core.text import RichText


def rt(value: str, **kwargs) -> RichText:
    """A RichText from a string, the shorthand every test needs."""
    return RichText(value=value, **kwargs)


def para(text: "str | RichText" = "p", **kwargs) -> ParagraphNode:
    """A paragraph with a fresh id; a string becomes its RichText."""
    if isinstance(text, str):
        text = rt(text)
    return ParagraphNode(type="paragraph", id=uuid4(), text=text, **kwargs)


def cell(row: int, col: int, text: str | None = None, **kwargs) -> Cell:
    """A table or layout cell; ``text`` becomes its one paragraph."""
    if text is not None:
        kwargs.setdefault("children", [para(text)])
    return Cell(row=row, col=col, **kwargs)


def item(*children, **kwargs) -> ListItem:
    """A list item; string children become paragraphs."""
    nodes = [para(child) if isinstance(child, str) else child for child in children]
    return ListItem(children=nodes, **kwargs)
