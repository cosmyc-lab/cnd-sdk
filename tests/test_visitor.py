from pathlib import Path
from typing import get_args
from uuid import UUID

import pytest

from ids import (
    HEADING001_ID,
    HEADING002_ID,
    PARA001_ID,
    TABLE001_CELL_PARA_IDS,
    TABLE001_ID,
)

from cnd.core.cnd import Cnd
from cnd.core.nodes import (
    AdmonitionNode,
    CndNode,
    HeadingNode,
    LayoutNode,
    NodeTraverseContext,
    ParagraphNode,
    TableNode,
)
from cnd.visitors.base_visitor import BaseVisitor


def _load(path: Path) -> Cnd:
    return Cnd.model_validate_json(path.read_text())


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
        self.texts.append(node.text.value)


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
        self, structured_cnd_path: Path,
    ) -> None:
        cnd = _load(structured_cnd_path)

        BaseVisitor().visit(cnd)

    def test_visit_dispatches_to_overridden_hooks(
        self, structured_cnd_path: Path,
    ) -> None:
        cnd = _load(structured_cnd_path)
        visitor = CollectIdsVisitor()

        visitor.visit(cnd)

        # The table's cells hold paragraphs, visited after the table.
        assert visitor.ids == [
            HEADING001_ID,
            HEADING002_ID,
            PARA001_ID,
            TABLE001_ID,
            *TABLE001_CELL_PARA_IDS,
        ]

    def test_subclass_can_override_a_single_node_type(
        self, minimal_cnd_path: Path,
    ) -> None:
        cnd = _load(minimal_cnd_path)
        visitor = CollectParagraphTextVisitor()

        visitor.visit(cnd)

        assert visitor.texts == ["Premier paragraphe du document."]

    def test_should_stop_descent_prunes_branches(
        self, structured_cnd_path: Path,
    ) -> None:
        cnd = _load(structured_cnd_path)
        visitor = StopAtLevelTwoVisitor()

        visitor.visit(cnd)

        assert visitor.ids == [HEADING001_ID, HEADING002_ID]

    def test_visitor_can_visit_a_node_subtree(
        self, structured_cnd_path: Path,
    ) -> None:
        cnd = _load(structured_cnd_path)
        section = cnd.nodes[0].children[0]
        assert isinstance(section, HeadingNode)
        visitor = CollectIdsVisitor()

        visitor.visit([section])

        assert visitor.ids == [
            HEADING002_ID,
            PARA001_ID,
            TABLE001_ID,
            *TABLE001_CELL_PARA_IDS,
        ]

    def test_current_node_and_ctx_are_tracked_during_visit(
        self,
        structured_cnd_path: Path,
    ) -> None:
        cnd = _load(structured_cnd_path)
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

        CurrentStateCollector().visit(cnd)

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
            ], 3),
            *[
                (cell_para_id, [
                    "1 Description du système",
                    "1.1 Paramètres nominaux",
                ], 4)
                for cell_para_id in TABLE001_CELL_PARA_IDS
            ],
        ]

    def test_context_is_passed_to_visit_hooks(
        self, structured_cnd_path: Path,
    ) -> None:
        cnd = _load(structured_cnd_path)
        contexts: list[NodeTraverseContext] = []

        class ContextCollector(BaseVisitor):
            def visit_paragraph(
                self,
                _node: ParagraphNode,
                ctx: NodeTraverseContext,
            ) -> None:
                contexts.append(ctx)

        ContextCollector().visit(cnd)

        # PARA001, then the four cell paragraphs.
        assert len(contexts) == 5
        assert contexts[0].depth == 2
        assert contexts[0].heading_path == [
            "1 Description du système",
            "1.1 Paramètres nominaux",
        ]
        assert isinstance(contexts[0].parent, HeadingNode)
        assert contexts[0].parent.id == HEADING002_ID


    def test_a_cell_paragraph_has_the_table_as_parent(
        self, structured_cnd_path: Path,
    ) -> None:
        cnd = _load(structured_cnd_path)
        parents: list[tuple[UUID, str | None, int | None]] = []

        class CellParents(BaseVisitor):
            def visit_paragraph(
                self, node: ParagraphNode, ctx: NodeTraverseContext,
            ) -> None:
                if isinstance(ctx.parent, TableNode):
                    parents.append((ctx.parent.id, ctx.slot, ctx.slot_index))

        CellParents().visit(cnd)

        assert parents == [(TABLE001_ID, "cells", index) for index in range(4)]


class TestEveryNodeType:
    """One hook per node type of the 0.5 model, and no type falls through
    to ``visit_unknown``."""

    @pytest.mark.parametrize(
        "node_type",
        [
            model.model_fields["type"].annotation.__args__[0]
            for model in get_args(get_args(CndNode)[0])
        ],
    )
    def test_there_is_a_hook_for_the_type(self, node_type: str) -> None:
        assert callable(getattr(BaseVisitor, f"visit_{node_type}"))

    def test_the_elements_fixture_visits_without_falling_through(
        self, elements_cnd_path: Path,
    ) -> None:
        seen: list[str] = []

        class Recorder(BaseVisitor):
            def visit_admonition(
                self, node: AdmonitionNode, ctx: NodeTraverseContext,
            ) -> None:
                seen.append("admonition")

            def visit_layout(
                self, node: LayoutNode, ctx: NodeTraverseContext,
            ) -> None:
                seen.append("layout")

        Recorder().visit(_load(elements_cnd_path))

        assert seen == ["admonition", "layout"]
