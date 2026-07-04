from pathlib import Path
from uuid import UUID

from ids import HEADING001_ID, HEADING002_ID, PARA001_ID, TABLE001_ID

from cnd.core.manifest import CndManifest
from cnd.core.nodes import CndNode, HeadingNode, NodeTraverseContext, ParagraphNode, TableNode
from cnd.visitors.base_visitor import BaseVisitor


def _load(path: Path) -> CndManifest:
    return CndManifest.model_validate_json(path.read_text())


class CollectIdsVisitor(BaseVisitor):
    def __init__(self) -> None:
        self.ids: list[UUID] = []

    def visit_heading(self, node: HeadingNode, _ctx: NodeTraverseContext) -> None:
        self.ids.append(node.id)

    def visit_paragraph(self, node: ParagraphNode, _ctx: NodeTraverseContext) -> None:
        self.ids.append(node.id)

    def visit_table(self, node: TableNode, _ctx: NodeTraverseContext) -> None:
        self.ids.append(node.id)


class CollectParagraphTextVisitor(BaseVisitor):
    def __init__(self) -> None:
        self.texts: list[str] = []

    def visit_paragraph(self, node: ParagraphNode, _ctx: NodeTraverseContext) -> None:
        self.texts.append(node.text)


class StopAtLevelTwoVisitor(BaseVisitor):
    def __init__(self) -> None:
        self.ids: list[UUID] = []

    def visit_heading(self, node: HeadingNode, _ctx: NodeTraverseContext) -> None:
        self.ids.append(node.id)

    def should_stop_descent(
        self,
        node: CndNode,
        _ctx: NodeTraverseContext,
    ) -> bool:
        return isinstance(node, HeadingNode) and node.level >= 2


class TestNodeVisitor:
    def test_default_visitor_visits_without_error(
        self, structured_manifest_path: Path,
    ) -> None:
        manifest = _load(structured_manifest_path)

        BaseVisitor().visit(manifest)

    def test_visit_dispatches_to_overridden_hooks(
        self, structured_manifest_path: Path,
    ) -> None:
        manifest = _load(structured_manifest_path)
        visitor = CollectIdsVisitor()

        visitor.visit(manifest)

        assert visitor.ids == [
            HEADING001_ID,
            HEADING002_ID,
            PARA001_ID,
            TABLE001_ID,
        ]

    def test_subclass_can_override_a_single_node_type(
        self, minimal_manifest_path: Path,
    ) -> None:
        manifest = _load(minimal_manifest_path)
        visitor = CollectParagraphTextVisitor()

        visitor.visit(manifest)

        assert visitor.texts == ["Premier paragraphe du document."]

    def test_should_stop_descent_prunes_branches(
        self, structured_manifest_path: Path,
    ) -> None:
        manifest = _load(structured_manifest_path)
        visitor = StopAtLevelTwoVisitor()

        visitor.visit(manifest)

        assert visitor.ids == [HEADING001_ID, HEADING002_ID]

    def test_visitor_can_visit_a_node_subtree(
        self, structured_manifest_path: Path,
    ) -> None:
        manifest = _load(structured_manifest_path)
        section = manifest.nodes[0].children[0]
        assert isinstance(section, HeadingNode)
        visitor = CollectIdsVisitor()

        visitor.visit([section])

        assert visitor.ids == [HEADING002_ID, PARA001_ID, TABLE001_ID]

    def test_current_node_and_ctx_are_tracked_during_visit(
        self,
        structured_manifest_path: Path,
    ) -> None:
        manifest = _load(structured_manifest_path)
        recorded: list[tuple[UUID, list[str], int]] = []

        class CurrentStateCollector(BaseVisitor):
            def visit_heading(self, node: HeadingNode, _ctx: NodeTraverseContext) -> None:
                self._record(node.id)

            def visit_paragraph(self, node: ParagraphNode, _ctx: NodeTraverseContext) -> None:
                self._record(node.id)

            def visit_table(self, node: TableNode, _ctx: NodeTraverseContext) -> None:
                self._record(node.id)

            def _record(self, node_id: UUID) -> None:
                assert self.current_node is not None
                assert self.current_ctx is not None
                assert self.current_node.id == node_id
                recorded.append((
                    node_id,
                    list(self.current_ctx.heading_path),
                    self.current_ctx.depth,
                ))

        CurrentStateCollector().visit(manifest)

        assert recorded == [
            (HEADING001_ID, [], 0),
            (HEADING002_ID, ["1 Description du système"], 1),
            (PARA001_ID, [
                "1 Description du système",
                "1.1 Paramètres nominaux",
            ], 2),
            (TABLE001_ID, [
                "1 Description du système",
                "1.1 Paramètres nominaux",
            ], 2),
        ]

    def test_context_is_passed_to_visit_hooks(
        self, structured_manifest_path: Path,
    ) -> None:
        manifest = _load(structured_manifest_path)
        contexts: list[NodeTraverseContext] = []

        class ContextCollector(BaseVisitor):
            def visit_paragraph(
                self,
                _node: ParagraphNode,
                ctx: NodeTraverseContext,
            ) -> None:
                contexts.append(ctx)

        ContextCollector().visit(manifest)

        assert len(contexts) == 1
        assert contexts[0].depth == 2
        assert contexts[0].heading_path == [
            "1 Description du système",
            "1.1 Paramètres nominaux",
        ]
        assert isinstance(contexts[0].parent, HeadingNode)
        assert contexts[0].parent.id == HEADING002_ID
