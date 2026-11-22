"""GFM tables from CND tables whose header is not row 0 or whose cells merge.

Every output is re-parsed with markdown-it: it must be exactly one table
whose cells are the ones the CND table holds (CND-58).
"""

from uuid import uuid4

from factories import cell
from markdown_it import MarkdownIt

from cnd.core.node_text import render_table_markdown
from cnd.core.nodes import TableNode


def _table(*cells) -> TableNode:
    return TableNode(type="table", id=uuid4(), cells=list(cells))


def _parse(markdown: str) -> tuple[list[list[str]], list[list[str]]]:
    """The (header rows, body rows) of the one table in ``markdown``."""
    tokens = MarkdownIt("commonmark").enable("table").parse(markdown)
    assert [t.type for t in tokens].count("table_open") == 1
    assert tokens[0].type == "table_open"
    head: list[list[str]] = []
    body: list[list[str]] = []
    target = head
    for tok in tokens:
        if tok.type == "tbody_open":
            target = body
        elif tok.type == "tr_open":
            target.append([])
        elif tok.type == "inline":
            target[-1].append(tok.content)
    return head, body


def test_row_headers_only_in_column_zero_keep_every_cell_in_one_table() -> None:
    # The header cells sit in column 0 from row 1 on; row 0 is data.
    node = _table(
        cell(0, 0, "n/a"), cell(0, 1, "x"),
        cell(1, 0, "Alpha", is_header=True), cell(1, 1, "1"),
        cell(2, 0, "Beta", is_header=True), cell(2, 1, "2"),
    )
    head, body = _parse(render_table_markdown(node))
    assert head == [["", ""]]
    assert body == [["n/a", "x"], ["Alpha", "1"], ["Beta", "2"]]


def test_header_row_after_a_data_row_does_not_break_the_table() -> None:
    node = _table(
        cell(0, 0, "a"), cell(0, 1, "b"),
        cell(1, 0, "H1", is_header=True), cell(1, 1, "H2", is_header=True),
        cell(2, 0, "c"), cell(2, 1, "d"),
    )
    head, body = _parse(render_table_markdown(node))
    assert head == [["", ""]]
    assert body == [["a", "b"], ["H1", "H2"], ["c", "d"]]


def test_leading_header_row_is_the_markdown_header() -> None:
    node = _table(
        cell(0, 0, "A", is_header=True), cell(0, 1, "B", is_header=True),
        cell(1, 0, "x"), cell(1, 1, "y"),
    )
    head, body = _parse(render_table_markdown(node))
    assert head == [["A", "B"]]
    assert body == [["x", "y"]]


def test_unflagged_table_takes_row_zero_as_header() -> None:
    node = _table(cell(0, 0, "A"), cell(0, 1, "B"), cell(1, 0, "x"), cell(1, 1, "y"))
    head, body = _parse(render_table_markdown(node))
    assert head == [["A", "B"]]
    assert body == [["x", "y"]]


def test_colspan_repeats_the_value_across_covered_columns() -> None:
    node = _table(
        cell(0, 0, "Wide", is_header=True, colspan=2), cell(0, 2, "C", is_header=True),
        cell(1, 0, "x"), cell(1, 1, "y"), cell(1, 2, "z"),
    )
    head, body = _parse(render_table_markdown(node))
    assert head == [["Wide", "Wide", "C"]]
    assert body == [["x", "y", "z"]]


def test_rowspan_repeats_the_value_down_covered_rows() -> None:
    node = _table(
        cell(0, 0, "K", is_header=True), cell(0, 1, "V", is_header=True),
        cell(1, 0, "Pressure", rowspan=2), cell(1, 1, "PT-101"),
        cell(2, 1, "PT-102"),
    )
    head, body = _parse(render_table_markdown(node))
    assert head == [["K", "V"]]
    assert body == [["Pressure", "PT-101"], ["Pressure", "PT-102"]]


def test_a_real_cell_is_never_overwritten_by_a_span() -> None:
    node = _table(
        cell(0, 0, "A", colspan=2), cell(0, 1, "B"),
        cell(1, 0, "x"), cell(1, 1, "y"),
    )
    head, body = _parse(render_table_markdown(node))
    assert head == [["A", "B"]]


def test_nutrition_table_with_merged_cells() -> None:
    # Shape of a real extracted table: header row, a full-width group row
    # (colspan 3) and a value spanning two rows.
    node = _table(
        cell(0, 0, "Nutrient", is_header=True), cell(0, 1, "Per 100g", is_header=True),
        cell(0, 2, "Per serving", is_header=True),
        cell(1, 0, "Calories"), cell(1, 1, "250 kcal"), cell(1, 2, "375 kcal"),
        cell(2, 0, "Macros", colspan=3),
        cell(3, 0, "Protein"), cell(3, 1, "8 g", rowspan=2), cell(3, 2, "12 g"),
        cell(4, 0, "Fat"), cell(4, 2, "18 g"),
        cell(5, 0, "Total"), cell(5, 1, "—"), cell(5, 2, "—"),
    )
    head, body = _parse(render_table_markdown(node))
    assert head == [["Nutrient", "Per 100g", "Per serving"]]
    assert body == [
        ["Calories", "250 kcal", "375 kcal"],
        ["Macros", "Macros", "Macros"],
        ["Protein", "8 g", "12 g"],
        ["Fat", "8 g", "18 g"],
        ["Total", "—", "—"],
    ]
