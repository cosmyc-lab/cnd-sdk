import io
from pathlib import Path

from rich.console import Console

from ids import (
    HEADING001_ID,
    HEADING002_ID,
    MINIMAL_HEADING_ID,
    MINIMAL_PARAGRAPH_ID,
    PARA001_ID,
    RICH_CODE_ID,
    RICH_IMAGE_ID,
    RICH_TERMS_ID,
    TABLE001_ID,
)

from cnd.core.cnd import Cnd
from cnd.core.nodes import HeadingNode
from cnd.visitors.node_display_visitor import NodeDisplayVisitor


def _load(path: Path) -> Cnd:
    return Cnd.model_validate_json(path.read_text())


def _capture_output(**visitor_kwargs) -> str:
    output = io.StringIO()
    console = Console(file=output, width=120, force_terminal=False, no_color=True)
    return output, console


class TestNodeDisplayVisitor:
    def test_prints_node_trace_with_summary(
        self, minimal_cnd_path: Path,
    ) -> None:
        cnd = _load(minimal_cnd_path)
        output, console = _capture_output()

        NodeDisplayVisitor(console=console).visit(cnd)

        text = output.getvalue()
        assert str(MINIMAL_HEADING_ID) in text
        assert "Introduction" in text
        assert str(MINIMAL_PARAGRAPH_ID) in text
        assert "Premier paragraphe du document." in text
        assert "Node summary" in text
        assert "heading" in text
        assert "paragraph" in text

    def test_renders_cnd_header(
        self, minimal_cnd_path: Path,
    ) -> None:
        cnd = _load(minimal_cnd_path)
        output, console = _capture_output()

        NodeDisplayVisitor(console=console).visit(cnd)

        text = output.getvalue()
        assert "Test Document" in text
        assert "v0.3.0" in text
        assert "sha256:abc123def45678" in text

    def test_tree_mode_shows_hierarchy(
        self, structured_cnd_path: Path,
    ) -> None:
        cnd = _load(structured_cnd_path)
        output, console = _capture_output()

        NodeDisplayVisitor(console=console, show_tree=True).visit(cnd)

        text = output.getvalue()
        assert "CND tree" in text
        assert str(HEADING002_ID) in text
        assert str(PARA001_ID) in text
        assert str(TABLE001_ID) in text
        assert "H1 Description du système" in text

    def test_panel_mode_without_tree(
        self, structured_cnd_path: Path,
    ) -> None:
        cnd = _load(structured_cnd_path)
        output, console = _capture_output()

        NodeDisplayVisitor(console=console, show_tree=False).visit(cnd)

        text = output.getvalue()
        assert "HEADING" in text
        assert "PARAGRAPH" in text
        assert "TABLE" in text

    def test_shows_heading_path_parent_and_refs(
        self, structured_cnd_path: Path,
    ) -> None:
        cnd = _load(structured_cnd_path)
        output, console = _capture_output()

        NodeDisplayVisitor(console=console).visit(cnd)

        text = output.getvalue()
        assert "1 Description du système > 1.1 Paramètres nominaux" in text
        assert f"parent={HEADING002_ID}" in text
        assert str(TABLE001_ID) in text
        assert str(HEADING002_ID) in text
        assert str(PARA001_ID) in text
        assert "sec-params" in text
        assert "tab-params-nominaux" in text

    def test_shows_type_specific_details(
        self, structured_cnd_path: Path,
    ) -> None:
        cnd = _load(structured_cnd_path)
        output, console = _capture_output()

        NodeDisplayVisitor(console=console).visit(cnd)

        text = output.getvalue()
        assert "depth=2" in text
        assert "number=1.1" in text
        assert "children=2" in text
        assert "lang=fr" in text
        assert "cells=4" in text
        assert "Paramètres nominaux de fonctionnement." in text
        # The counter word ("Table") is not in the data — `number` is the
        # resolved value alone and `kind` carries the selector.
        assert "number=1" in text
        assert "Table 1" not in text
        assert "page=1" in text
        assert "child=1/2" in text
        assert "on-page=3/5" in text
        assert "doc=3/5" in text
        assert "doc=5/5" in text

    def test_can_hide_refs_and_location(
        self, structured_cnd_path: Path,
    ) -> None:
        cnd = _load(structured_cnd_path)
        output, console = _capture_output()

        NodeDisplayVisitor(
            console=console,
            show_refs=False,
            show_location=False,
        ).visit(cnd)

        text = output.getvalue()
        assert "@tab-params-nominaux" not in text
        assert "page=1" not in text
        assert str(TABLE001_ID) in text

    def test_truncates_long_text(
        self, structured_cnd_path: Path,
    ) -> None:
        cnd = _load(structured_cnd_path)
        output, console = _capture_output()

        NodeDisplayVisitor(console=console, max_text_len=20).visit(cnd)

        text = output.getvalue()
        assert "Le système est co..." in text
        assert "Paramètres nomina..." in text

    def test_can_disable_summary(
        self, minimal_cnd_path: Path,
    ) -> None:
        cnd = _load(minimal_cnd_path)
        output, console = _capture_output()

        NodeDisplayVisitor(console=console, show_summary=False).visit(cnd)

        assert "Node summary" not in output.getvalue()

    def test_max_depth_limits_output(
        self, structured_cnd_path: Path,
    ) -> None:
        cnd = _load(structured_cnd_path)
        output, console = _capture_output()

        NodeDisplayVisitor(console=console).visit(cnd, max_depth=1)

        text = output.getvalue()
        assert str(HEADING001_ID) in text
        assert str(HEADING002_ID) in text
        assert str(PARA001_ID) not in text
        assert "cells=4" not in text
        assert "number=Table 1" not in text

    def test_can_visit_a_node_subtree(
        self, structured_cnd_path: Path,
    ) -> None:
        cnd = _load(structured_cnd_path)
        section = cnd.nodes[0].children[0]
        assert isinstance(section, HeadingNode)
        output, console = _capture_output()

        NodeDisplayVisitor(console=console).visit([section])

        text = output.getvalue()
        assert str(HEADING002_ID) in text
        assert str(PARA001_ID) in text
        assert str(TABLE001_ID) in text
        assert str(HEADING001_ID) not in text

    def test_resets_counts_between_visits(
        self, minimal_cnd_path: Path,
    ) -> None:
        cnd = _load(minimal_cnd_path)
        output, console = _capture_output()
        visitor = NodeDisplayVisitor(console=console)

        visitor.visit(cnd)
        visitor.visit(cnd)

        assert visitor._counts == {"heading": 1, "paragraph": 1}


class TestNodeDisplayVisitorRichContent:
    def test_shows_new_node_types_and_descends_figures(
        self, rich_content_cnd_path: Path,
    ) -> None:
        cnd = _load(rich_content_cnd_path)
        output, console = _capture_output()

        NodeDisplayVisitor(console=console).visit(cnd)

        text = output.getvalue()
        assert "TERMS" in text
        assert str(RICH_TERMS_ID) in text
        assert "IMAGE" in text
        assert str(RICH_IMAGE_ID) in text
        # The code node lives inside a figure wrapper — descent required.
        assert str(RICH_CODE_ID) in text

    def test_shows_link_families_with_spans(
        self, rich_content_cnd_path: Path,
    ) -> None:
        cnd = _load(rich_content_cnd_path)
        output, console = _capture_output()

        NodeDisplayVisitor(console=console, truncate_text=False).visit(cnd)

        text = output.getvalue()
        assert "refs" in text
        assert "@lst-api[77:88]" in text
        assert "cites" in text
        assert "@smith2024[6:18]" in text
        assert "@fn-rest[57:61]" in text


class TestTableContentPreview:
    def test_table_preview_shows_cells_not_just_label(
        self, structured_cnd_path: Path,
    ) -> None:
        cnd = _load(structured_cnd_path)
        output, console = _capture_output()

        NodeDisplayVisitor(console=console).visit(cnd)

        text = output.getvalue()
        assert "| Paramètre | Valeur |" in text
        assert "Débit nominal" in text
        # The label is still available on the identity line.
        assert "label=tab-params-nominaux" in text


class TestPoolPanels:
    def test_pool_panels_list_entries_with_incoming_counts(
        self, rich_content_cnd_path: Path,
    ) -> None:
        cnd = _load(rich_content_cnd_path)
        output, console = _capture_output()

        NodeDisplayVisitor(console=console).visit(cnd)

        text = output.getvalue()
        assert "Bibliography" in text
        assert "@smith2024" in text
        assert "Smith, J., & Doe, A." in text
        assert "cited by 1" in text
        assert "Footnotes" in text
        assert "@fn-rest" in text
        assert "REST : Representational State" in text
        assert "referenced by 1" in text

    def test_show_pools_false_hides_pool_panels(
        self, rich_content_cnd_path: Path,
    ) -> None:
        cnd = _load(rich_content_cnd_path)
        output, console = _capture_output()

        NodeDisplayVisitor(console=console, show_pools=False).visit(cnd)

        text = output.getvalue()
        assert "Bibliography" not in text
        assert "referenced by" not in text

    def test_empty_pools_render_no_panels(
        self, minimal_cnd_path: Path,
    ) -> None:
        cnd = _load(minimal_cnd_path)
        output, console = _capture_output()

        NodeDisplayVisitor(console=console).visit(cnd)

        text = output.getvalue()
        assert "Bibliography" not in text
        assert "Footnotes" not in text
