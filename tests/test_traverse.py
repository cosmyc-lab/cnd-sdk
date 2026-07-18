from pathlib import Path

from ids import FIGURE001_ID, HEADING001_ID, HEADING002_ID, PARA001_ID, TABLE001_ID

from cnd.core.manifest import CndManifest
from cnd.core.nodes import FigureNode, HeadingNode, ParagraphNode, TableNode, iter_nodes


def _load(path: Path) -> CndManifest:
    return CndManifest.model_validate_json(path.read_text())


class TestIterNodes:
    def test_manifest_is_directly_iterable(
        self, structured_manifest_path: Path,
    ) -> None:
        manifest = _load(structured_manifest_path)

        ids = [visit.node.id for visit in manifest]

        assert ids == [
            HEADING001_ID,
            HEADING002_ID,
            PARA001_ID,
            FIGURE001_ID,
            TABLE001_ID,
        ]

    def test_manifest_iter_accepts_traversal_options(
        self, structured_manifest_path: Path,
    ) -> None:
        manifest = _load(structured_manifest_path)

        ids = [
            visit.node.id
            for visit in manifest.iter(
                stop_predicate=lambda node, _ctx: (
                    isinstance(node, HeadingNode) and node.level >= 2
                ),
            )
        ]

        assert ids == [HEADING001_ID, HEADING002_ID]

    def test_context_heading_path_is_propagated_to_descendants(
        self, structured_manifest_path: Path,
    ) -> None:
        manifest = _load(structured_manifest_path)

        paragraph_visit = next(
            visit
            for visit in manifest
            if isinstance(visit.node, ParagraphNode)
        )

        assert paragraph_visit.ctx.depth == 2
        assert paragraph_visit.ctx.heading_path == [
            "1 Description du système",
            "1.1 Paramètres nominaux",
        ]
        assert isinstance(paragraph_visit.ctx.parent, HeadingNode)
        assert paragraph_visit.ctx.parent.id == HEADING002_ID

    def test_stop_predicate_can_prune_descendants(
        self, structured_manifest_path: Path,
    ) -> None:
        manifest = _load(structured_manifest_path)

        ids = [
            visit.node.id
            for visit in manifest.iter(
                stop_predicate=lambda node, _ctx: (
                    isinstance(node, HeadingNode) and node.level >= 2
                ),
            )
        ]

        assert ids == [HEADING001_ID, HEADING002_ID]

    def test_max_depth_limits_descent(self, structured_manifest_path: Path) -> None:
        manifest = _load(structured_manifest_path)

        ids = [visit.node.id for visit in manifest.iter(max_depth=1)]

        assert ids == [HEADING001_ID, HEADING002_ID]

    def test_iter_nodes_accepts_a_node_subtree(
        self, structured_manifest_path: Path,
    ) -> None:
        manifest = _load(structured_manifest_path)
        section = manifest.nodes[0].children[0]
        assert isinstance(section, HeadingNode)

        ids = [visit.node.id for visit in iter_nodes([section])]

        assert ids == [HEADING002_ID, PARA001_ID, FIGURE001_ID, TABLE001_ID]

    def test_consumer_can_filter_by_node_type(
        self, minimal_manifest_path: Path,
    ) -> None:
        manifest = _load(minimal_manifest_path)

        texts = [
            visit.node.text
            for visit in manifest
            if isinstance(visit.node, ParagraphNode)
        ]

        assert texts == ["Premier paragraphe du document."]

    def test_table_nodes_are_included(self, structured_manifest_path: Path) -> None:
        manifest = _load(structured_manifest_path)

        tables = [
            visit.node
            for visit in manifest
            if isinstance(visit.node, TableNode)
        ]

        assert len(tables) == 1
        assert tables[0].id == TABLE001_ID


class TestFigureDescent:
    def test_iter_descends_into_figure_children(
        self, structured_manifest_path: Path,
    ) -> None:
        manifest = _load(structured_manifest_path)

        table_visit = next(
            visit for visit in manifest if isinstance(visit.node, TableNode)
        )

        assert table_visit.node.id == TABLE001_ID
        assert isinstance(table_visit.ctx.parent, FigureNode)
        assert table_visit.ctx.parent.id == FIGURE001_ID
        assert table_visit.ctx.depth == 3
        # A figure carries no heading_path of its own — children keep the
        # enclosing section's path.
        assert table_visit.ctx.heading_path == [
            "1 Description du système",
            "1.1 Paramètres nominaux",
        ]

    def test_stop_predicate_treats_figure_as_atomic(
        self, structured_manifest_path: Path,
    ) -> None:
        manifest = _load(structured_manifest_path)

        ids = [
            visit.node.id
            for visit in manifest.iter(
                stop_predicate=lambda node, _ctx: node.type == "figure",
            )
        ]

        assert FIGURE001_ID in ids
        assert TABLE001_ID not in ids
