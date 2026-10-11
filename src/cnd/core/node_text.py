"""Shared text-rendering plumbing used by ``cnd.core.render`` renderers."""

from collections.abc import Callable
from typing import Literal
from uuid import UUID

from cnd.core.nodes import ListItem, TableNode

# docs/proposals/0001-configurable-table-figure-rendering.md.
# "placeholder" is the default everywhere: always the parseable placeholder,
# regardless of content. "inline" always renders the content as text
# instead. "auto" defers to the node's own content_kind hint (see TableNode)
# with no classifier — an unset hint resolves to "placeholder" rather than
# being guessed.
NodeTextMode = Literal["placeholder", "inline", "auto"]


def format_figure_placeholder(
    *,
    figure_id: UUID,
    kind: str,
    caption: str | None = None,
    number: str | None = None,
    header_row: str | None = None,
    summary: str | None = None,
    counter_label: str | None = None,
    shape: tuple[int, int] | None = None,
    row_labels: str | None = None,
) -> str:
    """Build a parseable figure placeholder for chunk content.

    It carries everything the node says about itself except a table's body
    cells (docs/proposals/0012). Attribute values are quoted, with ``\\``
    and ``"`` backslash-escaped, line breaks folded to spaces and ``]]``
    split, so the placeholder is always one line ending at its first ``]]``.
    """
    attrs: dict[str, str] = {"kind": kind}
    if counter_label:
        attrs["counter"] = counter_label
    if number:
        attrs["number"] = number
    if caption:
        attrs["caption"] = caption
    if header_row:
        attrs["header"] = header_row
    if shape:
        attrs["rows"], attrs["cols"] = str(shape[0]), str(shape[1])
    if row_labels:
        attrs["row_labels"] = row_labels
    if summary:
        attrs["summary"] = summary
    formatted = " ".join(f'{key}="{_attr_value(value)}"' for key, value in attrs.items())
    return f"[[figure:{figure_id} {formatted}]]"


def _attr_value(value: str) -> str:
    value = value.replace("\\", "\\\\").replace('"', '\\"')
    value = " ".join(value.split())
    while "]]" in value:
        value = value.replace("]]", "] ]")
    return value


def render_list_markdown(
    items: list[ListItem],
    *,
    ordered: bool,
    depth: int = 0,
    escape: Callable[[str], str] | None = None,
) -> str:
    """Render a bullet or numbered list as markdown-like text.

    An ordered item prints its own ``number`` when the producer set one
    (a list that starts at 5, or skips values), else its position.
    """
    return "\n".join(_render_list_items(items, ordered, "  " * depth, escape))


def _render_list_items(
    items: list[ListItem],
    ordered: bool,
    indent: str,
    escape: Callable[[str], str] | None,
) -> list[str]:
    lines: list[str] = []
    for index, item in enumerate(items, start=1):
        number = item.number if item.number is not None else index
        prefix = f"{number}." if ordered else "-"
        text = escape(item.text) if escape else item.text
        lines.append(f"{indent}{prefix} {text}")
        if item.children:
            # A child must start at its parent's content column, so the
            # indent grows with the marker ("- " is 2, "1. " is 3, "10. " is 4).
            child_indent = indent + " " * (len(prefix) + 1)
            lines.extend(_render_list_items(item.children, ordered, child_indent, escape))
    return lines


def header_row_text(node: TableNode) -> str | None:
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
    """Placeholder string for a bare table or grid node.

    Caption and number live on a wrapping ``FigureNode`` when present —
    a bare table placeholder carries only kind and header structure.
    """
    return format_figure_placeholder(
        figure_id=node.id,
        kind=node.kind,
        header_row=header_row_text(node),
        shape=table_shape(node),
        row_labels=row_labels_text(node),
    )


#: How many first-column labels a placeholder lists before it says how many
#: it left out — enough to find a row by name, not a dump of the column.
ROW_LABELS_CAP = 20


def table_shape(node: TableNode) -> tuple[int, int] | None:
    """``(rows, cols)`` of the table's grid, spans included."""
    if not node.cells:
        return None
    rows = max(cell.row + cell.rowspan for cell in node.cells)
    cols = max(cell.col + cell.colspan for cell in node.cells)
    return rows, cols


def row_labels_text(node: TableNode, cap: int = ROW_LABELS_CAP) -> str | None:
    """The first column's text below the header, joined — the labels a data
    table's rows are usually looked up by. None for a single-column table,
    where the first column is the whole body. Header rows are the cells
    flagged ``is_header``, else row 0 (as in :func:`header_row_text`)."""
    shape = table_shape(node)
    if shape is None or shape[1] < 2:
        return None
    header_rows = {cell.row for cell in node.cells if cell.is_header} or {0}
    labels = [
        cell.text
        for cell in sorted(node.cells, key=lambda c: c.row)
        if cell.col == 0 and cell.row not in header_rows and cell.text
    ]
    if not labels:
        return None
    kept = " | ".join(labels[:cap])
    return f"{kept} | … (+{len(labels) - cap})" if len(labels) > cap else kept


def _cell_text(text: str, escape: Callable[[str], str] | None) -> str:
    """Cell text that cannot break the GFM row it sits in."""
    if escape:
        text = escape(text)
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    return text.replace("|", "\\|").replace("\n", "<br>")


def render_table_markdown(node: TableNode, *, escape: Callable[[str], str] | None = None) -> str:
    """Render a table node's cells as a Markdown grid.

    Spanned cells (``rowspan``/``colspan`` > 1) place their text once, at
    the cell's own ``(row, col)`` — Markdown has no native merged-cell
    syntax, so the rest of the span is left blank rather than repeated.
    The separator row follows the header row (cells flagged ``is_header``
    when present, else row 0). Cell text has ``|`` escaped and newlines
    turned into ``<br>`` so the row keeps its column count; ``escape``,
    when given, runs first on each cell.
    """
    if not node.cells:
        return ""
    max_row = max(cell.row + cell.rowspan - 1 for cell in node.cells)
    max_col = max(cell.col + cell.colspan - 1 for cell in node.cells)
    grid: list[list[str]] = [["" for _ in range(max_col + 1)] for _ in range(max_row + 1)]
    header_rows: set[int] = set()
    for cell in node.cells:
        grid[cell.row][cell.col] = _cell_text(cell.text, escape)
        if cell.is_header:
            header_rows.add(cell.row)

    header_row_index = min(header_rows) if header_rows else 0
    lines: list[str] = []
    for row_index, row in enumerate(grid):
        lines.append("| " + " | ".join(row) + " |")
        if row_index == header_row_index:
            lines.append("| " + " | ".join("---" for _ in row) + " |")

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
