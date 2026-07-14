"""Text rendering helpers for CND manifest nodes."""

from typing import Literal
from uuid import UUID

from cnd.core.nodes import CndNode, FigureNode, ListItem, ListNode, TableNode

# docs/proposals/0001-configurable-table-figure-rendering.md.
# "placeholder" is the default everywhere (TableNode.to_text()'s output is
# unaffected by this type existing at all): always the parseable
# placeholder, regardless of content. "inline" always renders the table's
# cells as text instead. "auto" defers to the node's own content_kind hint
# (see TableNode) with no classifier — an unset hint resolves to
# "placeholder", the same as today, rather than being guessed.
NodeTextMode = Literal["placeholder", "inline", "auto"]


def format_figure_placeholder(
    *,
    figure_id: UUID,
    kind: str,
    caption: str | None = None,
    number: str | None = None,
    header_row: str | None = None,
    summary: str | None = None,
) -> str:
    """Build a parseable figure placeholder for chunk content."""
    attrs: dict[str, str] = {"kind": kind}
    if number:
        attrs["number"] = number
    if caption:
        attrs["caption"] = caption
    if header_row:
        attrs["header"] = header_row
    if summary:
        attrs["summary"] = summary
    formatted = " ".join(f'{key}="{value}"' for key, value in attrs.items())
    return f"[[figure:{figure_id} {formatted}]]"


def render_list_markdown(items: list[ListItem], *, ordered: bool, depth: int = 0) -> str:
    """Render a bullet or numbered list as markdown-like text."""
    return "\n".join(_render_list_items(items, ordered, depth))


def _render_list_items(items: list[ListItem], ordered: bool, depth: int) -> list[str]:
    lines: list[str] = []
    for index, item in enumerate(items, start=1):
        prefix = f"{index}." if ordered else "-"
        indent = "  " * depth
        lines.append(f"{indent}{prefix} {item.text}")
        if item.children:
            lines.extend(_render_list_items(item.children, ordered, depth + 1))
    return lines


def _header_row_text(node: TableNode) -> str | None:
    """The header row's cell text, joined — cells flagged ``is_header``
    when present, else row 0 (the common case for tables that never set
    the flag). Used to give even a placeholder some structure, not just an
    id (docs/proposals/0001, "cheap to do on its own")."""
    if not node.cells:
        return None
    header_rows = {cell.row for cell in node.cells if cell.is_header}
    target_row = min(header_rows) if header_rows else 0
    row_cells = sorted((c for c in node.cells if c.row == target_row), key=lambda c: c.col)
    texts = [c.text for c in row_cells if c.text]
    return " | ".join(texts) if texts else None


def table_node_placeholder(node: TableNode) -> str:
    """Placeholder string for a table or grid node."""
    return format_figure_placeholder(
        figure_id=node.id,
        kind=node.kind,
        caption=node.caption,
        number=node.fig_number,
        header_row=_header_row_text(node),
    )


def figure_node_placeholder(node: FigureNode) -> str:
    """Placeholder string for a non-table figure node."""
    return format_figure_placeholder(
        figure_id=node.id,
        kind=node.kind or "image",
        caption=node.caption,
        number=node.fig_number,
    )


def render_table_markdown(node: TableNode) -> str:
    """Render a table node's cells as a Markdown grid.

    Spanned cells (``rowspan``/``colspan`` > 1) place their text once, at
    the cell's own ``(row, col)`` — Markdown has no native merged-cell
    syntax, so the rest of the span is left blank rather than repeated.
    The separator row follows the header row (cells flagged ``is_header``
    when present, else row 0).
    """
    if not node.cells:
        return ""
    max_row = max(cell.row + cell.rowspan - 1 for cell in node.cells)
    max_col = max(cell.col + cell.colspan - 1 for cell in node.cells)
    grid: list[list[str]] = [["" for _ in range(max_col + 1)] for _ in range(max_row + 1)]
    header_rows: set[int] = set()
    for cell in node.cells:
        grid[cell.row][cell.col] = cell.text
        if cell.is_header:
            header_rows.add(cell.row)

    header_row_index = min(header_rows) if header_rows else 0
    lines: list[str] = []
    for row_index, row in enumerate(grid):
        lines.append("| " + " | ".join(row) + " |")
        if row_index == header_row_index:
            lines.append("| " + " | ".join("---" for _ in row) + " |")

    title = " — ".join(part for part in (node.fig_number, node.caption) if part)
    if title:
        return f"{title}\n\n" + "\n".join(lines)
    return "\n".join(lines)


def table_node_text(node: TableNode, *, mode: NodeTextMode = "placeholder") -> str:
    """Render a table node's text, honoring an explicit rendering mode.

    Falls back to the placeholder if the resolved mode would render inline
    but the table has no cells to render (nothing to gain from switching).
    """
    wants_inline = mode == "inline" or (mode == "auto" and node.content_kind == "content")
    if wants_inline:
        rendered = render_table_markdown(node)
        if rendered:
            return rendered
    return table_node_placeholder(node)


def render_node_text(node: CndNode, *, mode: NodeTextMode = "placeholder") -> str:
    """Polymorphic text rendering with mode support (docs/proposals/0001).

    Only table nodes currently vary by ``mode`` — every other node type has
    exactly one textual representation regardless of content, so this falls
    through to that type's own zero-argument ``to_text()`` unchanged; a
    future node type can opt into mode-aware rendering the same way tables
    did, without ``to_text()`` itself ever needing a parameter.
    """
    if isinstance(node, TableNode):
        return table_node_text(node, mode=mode)
    return node.to_text()
