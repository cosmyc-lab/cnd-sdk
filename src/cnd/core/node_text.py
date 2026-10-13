"""Shared text-rendering plumbing used by ``cnd.core.render`` renderers."""

from collections.abc import Callable
from typing import Literal
from uuid import UUID

from cnd.core.nodes import (
    Cell,
    CndNode,
    CodeNode,
    ImageNode,
    MathNode,
    ParagraphNode,
    TableNode,
    child_slots,
    texts_of,
)

# docs/proposals/0001-configurable-table-figure-rendering.md.
# "placeholder" is the default everywhere: always the parseable placeholder,
# regardless of content. "inline" always renders the content as text
# instead. "auto" defers to the table's ``kind`` (docs/proposals/0013):
# inline for "content"; "data", None and any unknown kind resolve to
# "placeholder" rather than being guessed.
NodeTextMode = Literal["placeholder", "inline", "auto"]


def wants_inline_table(node: TableNode, mode: NodeTextMode) -> bool:
    """Whether ``mode`` renders this table's cells rather than a placeholder."""
    return mode == "inline" or (mode == "auto" and node.kind == "content")


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
    description: str | None = None,
    table_kind: str | None = None,
    escape: Callable[[str], str] | None = None,
) -> str:
    """Build a parseable figure placeholder for chunk content.

    It carries everything the node says about itself except a table's body
    cells (docs/proposals/0012), in this order: kind, counter word, number,
    caption, description, table kind, header row, size, row labels,
    summary. Every value is plain text (marks dropped). Attribute values
    are quoted, with ``\\`` and ``"`` backslash-escaped, line breaks folded
    to spaces and ``]]`` split, so the placeholder is always one line
    ending at its first ``]]``. ``escape``, when given, is applied to
    every quoted value afterwards (a Markdown renderer passes its
    free-text escaping, so a value cannot become Markdown syntax).
    """
    attrs: dict[str, str] = {"kind": kind}
    if counter_label:
        attrs["counter"] = counter_label
    if number:
        attrs["number"] = number
    if caption:
        attrs["caption"] = caption
    if description:
        attrs["description"] = description
    if table_kind:
        attrs["table_kind"] = table_kind
    if header_row:
        attrs["header"] = header_row
    if shape:
        attrs["rows"], attrs["cols"] = str(shape[0]), str(shape[1])
    if row_labels:
        attrs["row_labels"] = row_labels
    if summary:
        attrs["summary"] = summary
    quote = escape or (lambda value: value)
    formatted = " ".join(
        f'{key}="{quote(attr_value(value))}"' for key, value in attrs.items()
    )
    return f"[[figure:{figure_id} {formatted}]]"


def attr_value(value: str) -> str:
    """A placeholder attribute value: ``\\`` and ``"`` backslash-escaped,
    whitespace runs (line breaks included) folded to one space, ``]]``
    split."""
    value = value.replace("\\", "\\\\").replace('"', '\\"')
    value = " ".join(value.split())
    while "]]" in value:
        value = value.replace("]]", "] ]")
    return value


def blocks_plain_text(nodes: list[CndNode]) -> str:
    """The plain text of block nodes, in reading order, joined by spaces:
    every text of every node (marks dropped), a code or math node's
    source, an image's alt. Used where a one-line summary is needed."""
    parts: list[str] = []
    for node in nodes:
        parts.extend(text.value for text in texts_of(node))
        if isinstance(node, (CodeNode, MathNode)):
            parts.append(node.text)
        elif isinstance(node, ImageNode) and node.alt:
            parts.append(node.alt)
        for slot in child_slots(node):
            parts.append(blocks_plain_text(slot.nodes))
    return " ".join(part for part in parts if part)


def cell_plain_text(cell: Cell) -> str:
    """A cell's content as one line of plain text."""
    return blocks_plain_text(cell.children)


def is_inline_cell(cell: Cell) -> bool:
    """Whether a cell fits in a GFM table cell: empty, one paragraph, or
    one image (docs/proposals/0013, "Rendering")."""
    return len(cell.children) == 0 or (
        len(cell.children) == 1 and isinstance(cell.children[0], (ParagraphNode, ImageNode))
    )


def header_row_text(node: TableNode) -> str | None:
    """The header row's cell text, joined — cells flagged ``is_header``
    when present, else row 0 (the common case for tables that never set
    the flag). Used to give even a placeholder some structure, not just an
    id (docs/proposals/0001, "cheap to do on its own")."""
    if not node.cells:
        return None
    flagged = {cell.row for cell in node.cells if cell.is_header}
    target_row = min(flagged) if flagged else 0
    row_cells = sorted((c for c in node.cells if c.row == target_row), key=lambda c: c.col)
    texts = [text for text in map(cell_plain_text, row_cells) if text]
    return " | ".join(texts) if texts else None


def table_node_placeholder(
    node: TableNode, escape: Callable[[str], str] | None = None
) -> str:
    """Placeholder string for a bare table node.

    Caption and number live on a wrapping ``FigureNode`` when present —
    a bare table placeholder carries its kind, header structure, size and
    row labels. ``escape`` is passed to ``format_figure_placeholder``.
    """
    return format_figure_placeholder(
        figure_id=node.id,
        kind="table",
        table_kind=node.kind,
        header_row=header_row_text(node),
        shape=table_shape(node),
        row_labels=row_labels_text(node),
        escape=escape,
    )


#: How many first-column labels a placeholder lists before it says how many
#: it left out — enough to find a row by name, not a dump of the column.
ROW_LABELS_CAP = 20


def table_shape(node: TableNode) -> tuple[int, int] | None:
    """``(rows, cols)`` of the table's grid, spans included."""
    if not node.cells:
        return None
    rows = max(cell.row + max(cell.rowspan, 1) for cell in node.cells)
    cols = max(cell.col + max(cell.colspan, 1) for cell in node.cells)
    return rows, cols


def header_rows(node: TableNode) -> set[int]:
    """Rows whose every cell is a header. A row merely *containing* a
    header cell is not one: row headers (the first column of a data table)
    flag a cell on every row. With no flag anywhere, row 0, the same
    assumption as :func:`header_row_text`."""
    if not any(cell.is_header for cell in node.cells):
        return {0}
    rows: dict[int, bool] = {}
    for cell in node.cells:
        rows[cell.row] = rows.get(cell.row, True) and cell.is_header
    return {row for row, all_header in rows.items() if all_header}


def row_labels_text(node: TableNode, cap: int = ROW_LABELS_CAP) -> str | None:
    """The first column's text below the header, joined — the labels a data
    table's rows are usually looked up by. None for a single-column table,
    where the first column is the whole body. See :func:`header_rows`."""
    shape = table_shape(node)
    if shape is None or shape[1] < 2:
        return None
    skipped = header_rows(node)
    labels = [
        text
        for cell in sorted(node.cells, key=lambda c: c.row)
        if cell.col == 0 and cell.row not in skipped and (text := cell_plain_text(cell))
    ]
    if not labels:
        return None
    kept = " | ".join(labels[:cap])
    return f"{kept} | … (+{len(labels) - cap})" if len(labels) > cap else kept


def _gfm_cell(text: str, *, text_only: bool) -> str:
    """Cell text that cannot break the GFM row it sits in."""
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    return text.replace("|", "\\|").replace("\n", " " if text_only else "<br>")


def render_table_markdown(
    node: TableNode,
    *,
    cell_text: Callable[[Cell], str] | None = None,
    text_only: bool = False,
) -> str:
    """Render a table node's cells as a GFM grid.

    ``cell_text`` turns a cell into inline Markdown; the default is the
    cell's plain text. Call it only on a table whose cells pass
    :func:`is_inline_cell`, or block content is flattened. Spanned cells
    (``rowspan``/``colspan`` > 1) place their text once, at the cell's own
    ``(row, col)`` — Markdown has no merged-cell syntax, so the rest of the
    span is left blank rather than repeated. The separator row follows the
    header row (cells flagged ``is_header`` when present, else row 0).
    Each cell has ``|`` escaped and newlines turned into ``<br>`` (a space
    under ``text_only``) so the row keeps its column count.
    """
    if not node.cells:
        return ""
    render_cell = cell_text or cell_plain_text
    max_row = max(cell.row + cell.rowspan - 1 for cell in node.cells)
    max_col = max(cell.col + cell.colspan - 1 for cell in node.cells)
    grid: list[list[str]] = [["" for _ in range(max_col + 1)] for _ in range(max_row + 1)]
    flagged: set[int] = set()
    for cell in node.cells:
        grid[cell.row][cell.col] = _gfm_cell(render_cell(cell), text_only=text_only)
        if cell.is_header:
            flagged.add(cell.row)

    header_row_index = min(flagged) if flagged else 0
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
    Cells render as plain text here; ``MarkdownRenderer`` renders marks.
    """
    if wants_inline_table(node, mode):
        rendered = render_table_markdown(node)
        if rendered:
            return rendered
    return table_node_placeholder(node)
