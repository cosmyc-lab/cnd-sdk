"""Node renderers (docs/adr — rendering as an SDK renderer hierarchy).

Nodes are pure data: no node has a rendering method. Rendering a node to
text is done by a ``NodeRenderer`` — one abstract method per node type plus
a single concrete ``render()`` dispatch over the discriminated union.
``MarkdownRenderer`` is the concrete content renderer; verbosity for
tables/figures is constructor configuration, orthogonal to the format.
Every renderer renders the prose of a node (a ``RichText``) through
``render_text``, which goes through the one inline layer,
``cnd.core.inline``.

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

from cnd.core.inline import concat_texts, render_inline, with_whole_mark
from cnd.core.markdown_escape import escape_block
from cnd.core.node_text import (
    NodeTextMode,
    cell_plain_text,
    format_figure_placeholder,
    header_row_text,
    header_rows,
    is_inline_cell,
    render_table_markdown,
    row_labels_text,
    table_node_placeholder,
    table_shape,
    wants_inline_table,
)
from cnd.core.nodes import (
    KNOWN_ADMONITION_KINDS,
    AdmonitionNode,
    Cell,
    CndNode,
    CodeNode,
    FigureNode,
    HeadingNode,
    ImageNode,
    LayoutNode,
    ListNode,
    MathNode,
    ParagraphNode,
    QuoteNode,
    TableNode,
    TermsNode,
)
from cnd.core.text import RichText


_DEST_NEEDS_BRACKETS = re.compile(r"[ ()<>]")


def _image_destination(path: str) -> str:
    if _DEST_NEEDS_BRACKETS.search(path):
        return "<" + path.replace("<", "%3C").replace(">", "%3E") + ">"
    return path


def _unix_newlines(text: str) -> str:
    return text.replace("\r\n", "\n").replace("\r", "\n")


_ALT_ESCAPE = re.compile(r"\\(?=[!-/:-@\[-`{-~]|\Z)|[\[\]]")


def _escape_alt(alt: str) -> str:
    """Escape ``[``/``]``; double a backslash only where it would escape
    something (before ASCII punctuation or at the end), as escape_inline does."""
    return _ALT_ESCAPE.sub(lambda m: "\\\\" if m.group() == "\\" else "\\" + m.group(), alt)


_BACKTICK_RUN = re.compile(r"`+")


def _fence_for(text: str) -> str:
    """A backtick fence longer than any backtick run inside ``text``.

    CommonMark closes a fenced block on the first line holding a fence at
    least as long as the opening one, so a fixed three-backtick fence lets
    code that itself contains a fence end the block early.
    """
    longest = max((len(m.group()) for m in _BACKTICK_RUN.finditer(text)), default=0)
    return "`" * max(3, longest + 1)


def _prefixed(lines: list[str], marker: str) -> str:
    """Prefix every line (``"> "``, or ``">"`` on a blank line)."""
    return "\n".join(f"{marker} {line}" if line else marker for line in lines)


def _indented(text: str, first: str, indent: str) -> str:
    """``first`` before the first line, ``indent`` before every other
    non-blank line: how a list item or a definition holds its blocks."""
    lines = text.split("\n")
    head = f"{first}{lines[0]}".rstrip()
    rest = [f"{indent}{line}" if line else "" for line in lines[1:]]
    return "\n".join([head, *rest])


def expand_headings(nodes: list[CndNode]) -> list[CndNode]:
    """``nodes`` with every heading followed by its section, recursively,
    in pre-order.

    A renderer emits only the line of a heading; the converters' body walk
    visits the section under it. A heading nested in a container (a quote,
    an item, a cell, a figure) or held by a footnote is not on that walk,
    so whatever renders the container's or the footnote's blocks renders
    this list instead of the raw children, or the section would be lost.
    """
    out: list[CndNode] = []
    for node in nodes:
        out.append(node)
        if isinstance(node, HeadingNode):
            out.extend(expand_headings(node.children))
    return out


def _is_one_inline_block(nodes: list[CndNode]) -> bool:
    """Whether ``nodes`` is at most one paragraph or image: content a
    tight sibling can follow on the next line. After any other block (a
    quote, a list, a fence) the next line could continue that block, so
    a blank line has to separate them."""
    expanded = expand_headings(nodes)
    return not expanded or (
        len(expanded) == 1 and isinstance(expanded[0], (ParagraphNode, ImageNode))
    )


def _is_loose(blocks_per_item: list[list[CndNode]]) -> bool:
    """A list is tight unless an item holds several blocks. A nested list
    does not count: ``1. Parent`` over a nested list stays tight, as in
    CommonMark (docs/proposals/0013, "Lists and terms hold blocks")."""
    return any(
        sum(not isinstance(node, ListNode) for node in expand_headings(nodes)) > 1
        for nodes in blocks_per_item
    )


class NodeRenderer(ABC):
    """Renders any ``CndNode`` to text, one method per node type.

    Subclasses implement every ``render_*`` method and ``render_text``;
    ``render()`` is the concrete entry point that dispatches on the node's
    type. The double lock: the ABC machinery rejects incomplete subclasses
    at runtime, and ``assert_never`` fails exhaustiveness at type-check
    when the union grows.
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
            case AdmonitionNode():
                return self.render_admonition(node)
            case LayoutNode():
                return self.render_layout(node)
            case _:
                assert_never(node)

    @abstractmethod
    def render_text(self, text: RichText) -> str:
        """Render one rich text (a paragraph's text, a caption, a term…)."""

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

    @abstractmethod
    def render_admonition(self, node: AdmonitionNode) -> str: ...

    @abstractmethod
    def render_layout(self, node: LayoutNode) -> str: ...


_CLOSING_HASHES = re.compile(r"(?:^|(?<=[ \t]))(#+)[ \t]*$")


class MarkdownRenderer(NodeRenderer):
    """Render nodes as CommonMark + GFM Markdown text.

    A container renders its nested nodes itself (a list its items' blocks,
    a table its cells', a quote its children), so a caller renders the
    top of a subtree once and never its descendants again.

    ``tables`` and ``figures`` set the verbosity for the two float-like
    node types (docs/proposals/0001):

    - ``"placeholder"`` (default) — a parseable ``[[figure:id ...]]``
      placeholder.
    - ``"inline"`` — always render content (cells / children) as text.
    - ``"auto"`` — defer to the table's ``kind``: inline when
      ``"content"``, placeholder when ``"data"``, unset or unknown (never
      guessed). For a figure, ``auto`` looks at the wrapped tables.

    A ``layout`` is not a table: it is always flattened, cell contents in
    reading order.

    Three further flags default to off:

    - ``escape`` — escape free text (every rich text, image alt aside) so
      it cannot start Markdown syntax. Code and math are never escaped.
    - ``heading_numbers`` — prefix each heading with its numbering
      (``name`` and ``value``, never escaped).
    - ``text_only`` — no HTML in the output: the ``sup``, ``sub``,
      ``underline`` and ``highlight`` marks render as plain text, a mark
      Markdown cannot delimit at its position is dropped instead of
      becoming an HTML tag, a table whose cells hold blocks becomes
      linearized rows instead of an HTML table, and a line break in a
      table cell becomes a space instead of ``<br>``.

    ``escape`` and ``heading_numbers`` default to off because plain-text
    consumers (chunk text, embeddings) must not receive backslashes, and
    heading numbers would change their text. ``MarkdownConverter`` turns
    both on.
    """

    def __init__(
        self,
        *,
        tables: NodeTextMode = "placeholder",
        figures: NodeTextMode = "placeholder",
        escape: bool = False,
        heading_numbers: bool = False,
        text_only: bool = False,
    ) -> None:
        self.tables = tables
        self.figures = figures
        self.escape = escape
        self.heading_numbers = heading_numbers
        self.text_only = text_only

    def render_text(self, text: RichText) -> str:
        return render_inline(text, "markdown", escape=self.escape, text_only=self.text_only)

    def _plain(self, text: str) -> str:
        """A plain string (a kind, a title, a column header) as Markdown."""
        return escape_block(text) if self.escape else text

    def _blocks(self, nodes: list[CndNode], separator: str = "\n\n") -> str:
        rendered = (self.render(node).strip("\n") for node in expand_headings(nodes))
        return separator.join(block for block in rendered if block)

    def _prefixed_blocks(self, nodes: list[CndNode], prefix: str, separator: str = "\n\n") -> str:
        """``nodes`` rendered as blocks behind an inline ``prefix`` (a
        definition's ``: ``, a task item's ``[ ] ``, a row's ``Label: ``).

        The prefix shares the first line with a paragraph or an image. Any
        other first block (a fence, a list, a quote, a table, a heading)
        only parses at the start of a line, so the prefix stands on a line
        of its own and the blocks start on the next one; the caller indents
        that line to the content column like the others.
        """
        content = self._blocks(nodes, separator)
        if not content:
            return ""
        if not prefix:
            return content
        first = next(
            (node for node in expand_headings(nodes) if self.render(node).strip("\n")), None
        )
        if isinstance(first, (ParagraphNode, ImageNode)):
            return f"{prefix}{content}"
        return f"{prefix.rstrip()}\n{content}"

    def render_heading(self, node: HeadingNode) -> str:
        text = self.render_text(node.text)
        if self.escape and (m := _CLOSING_HASHES.search(text)):
            # CommonMark drops a closing "#" sequence from an ATX heading.
            text = f"{text[: m.start(1)]}\\{text[m.start(1):]}"
        if self.heading_numbers and node.numbering is not None:
            prefix = " ".join(p for p in (node.numbering.name, node.numbering.value) if p)
            text = f"{prefix} {text}"
        return f"{'#' * node.level} {text}"

    def render_paragraph(self, node: ParagraphNode) -> str:
        return self.render_text(node.text)

    def render_quote(self, node: QuoteNode) -> str:
        body = _unix_newlines(self._blocks(node.children))
        lines = body.split("\n") if body else []
        if node.attribution is not None:
            attribution = f"— {_unix_newlines(self.render_text(node.attribution))}"
            lines += ["", *attribution.split("\n")] if lines else attribution.split("\n")
        return _prefixed(lines or [""], ">")

    def render_admonition(self, node: AdmonitionNode) -> str:
        """A known kind is a GFM alert (``> [!WARNING]``), its title a bold
        line under the marker. An unknown kind is a quote whose first line
        is the title in bold, or the kind when there is no title."""
        title = (
            self.render_text(with_whole_mark(node.title, "strong"))
            if node.title is not None
            else None
        )
        if node.kind in KNOWN_ADMONITION_KINDS:
            head = [f"[!{node.kind.upper()}]"] + ([title] if title else [])
        else:
            head = [title or self.render_text(with_whole_mark(RichText(value=node.kind), "strong"))]
        body = _unix_newlines(self._blocks(node.children))
        lines = _unix_newlines("\n".join(head)).split("\n")
        if body:
            lines += ["", *body.split("\n")]
        return _prefixed(lines, ">")

    def render_code(self, node: CodeNode) -> str:
        fence = _fence_for(node.text)
        opening = f"{fence}{node.lang or ''}".rstrip()
        # The closing fence goes on a line of its own: a text that already
        # ends in a newline would otherwise gain a blank line in the block.
        text = node.text[:-1] if node.text.endswith("\n") else node.text
        block = f"{opening}\n{text}\n{fence}"
        if node.title:
            title = " ".join(_unix_newlines(node.title).split("\n"))
            return f"{self._plain(title)}\n{block}"
        return block

    def render_math(self, node: MathNode) -> str:
        return node.text

    def render_image(self, node: ImageNode) -> str:
        if node.path:
            return f"![{_escape_alt(node.alt or '')}]({_image_destination(node.path)})"
        if node.alt:
            return f'[[image:{node.id} alt="{node.alt}"]]'
        return f"[[image:{node.id}]]"

    def render_list(self, node: ListNode) -> str:
        """Bullets or numbers; ``checked`` adds ``[x]``/``[ ]``. An ordered
        item prints its own ``number`` when the producer set one (a list
        that starts at 5, or skips values), else its position. An item's
        blocks start at its content column, so the indent grows with the
        marker (``- `` is 2, ``1. `` is 3, ``10. `` is 4)."""
        loose = _is_loose([item.children for item in node.items])
        separator = "\n\n" if loose else "\n"
        out: list[str] = []
        for index, item in enumerate(node.items, start=1):
            number = item.number if item.number is not None else index
            marker = f"{number}." if node.ordered else "-"
            box = "" if item.checked is None else ("[x] " if item.checked else "[ ] ")
            content = self._prefixed_blocks(item.children, box, "\n\n" if loose else "\n")
            out.append(_indented(content, f"{marker} ", " " * (len(marker) + 1)))
        return separator.join(out)

    def render_terms(self, node: TermsNode) -> str:
        """``**term**`` then ``: definition``; a definition's further
        blocks are indented under it."""
        loose = any(not _is_one_inline_block(item.children) for item in node.items)
        out: list[str] = []
        for item in node.items:
            term = self.render_text(with_whole_mark(item.term, "strong"))
            definition = self._prefixed_blocks(item.children, ": ")
            if definition:
                term = f"{term}\n{_indented(definition, '', '  ')}"
            out.append(term)
        return ("\n\n" if loose else "\n").join(out)

    def render_layout(self, node: LayoutNode) -> str:
        cells = sorted(node.cells, key=lambda cell: (cell.row, cell.col))
        return self._blocks([child for cell in cells for child in cell.children])

    def render_table(self, node: TableNode) -> str:
        if not wants_inline_table(node, self.tables) or not node.cells:
            return table_node_placeholder(node)
        if all(is_inline_cell(cell) for cell in node.cells):
            return render_table_markdown(node, cell_text=self._gfm_cell, text_only=self.text_only)
        if self.text_only:
            return self._linear_rows(node)
        return self._html_table(node)

    def _gfm_cell(self, cell: Cell) -> str:
        return self.render(cell.children[0]) if cell.children else ""

    def _html_table(self, node: TableNode) -> str:
        """A table whose cells hold blocks, as one HTML block.

        Markdown is not parsed inside an HTML block and a blank line ends
        it, so the cells are rendered as HTML and every newline becomes
        ``&#10;``, which keeps a ``<pre>`` intact. The import is local
        because ``HtmlNodeRenderer`` lives with its converter: moving it
        into the core is a spec §7 decision (see ``cnd.converters.html``).
        """
        from cnd.converters.html import HtmlNodeRenderer

        # The converter already appends every link to the marker line.
        return HtmlNodeRenderer(links=False).render_table(node).replace("\n", "&#10;")

    def _linear_rows(self, node: TableNode) -> str:
        """Under ``text_only``, a table whose cells hold blocks becomes one
        bullet per body row; each cell's blocks follow its column header
        (``Header: …``)."""
        skipped = header_rows(node)
        body = sorted({cell.row for cell in node.cells} - skipped)
        labels: dict[int, str] = {}
        if body and skipped:
            top = min(skipped)
            for cell in node.cells:
                if cell.row == top:
                    for col in range(cell.col, cell.col + max(cell.colspan, 1)):
                        labels[col] = cell_plain_text(cell)
        else:
            body = sorted({cell.row for cell in node.cells})
        rows: list[list[list[CndNode]]] = []
        out: list[str] = []
        for row in body:
            cells = sorted((c for c in node.cells if c.row == row), key=lambda c: c.col)
            rows.append([expand_headings(cell.children) for cell in cells])
            parts: list[str] = []
            for cell in cells:
                label = labels.get(cell.col)
                prefix = f"{self._plain(label)}: " if label else ""
                content = self._prefixed_blocks(cell.children, prefix)
                if not content:
                    continue
                parts.append(content)
            several = any(not _is_one_inline_block(children) for children in rows[-1])
            out.append(_indented(("\n\n" if several else "\n").join(parts), "- ", "  "))
        loose = any(not _is_one_inline_block(children) for cells in rows for children in cells)
        return ("\n\n" if loose else "\n").join(out)

    def render_figure(self, node: FigureNode) -> str:
        wants_inline = self.figures == "inline" or (
            self.figures == "auto"
            and any(
                isinstance(child, TableNode) and child.kind == "content"
                for child in node.children
            )
        )
        if wants_inline and node.children:
            parts = [self.render(child) for child in expand_headings(node.children)]
            parts += self._figure_caption_parts(node)
            return "\n\n".join(part for part in parts if part)
        if wants_inline and node.raw is None and (node.caption or node.numbering):
            # A figure carrying only raw source is unconvertible content: its
            # placeholder must stay, a bare caption would hide that.
            return "\n\n".join(self._figure_caption_parts(node))
        table = self._figure_table(node)
        numbering = node.numbering
        return format_figure_placeholder(
            figure_id=node.id,
            kind=node.kind or self._infer_figure_kind(node),
            caption=node.caption.value if node.caption else None,
            description=node.description.value if node.description else None,
            number=numbering.value if numbering else None,
            counter_label=numbering.name if numbering else None,
            table_kind=table.kind if table else None,
            header_row=header_row_text(table) if table else None,
            shape=table_shape(table) if table else None,
            row_labels=row_labels_text(table) if table else None,
            summary=self._figure_summary(node),
        )

    def _figure_caption_parts(self, node: FigureNode) -> list[str]:
        """The caption line (``*Figure 3: caption*``), then the description
        as a paragraph (docs/proposals/0013, "Figures")."""
        # Composing "Figure 3" from its parts is the renderer's job, which is
        # why the format keeps them apart (docs/proposals/0010).
        numbering = node.numbering
        counter = (
            " ".join(p for p in (numbering.name, numbering.value) if p) if numbering else ""
        )
        separator = ": " if counter and node.caption else ""
        title = concat_texts(counter, separator, node.caption)
        parts: list[str] = []
        if title.value:
            parts.append(self.render_text(with_whole_mark(title, "emph")))
        if node.description is not None:
            parts.append(self.render_text(node.description))
        return parts

    @staticmethod
    def _infer_figure_kind(node: FigureNode) -> str:
        for child in node.children:
            return str(child.type)
        return "figure"

    @staticmethod
    def _figure_table(node: FigureNode) -> TableNode | None:
        tables = [child for child in node.children if isinstance(child, TableNode)]
        return tables[0] if len(tables) == 1 else None

    def _figure_summary(self, node: FigureNode) -> str | None:
        parts = [self._child_summary(child) for child in node.children]
        parts = [part for part in parts if part]
        return "; ".join(parts) if parts else None

    @staticmethod
    def _child_summary(child: CndNode) -> str:
        match child:
            case ImageNode():
                return child.alt or child.path or "image"
            case CodeNode():
                return f"code ({child.lang})" if child.lang else "code"
            case _:
                return str(child.type)
