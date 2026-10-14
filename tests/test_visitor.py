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


class _PathsVisitor(BaseVisitor):
    """Records each visited node's text, path and slot."""

    def __init__(self) -> None:
        self.seen: list[tuple[str, tuple, str | None]] = []

    def visit_paragraph(self, node: ParagraphNode, ctx: NodeTraverseContext) -> None:
        self.seen.append((node.text.value, ctx.path, ctx.slot))

    def visit_quote(self, node, ctx: NodeTraverseContext) -> None:
        self.seen.append(("quote", ctx.path, ctx.slot))


def _cnd_with_a_note() -> Cnd:
    from datetime import datetime, timezone
    from uuid import uuid4

    from factories import para

    from cnd.core.cnd import DocMetadata, Footnote
    from cnd.core.nodes import QuoteNode

    return Cnd(
        cnd_version="0.5.0",
        built_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        doc=DocMetadata(title="T"),
        nodes=[para("body")],
        footnotes=[
            Footnote(id=uuid4(), label="fn-a", children=[para("note a")]),
            Footnote(
                id=uuid4(),
                label="fn-b",
                children=[
                    QuoteNode(id=uuid4(), type="quote", children=[para("quoted")])
                ],
            ),
        ],
    )


class TestFullWalk:
    """``visit(cnd, full=True)`` is the full walk of spec §8: the body,
    then each footnote's content, with document paths and the footnote
    slot. Walking ``cnd.footnotes[i].children`` by hand would give
    ``("nodes", 0)`` paths that point into the body."""

    def test_the_default_walk_is_the_body_only(self) -> None:
        visitor = _PathsVisitor()
        visitor.visit(_cnd_with_a_note())
        assert visitor.seen == [("body", ("nodes", 0), None)]

    def test_full_walk_visits_footnote_content_with_spec_paths(self) -> None:
        visitor = _PathsVisitor()
        visitor.visit(_cnd_with_a_note(), full=True)
        assert visitor.seen == [
            ("body", ("nodes", 0), None),
            ("note a", ("footnotes", 0, "children", 0), "footnotes"),
            ("quote", ("footnotes", 1, "children", 0), "footnotes"),
            ("quoted", ("footnotes", 1, "children", 0, "children", 0), "children"),
        ]

    def test_full_walk_matches_iter_all(self) -> None:
        cnd = _cnd_with_a_note()
        visitor = _PathsVisitor()
        visitor.visit(cnd, full=True)
        assert [path for _, path, _ in visitor.seen] == [
            visit.ctx.path for visit in cnd.iter_all()
        ]

    def test_pruning_reaches_into_footnotes(self) -> None:
        class NoQuoteContent(_PathsVisitor):
            def should_stop_descent(self, node, ctx) -> bool:
                return node.type == "quote"

        visitor = NoQuoteContent()
        visitor.visit(_cnd_with_a_note(), full=True)
        assert "quoted" not in [text for text, _, _ in visitor.seen]
        assert "quote" in [text for text, _, _ in visitor.seen]

    def test_full_needs_a_cnd(self) -> None:
        from factories import para

        with pytest.raises(ValueError, match="full"):
            _PathsVisitor().visit([para("x")], full=True)
