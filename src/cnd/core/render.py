"""Node renderers (docs/adr — rendering as an SDK renderer hierarchy).

Nodes are pure data: no node has a rendering method. Rendering a node to
text is done by a ``NodeRenderer`` — one abstract method per node type plus
a single concrete ``render()`` dispatch over the discriminated union.
``MarkdownRenderer`` is the concrete content renderer; verbosity for
tables/figures is constructor configuration, orthogonal to the format.

"raw" is not a renderer: Pydantic's own ``repr()`` / ``model_dump_json()``
already are the raw representation.

This module is part of the zero-dependency core — it must not import
``rich`` or any other optional extra.
"""

import re
from abc import ABC, abstractmethod

try:  # Python >= 3.11
    from typing import assert_never
except ImportError:  # pragma: no cover — Python 3.10, via pydantic's typing-extensions
    from typing_extensions import assert_never

from cnd.core.markdown_escape import escape_block
from cnd.core.node_text import (
    NodeTextMode,
    format_figure_placeholder,
    header_row_text,
    render_list_markdown,
    render_table_markdown,
    table_node_placeholder,
)
from cnd.core.nodes import (
    CndNode,
    CodeNode,
    FigureNode,
    HeadingNode,
    ImageNode,
    ListNode,
    MathNode,
    ParagraphNode,
    QuoteNode,
    TableNode,
    TermsNode,
)


_BACKTICK_RUN = re.compile(r"`+")
_DEST_NEEDS_BRACKETS = re.compile(r"[ ()<>]")


def _image_destination(path: str) -> str:
    if _DEST_NEEDS_BRACKETS.search(path):
        return "<" + path.replace("<", "%3C").replace(">", "%3E") + ">"
    return path


def _unix_newlines(text: str) -> str:
    return text.replace("\r\n", "\n").replace("\r", "\n")


def _escape_alt(alt: str) -> str:
    return alt.replace("\\", "\\\\").replace("[", "\\[").replace("]", "\\]")


def _fence_for(text: str) -> str:
    """A backtick fence longer than any backtick run inside ``text``.

    CommonMark closes a fenced block on the first line holding a fence at
    least as long as the opening one, so a fixed three-backtick fence lets
    code that itself contains a fence end the block early.
    """
    longest = max((len(m.group()) for m in _BACKTICK_RUN.finditer(text)), default=0)
    return "`" * max(3, longest + 1)


class NodeRenderer(ABC):
    """Renders any ``CndNode`` to text, one method per node type.

    Subclasses implement every ``render_*`` method; ``render()`` is the
    concrete entry point that dispatches on the node's type. The double
    lock: the ABC machinery rejects incomplete subclasses at runtime, and
    ``assert_never`` fails exhaustiveness at type-check when the union
    grows.
    """

    def render(self, node: CndNode) -> str:
        """Dispatch ``node`` to its type-specific ``render_*`` method."""
        match node:
            case HeadingNode():
                return self.render_heading(node)
            case ParagraphNode():
                return self.render_paragraph(node)
            case TableNode():
                return self.render_table(node)
            case QuoteNode():
                return self.render_quote(node)
            case CodeNode():
                return self.render_code(node)
            case MathNode():
                return self.render_math(node)
            case FigureNode():
                return self.render_figure(node)
            case ImageNode():
                return self.render_image(node)
            case ListNode():
                return self.render_list(node)
            case TermsNode():
                return self.render_terms(node)
            case _:
                assert_never(node)

    @abstractmethod
    def render_heading(self, node: HeadingNode) -> str: ...

    @abstractmethod
    def render_paragraph(self, node: ParagraphNode) -> str: ...

    @abstractmethod
    def render_table(self, node: TableNode) -> str: ...

    @abstractmethod
    def render_quote(self, node: QuoteNode) -> str: ...

    @abstractmethod
    def render_code(self, node: CodeNode) -> str: ...

    @abstractmethod
    def render_math(self, node: MathNode) -> str: ...

    @abstractmethod
    def render_figure(self, node: FigureNode) -> str: ...

    @abstractmethod
    def render_image(self, node: ImageNode) -> str: ...

    @abstractmethod
    def render_list(self, node: ListNode) -> str: ...

    @abstractmethod
    def render_terms(self, node: TermsNode) -> str: ...


_CLOSING_HASHES = re.compile(r"(?:^|(?<=[ \t]))(#+)[ \t]*$")


class MarkdownRenderer(NodeRenderer):
    """Render nodes as CommonMark-ish Markdown text.

    ``tables`` and ``figures`` set the verbosity for the two float-like
    node types (docs/proposals/0001):

    - ``"placeholder"`` (default) — a parseable ``[[figure:id ...]]``
      placeholder.
    - ``"inline"`` — always render content (cells / children) as text.
    - ``"auto"`` — defer to the table's ``content_kind`` hint: inline when
      ``"content"``, placeholder when ``"data"`` or unset (never guessed).
      For a figure, ``auto`` looks at the wrapped table's hint.

    Two further flags default to off:

    - ``escape`` — escape free text (paragraphs, headings, list items,
      terms, table cells, figure captions) so it cannot start Markdown
      syntax. Code and math text are never escaped.
    - ``heading_numbers`` — prefix each heading with its ``counter_label``
      and ``number`` when it has them (never escaped).

    Both default to off because plain-text consumers (chunk text,
    embeddings) must not receive backslashes, and heading numbers would
    change their text. ``MarkdownConverter`` turns both on.
    """

    def __init__(
        self,
        *,
        tables: NodeTextMode = "placeholder",
        figures: NodeTextMode = "placeholder",
        escape: bool = False,
        heading_numbers: bool = False,
    ) -> None:
        self.tables = tables
        self.figures = figures
        self.escape = escape
        self.heading_numbers = heading_numbers

    def _text(self, text: str) -> str:
        return escape_block(text) if self.escape else text

    def render_heading(self, node: HeadingNode) -> str:
        text = self._text(node.text)
        if self.escape and (m := _CLOSING_HASHES.search(text)):
            # CommonMark drops a closing "#" sequence from an ATX heading.
            text = f"{text[: m.start(1)]}\\{text[m.start(1):]}"
        if self.heading_numbers:
            prefix = " ".join(p for p in (node.counter_label, node.number) if p)
            if prefix:
                text = f"{prefix} {text}"
        return f"{'#' * node.level} {text}"

    def render_paragraph(self, node: ParagraphNode) -> str:
        return self._text(node.text)

    def render_table(self, node: TableNode) -> str:
        wants_inline = self.tables == "inline" or (
            self.tables == "auto" and node.content_kind == "content"
        )
        if wants_inline:
            rendered = render_table_markdown(
                node, escape=self._text if self.escape else None
            )
            if rendered:
                return rendered
        return table_node_placeholder(node)

    def render_quote(self, node: QuoteNode) -> str:
        lines = self._text(_unix_newlines(node.text)).split("\n")
        if node.attribution:
            attribution = f"— {self._text(_unix_newlines(node.attribution))}"
            lines += ["", *attribution.split("\n")]
        return "\n".join(f"> {line}" if line else ">" for line in lines)

    def render_code(self, node: CodeNode) -> str:
        fence = _fence_for(node.text)
        opening = f"{fence}{node.lang or ''}".rstrip()
        return f"{opening}\n{node.text}\n{fence}"

    def render_math(self, node: MathNode) -> str:
        return node.text

    def render_figure(self, node: FigureNode) -> str:
        wants_inline = self.figures == "inline" or (
            self.figures == "auto"
            and any(
                isinstance(child, TableNode) and child.content_kind == "content"
                for child in node.children
            )
        )
        if wants_inline and node.children:
            parts = [self.render(child) for child in node.children]
            caption_line = self._figure_caption_line(node)
            if caption_line:
                parts.append(caption_line)
            return "\n\n".join(parts)
        if wants_inline and node.raw is None:
            # A figure carrying only raw source is unconvertible content: its
            # placeholder must stay, a bare caption would hide that.
            caption_line = self._figure_caption_line(node)
            if caption_line and (node.caption or node.number):
                return caption_line
        return format_figure_placeholder(
            figure_id=node.id,
            kind=node.kind or self._infer_figure_kind(node),
            caption=node.caption,
            number=node.number,
            header_row=self._figure_header_row(node),
            summary=self._figure_summary(node),
        )

    def render_image(self, node: ImageNode) -> str:
        if node.path:
            return f"![{_escape_alt(node.alt or '')}]({_image_destination(node.path)})"
        if node.alt:
            return f'[[image:{node.id} alt="{node.alt}"]]'
        return f"[[image:{node.id}]]"

    def render_list(self, node: ListNode) -> str:
        return render_list_markdown(
            node.items,
            ordered=node.ordered,
            escape=self._text if self.escape else None,
        )

    def render_terms(self, node: TermsNode) -> str:
        return "\n".join(
            f"**{self._text(item.term)}**\n: {self._text(item.description)}" for item in node.items
        )

    def _figure_caption_line(self, node: FigureNode) -> str | None:
        # Composing "Figure 3" from its parts is the renderer's job, which is
        # why the format keeps them apart (docs/proposals/0010).
        counter = " ".join(
            part for part in (node.counter_label, node.number) if part
        )
        caption = self._text(node.caption) if node.caption else None
        title = ": ".join(part for part in (counter, caption) if part)
        return f"*{title}*" if title else None

    @staticmethod
    def _infer_figure_kind(node: FigureNode) -> str:
        for child in node.children:
            return str(child.type)
        return "figure"

    @staticmethod
    def _figure_header_row(node: FigureNode) -> str | None:
        tables = [child for child in node.children if isinstance(child, TableNode)]
        if len(tables) == 1:
            return header_row_text(tables[0])
        return None

    def _figure_summary(self, node: FigureNode) -> str | None:
        parts = [self._child_summary(child) for child in node.children]
        parts = [part for part in parts if part]
        return "; ".join(parts) if parts else None

    @staticmethod
    def _child_summary(child: CndNode) -> str:
        match child:
            case ImageNode():
                return child.alt or child.path or "image"
            case TableNode():
                return child.kind
            case CodeNode():
                return f"code ({child.lang})" if child.lang else "code"
            case _:
                return str(child.type)
