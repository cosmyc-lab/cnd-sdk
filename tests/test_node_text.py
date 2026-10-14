"""Placeholder and table helpers on 0.5 nodes (docs/proposals/0012, 0013)."""

from uuid import uuid4

from factories import cell, para, rt

from cnd.core.node_text import (
    blocks_plain_text,
    format_figure_placeholder,
    header_row_text,
    is_inline_cell,
    render_table_markdown,
    row_labels_text,
    table_node_placeholder,
    table_node_text,
    wants_inline_table,
)
from cnd.core.nodes import ImageNode, ListNode, TableNode
from cnd.core.text import Mark


def _table(**kwargs) -> TableNode:
    return TableNode(type="table", id=uuid4(), **kwargs)


def _image(alt: str = "Alt") -> ImageNode:
    return ImageNode(type="image", id=uuid4(), path="a.png", alt=alt)


def test_plain_text_drops_marks_and_walks_containers() -> None:
    bold = para(rt("Bold move", marks=[Mark(start=0, end=4, kind="strong")]))
    nested = ListNode(type="list", id=uuid4(), items=[])
    assert blocks_plain_text([bold, _image("Logo"), nested]) == "Bold move Logo"


def test_inline_cells() -> None:
    assert is_inline_cell(cell(0, 0))
    assert is_inline_cell(cell(0, 0, "x"))
    assert is_inline_cell(cell(0, 0, children=[_image()]))
    assert not is_inline_cell(cell(0, 0, children=[para("a"), para("b")]))
    assert not is_inline_cell(cell(0, 0, children=[ListNode(type="list", id=uuid4())]))


def test_auto_mode_follows_table_kind() -> None:
    assert wants_inline_table(_table(kind="content"), "auto")
    assert not wants_inline_table(_table(kind="data"), "auto")
    assert not wants_inline_table(_table(kind=None), "auto")
    assert not wants_inline_table(_table(kind="matrix"), "auto")
    assert wants_inline_table(_table(kind="data"), "inline")


def test_placeholder_carries_description_and_table_kind() -> None:
    figure_id = uuid4()
    out = format_figure_placeholder(
        figure_id=figure_id,
        kind="chart",
        caption="Rates",
        description="Bars: A 38 %, B 27 %",
        table_kind="data",
    )
    assert out == (
        f'[[figure:{figure_id} kind="chart" caption="Rates" '
        f'description="Bars: A 38 %, B 27 %" table_kind="data"]]'
    )


def test_bare_table_placeholder_reads_cell_paragraphs() -> None:
    node = _table(
        kind="data",
        cells=[
            cell(0, 0, "Station", is_header=True),
            cell(0, 1, "hPa", is_header=True),
            cell(1, 0, "Brest"),
            cell(1, 1, "1013"),
        ],
    )
    assert header_row_text(node) == "Station | hPa"
    assert row_labels_text(node) == "Brest"
    assert table_node_placeholder(node) == (
        f'[[figure:{node.id} kind="table" table_kind="data" header="Station | hPa" '
        f'rows="2" cols="2" row_labels="Brest"]]'
    )


def test_gfm_grid_uses_the_cell_renderer() -> None:
    node = _table(cells=[cell(0, 0, "a|b", is_header=True), cell(1, 0, "x\ny")])
    assert render_table_markdown(node) == "| a\\|b |\n| --- |\n| x<br>y |"
    assert render_table_markdown(node, text_only=True).splitlines()[2] == "| x y |"
    shouted = render_table_markdown(node, cell_text=lambda c: blocks_plain_text(c.children).upper())
    assert shouted.splitlines()[0] == "| A\\|B |"


def test_table_node_text_modes() -> None:
    node = _table(kind="content", cells=[cell(0, 0, "A", is_header=True)])
    assert table_node_text(node, mode="auto") == "| A |\n| --- |"
    assert table_node_text(node).startswith("[[figure:")
