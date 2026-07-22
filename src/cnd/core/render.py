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

from abc import ABC, abstractmethod

try:  # Python >= 3.11
    from typing import assert_never
except ImportError:  # pragma: no cover — Python 3.10, via pydantic's typing-extensions
    from typing_extensions import assert_never

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
    """

    def __init__(
        self,
        *,
        tables: NodeTextMode = "placeholder",
        figures: NodeTextMode = "placeholder",
    ) -> None:
        self.tables = tables
        self.figures = figures

    def render_heading(self, node: HeadingNode) -> str:
        return f"{'#' * node.level} {node.text}"

    def render_paragraph(self, node: ParagraphNode) -> str:
        return node.text

    def render_table(self, node: TableNode) -> str:
        wants_inline = self.tables == "inline" or (
            self.tables == "auto" and node.content_kind == "content"
        )
        if wants_inline:
            rendered = render_table_markdown(node)
            if rendered:
                return rendered
        return table_node_placeholder(node)

    def render_quote(self, node: QuoteNode) -> str:
        if node.attribution:
            return f"{node.text}\n— {node.attribution}"
        return node.text

    def render_code(self, node: CodeNode) -> str:
        fence = f"```{node.lang or ''}".rstrip()
        return f"{fence}\n{node.text}\n```"

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
            return f"![{node.alt or ''}]({node.path})"
        if node.alt:
            return f'[[image:{node.id} alt="{node.alt}"]]'
        return f"[[image:{node.id}]]"

    def render_list(self, node: ListNode) -> str:
        return render_list_markdown(node.items, ordered=node.ordered)

    def render_terms(self, node: TermsNode) -> str:
        return "\n".join(
            f"**{item.term}**\n: {item.description}" for item in node.items
        )

    @staticmethod
    def _figure_caption_line(node: FigureNode) -> str | None:
        title = ": ".join(part for part in (node.number, node.caption) if part)
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
