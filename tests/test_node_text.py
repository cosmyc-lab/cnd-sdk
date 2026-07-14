from pathlib import Path
from uuid import uuid4

from cnd.core.manifest import CndManifest
from cnd.core.node_text import (
    format_figure_placeholder,
    render_list_markdown,
    render_node_text,
    render_table_markdown,
    table_node_text,
)
from cnd.core.nodes import (
    CodeNode,
    FigureNode,
    ListItem,
    ListNode,
    MathNode,
    NodeLocation,
    ParagraphNode,
    QuoteNode,
    TableCell,
    TableNode,
)


def _location(span: int = 0) -> NodeLocation:
    return NodeLocation(
        page=1,
        span=span,
        page_span=span,
        parent_span=0,
        span_count=1,
    )


def _base(**kwargs):
    defaults = {
        "id": uuid4(),
        "location": _location(),
    }
    defaults.update(kwargs)
    return defaults


class TestNodeToText:
    def test_paragraph_to_text(self) -> None:
        node = ParagraphNode(type="paragraph", text="Hello world", **_base())
        assert node.to_text() == "Hello world"

    def test_quote_to_text_with_attribution(self) -> None:
        node = QuoteNode(
            type="quote",
            text="Programs must be written for people to read.",
            attribution="Ada Lovelace",
            **_base(),
        )
        assert node.to_text() == (
            "Programs must be written for people to read.\n— Ada Lovelace"
        )

    def test_code_to_text(self) -> None:
        node = CodeNode(
            type="code",
            text="print('hi')",
            lang="python",
            **_base(),
        )
        assert node.to_text() == "```python\nprint('hi')\n```"

    def test_math_to_text(self) -> None:
        node = MathNode(type="math", text="E = m c^2", **_base())
        assert node.to_text() == "E = m c^2"

    def test_list_to_text(self) -> None:
        node = ListNode(
            type="list",
            ordered=False,
            items=[
                ListItem(text="Alpha"),
                ListItem(text="Beta"),
            ],
            **_base(),
        )
        assert node.to_text() == "- Alpha\n- Beta"

    def test_table_placeholder_uses_kind(self) -> None:
        node = TableNode(
            type="table",
            kind="grid",
            caption="A grid",
            fig_number="Figure 2",
            cells=[TableCell(row=0, col=0, text="A")],
            **_base(),
        )
        text = node.to_text()
        assert 'kind="grid"' in text
        assert 'caption="A grid"' in text

    def test_table_placeholder_includes_header_row_text(self) -> None:
        node = TableNode(
            type="table",
            cells=[
                TableCell(row=0, col=0, text="Name", is_header=True),
                TableCell(row=0, col=1, text="Value", is_header=True),
                TableCell(row=1, col=0, text="Torque"),
                TableCell(row=1, col=1, text="12 Nm"),
            ],
            **_base(),
        )
        assert 'header="Name | Value"' in node.to_text()

    def test_table_placeholder_falls_back_to_first_row_without_header_flag(self) -> None:
        node = TableNode(
            type="table",
            cells=[
                TableCell(row=0, col=0, text="A"),
                TableCell(row=1, col=0, text="B"),
            ],
            **_base(),
        )
        assert 'header="A"' in node.to_text()

    def test_table_placeholder_omits_header_attr_when_no_cells(self) -> None:
        node = TableNode(type="table", **_base())
        assert "header=" not in node.to_text()

    def test_figure_placeholder(self) -> None:
        node = FigureNode(
            type="figure",
            kind="image",
            caption="Diagram",
            fig_number="Figure 1",
            **_base(),
        )
        text = node.to_text()
        assert 'kind="image"' in text
        assert 'caption="Diagram"' in text


class TestNodeTextHelpers:
    def test_render_list_markdown_nested(self) -> None:
        items = [
            ListItem(
                text="Parent",
                children=[ListItem(text="Child")],
            )
        ]
        assert render_list_markdown(items, ordered=True) == "1. Parent\n  1. Child"

    def test_format_figure_placeholder(self) -> None:
        figure_id = uuid4()
        placeholder = format_figure_placeholder(
            figure_id=figure_id,
            kind="grid",
            caption="Layout",
            number="Figure 3",
        )
        assert str(figure_id) in placeholder
        assert 'kind="grid"' in placeholder


class TestRenderTableMarkdown:
    def test_simple_grid(self) -> None:
        node = TableNode(
            type="table",
            cells=[
                TableCell(row=0, col=0, text="Name", is_header=True),
                TableCell(row=0, col=1, text="Value", is_header=True),
                TableCell(row=1, col=0, text="Torque"),
                TableCell(row=1, col=1, text="12 Nm"),
            ],
            **_base(),
        )
        assert render_table_markdown(node) == (
            "| Name | Value |\n"
            "| --- | --- |\n"
            "| Torque | 12 Nm |"
        )

    def test_no_cells_returns_empty_string(self) -> None:
        node = TableNode(type="table", **_base())
        assert render_table_markdown(node) == ""

    def test_header_row_detected_without_flag_defaults_to_row_zero(self) -> None:
        node = TableNode(
            type="table",
            cells=[
                TableCell(row=0, col=0, text="A"),
                TableCell(row=1, col=0, text="B"),
            ],
            **_base(),
        )
        assert render_table_markdown(node) == "| A |\n| --- |\n| B |"

    def test_spanned_cell_extends_grid_without_truncation(self) -> None:
        # A cell spanning two columns starting at the last column index any
        # other cell uses — max_col must account for colspan, not just col.
        node = TableNode(
            type="table",
            cells=[
                TableCell(row=0, col=0, text="A", colspan=2),
                TableCell(row=1, col=0, text="B"),
                TableCell(row=1, col=1, text="C"),
            ],
            **_base(),
        )
        rendered = render_table_markdown(node)
        rows = rendered.split("\n")
        assert rows[0] == "| A |  |"
        assert rows[-1] == "| B | C |"

    def test_includes_caption_and_number_as_title(self) -> None:
        node = TableNode(
            type="table",
            caption="Nominal parameters",
            fig_number="Table 1",
            cells=[TableCell(row=0, col=0, text="A")],
            **_base(),
        )
        rendered = render_table_markdown(node)
        assert rendered.startswith("Table 1 — Nominal parameters\n\n")


class TestTableNodeText:
    _CELLS = [TableCell(row=0, col=0, text="A", is_header=True), TableCell(row=1, col=0, text="B")]

    def test_placeholder_mode_ignores_content_kind(self) -> None:
        node = TableNode(type="table", content_kind="content", cells=self._CELLS, **_base())
        assert table_node_text(node, mode="placeholder").startswith("[[figure:")

    def test_inline_mode_renders_markdown_regardless_of_content_kind(self) -> None:
        node = TableNode(type="table", content_kind="data", cells=self._CELLS, **_base())
        assert table_node_text(node, mode="inline") == "| A |\n| --- |\n| B |"

    def test_auto_mode_inlines_when_content_kind_is_content(self) -> None:
        node = TableNode(type="table", content_kind="content", cells=self._CELLS, **_base())
        assert table_node_text(node, mode="auto") == "| A |\n| --- |\n| B |"

    def test_auto_mode_placeholders_when_content_kind_is_data(self) -> None:
        node = TableNode(type="table", content_kind="data", cells=self._CELLS, **_base())
        assert table_node_text(node, mode="auto").startswith("[[figure:")

    def test_auto_mode_placeholders_when_content_kind_unset(self) -> None:
        # No classifier: an unset hint is treated as "data", never guessed.
        node = TableNode(type="table", content_kind=None, cells=self._CELLS, **_base())
        assert table_node_text(node, mode="auto").startswith("[[figure:")

    def test_inline_mode_falls_back_to_placeholder_when_no_cells(self) -> None:
        node = TableNode(type="table", **_base())
        assert table_node_text(node, mode="inline").startswith("[[figure:")

    def test_default_mode_matches_to_text(self) -> None:
        node = TableNode(type="table", content_kind="content", cells=self._CELLS, **_base())
        assert table_node_text(node) == node.to_text()


class TestRenderNodeText:
    def test_dispatches_table_with_mode(self) -> None:
        node = TableNode(
            type="table",
            content_kind="content",
            cells=[TableCell(row=0, col=0, text="A")],
            **_base(),
        )
        assert render_node_text(node, mode="inline") == "| A |\n| --- |"

    def test_non_table_node_ignores_mode(self) -> None:
        node = ParagraphNode(type="paragraph", text="Hello", **_base())
        assert render_node_text(node, mode="inline") == "Hello"
        assert render_node_text(node) == node.to_text()


class TestRealFixtureTable:
    """Integration coverage on a real, rowspan-heavy table (the sensor
    range table in fixtures/comprehensive_manifest.json), not a hand-built
    minimal one — this is the exact shape the old renderer mis-sized."""

    def _find_table(self, manifest: CndManifest) -> TableNode:
        for nt in manifest.iter():
            if isinstance(nt.node, TableNode):
                return nt.node
        raise AssertionError("no table node in fixture")

    def test_fixture_table_has_content_kind_content(self, comprehensive_manifest_path: Path) -> None:
        manifest = CndManifest.model_validate_json(comprehensive_manifest_path.read_text())
        table = self._find_table(manifest)
        assert table.content_kind == "content"

    def test_auto_mode_inlines_the_real_table(self, comprehensive_manifest_path: Path) -> None:
        manifest = CndManifest.model_validate_json(comprehensive_manifest_path.read_text())
        table = self._find_table(manifest)
        rendered = table_node_text(table, mode="auto")

        assert rendered != table.to_text(), "auto mode should have inlined, not returned the placeholder"
        assert "Capteur" in rendered
        assert "Pression" in rendered
        assert "0–16 bar" in rendered
        rows = [line for line in rendered.split("\n") if line.startswith("|")]
        # 1 header + 1 separator + 3 data rows (Pression spans rows 1-2,
        # Débit is row 3) — the grid must be sized from row+rowspan, not
        # just the max row any single cell declares.
        assert len(rows) == 5

    def test_placeholder_mode_still_available_on_the_same_table(
        self, comprehensive_manifest_path: Path
    ) -> None:
        manifest = CndManifest.model_validate_json(comprehensive_manifest_path.read_text())
        table = self._find_table(manifest)
        assert table_node_text(table, mode="placeholder") == table.to_text()
