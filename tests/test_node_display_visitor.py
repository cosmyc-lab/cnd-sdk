import io
from pathlib import Path

from rich.console import Console

from ids import (
    HEADING001_ID,
    HEADING002_ID,
    MINIMAL_HEADING_ID,
    MINIMAL_PARAGRAPH_ID,
    PARA001_ID,
    TABLE001_ID,
)

from cnd.core.manifest import CndManifest
from cnd.core.nodes import HeadingNode
from cnd.visitors.node_display_visitor import NodeDisplayVisitor


def _load(path: Path) -> CndManifest:
    return CndManifest.model_validate_json(path.read_text())


def _capture_output(**visitor_kwargs) -> str:
    output = io.StringIO()
    console = Console(file=output, width=120, force_terminal=False, no_color=True)
    return output, console


class TestNodeDisplayVisitor:
    def test_prints_node_trace_with_summary(
        self, minimal_manifest_path: Path,
    ) -> None:
        manifest = _load(minimal_manifest_path)
        output, console = _capture_output()

        NodeDisplayVisitor(console=console).visit(manifest)

        text = output.getvalue()
        assert str(MINIMAL_HEADING_ID) in text
        assert "Introduction" in text
        assert str(MINIMAL_PARAGRAPH_ID) in text
        assert "Premier paragraphe du document." in text
        assert "Node summary" in text
        assert "heading" in text
        assert "paragraph" in text

    def test_renders_manifest_header(
        self, minimal_manifest_path: Path,
    ) -> None:
        manifest = _load(minimal_manifest_path)
        output, console = _capture_output()

        NodeDisplayVisitor(console=console).visit(manifest)

        text = output.getvalue()
        assert "Test Document" in text
        assert "v0.1.0" in text
        assert "sha256:abc123def45678" in text

    def test_tree_mode_shows_hierarchy(
        self, structured_manifest_path: Path,
    ) -> None:
        manifest = _load(structured_manifest_path)
        output, console = _capture_output()

        NodeDisplayVisitor(console=console, show_tree=True).visit(manifest)

        text = output.getvalue()
        assert "CND Manifest" in text
        assert str(HEADING002_ID) in text
        assert str(PARA001_ID) in text
        assert str(TABLE001_ID) in text
        assert "H1 Description du système" in text

    def test_panel_mode_without_tree(
        self, structured_manifest_path: Path,
    ) -> None:
        manifest = _load(structured_manifest_path)
        output, console = _capture_output()

        NodeDisplayVisitor(console=console, show_tree=False).visit(manifest)

        text = output.getvalue()
        assert "HEADING" in text
        assert "PARAGRAPH" in text
        assert "TABLE" in text

    def test_shows_heading_path_parent_and_refs(
        self, structured_manifest_path: Path,
    ) -> None:
        manifest = _load(structured_manifest_path)
        output, console = _capture_output()

        NodeDisplayVisitor(console=console).visit(manifest)

        text = output.getvalue()
        assert "1 Description du système > 1.1 Paramètres nominaux" in text
        assert f"parent={HEADING002_ID}" in text
        assert str(TABLE001_ID) in text
        assert str(HEADING002_ID) in text
        assert str(PARA001_ID) in text
        assert "sec-params" in text
        assert "tab-params-nominaux" in text

    def test_shows_type_specific_details(
        self, structured_manifest_path: Path,
    ) -> None:
        manifest = _load(structured_manifest_path)
        output, console = _capture_output()

        NodeDisplayVisitor(console=console).visit(manifest)

        text = output.getvalue()
        assert "depth=2" in text
        assert "numbering=1.1" in text
        assert "children=2" in text
        assert "lang=fr" in text
        assert "cells=4" in text
        assert "Paramètres nominaux de fonctionnement." in text
        assert "Table 1" in text
        assert "page=1" in text
        assert "span=2" in text
        assert "page_span=2" in text
        assert "parent_span=1" in text

    def test_can_hide_refs_and_location(
        self, structured_manifest_path: Path,
    ) -> None:
        manifest = _load(structured_manifest_path)
        output, console = _capture_output()

        NodeDisplayVisitor(
            console=console,
            show_refs=False,
            show_location=False,
        ).visit(manifest)

        text = output.getvalue()
        assert "refs_to" not in text
        assert "refs_from" not in text
        assert "page=1" not in text
        assert str(TABLE001_ID) in text

    def test_truncates_long_text(
        self, structured_manifest_path: Path,
    ) -> None:
        manifest = _load(structured_manifest_path)
        output, console = _capture_output()

        NodeDisplayVisitor(console=console, max_text_len=20).visit(manifest)

        text = output.getvalue()
        assert "Le système est co..." in text
        assert "Paramètres nomina..." in text

    def test_can_disable_summary(
        self, minimal_manifest_path: Path,
    ) -> None:
        manifest = _load(minimal_manifest_path)
        output, console = _capture_output()

        NodeDisplayVisitor(console=console, show_summary=False).visit(manifest)

        assert "Node summary" not in output.getvalue()

    def test_max_depth_limits_output(
        self, structured_manifest_path: Path,
    ) -> None:
        manifest = _load(structured_manifest_path)
        output, console = _capture_output()

        NodeDisplayVisitor(console=console).visit(manifest, max_depth=1)

        text = output.getvalue()
        assert str(HEADING001_ID) in text
        assert str(HEADING002_ID) in text
        assert str(PARA001_ID) not in text
        assert "cells=4" not in text
        assert "fig_number=Table 1" not in text

    def test_can_visit_a_node_subtree(
        self, structured_manifest_path: Path,
    ) -> None:
        manifest = _load(structured_manifest_path)
        section = manifest.nodes[0].children[0]
        assert isinstance(section, HeadingNode)
        output, console = _capture_output()

        NodeDisplayVisitor(console=console).visit([section])

        text = output.getvalue()
        assert str(HEADING002_ID) in text
        assert str(PARA001_ID) in text
        assert str(TABLE001_ID) in text
        assert str(HEADING001_ID) not in text

    def test_resets_counts_between_visits(
        self, minimal_manifest_path: Path,
    ) -> None:
        manifest = _load(minimal_manifest_path)
        output, console = _capture_output()
        visitor = NodeDisplayVisitor(console=console)

        visitor.visit(manifest)
        visitor.visit(manifest)

        assert visitor._counts == {"heading": 1, "paragraph": 1}
