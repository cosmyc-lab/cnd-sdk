import json
from pathlib import Path

from ids import FIGURE001_ID, HEADING001_ID, HEADING002_ID, PARA001_ID, TABLE001_ID

from cnd.core.cnd import Cnd
from cnd.core.nodes import FigureNode, HeadingNode, ParagraphNode, TableNode, iter_nodes


def _load(path: Path) -> Cnd:
    return Cnd.model_validate_json(path.read_text())


class TestIterNodes:
    def test_cnd_is_directly_iterable(
        self, structured_cnd_path: Path,
    ) -> None:
        cnd = _load(structured_cnd_path)

        ids = [visit.node.id for visit in cnd]

        assert ids == [
            HEADING001_ID,
            HEADING002_ID,
            PARA001_ID,
            FIGURE001_ID,
            TABLE001_ID,
        ]

    def test_cnd_iter_accepts_traversal_options(
        self, structured_cnd_path: Path,
    ) -> None:
        cnd = _load(structured_cnd_path)

        ids = [
            visit.node.id
            for visit in cnd.iter(
                stop_predicate=lambda node, _ctx: (
                    isinstance(node, HeadingNode) and node.level >= 2
                ),
            )
        ]

        assert ids == [HEADING001_ID, HEADING002_ID]

    def test_context_heading_path_is_propagated_to_descendants(
        self, structured_cnd_path: Path,
    ) -> None:
        cnd = _load(structured_cnd_path)

        paragraph_visit = next(
            visit
            for visit in cnd
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
        self, structured_cnd_path: Path,
    ) -> None:
        cnd = _load(structured_cnd_path)

        ids = [
            visit.node.id
            for visit in cnd.iter(
                stop_predicate=lambda node, _ctx: (
                    isinstance(node, HeadingNode) and node.level >= 2
                ),
            )
        ]

        assert ids == [HEADING001_ID, HEADING002_ID]

    def test_max_depth_limits_descent(self, structured_cnd_path: Path) -> None:
        cnd = _load(structured_cnd_path)

        ids = [visit.node.id for visit in cnd.iter(max_depth=1)]

        assert ids == [HEADING001_ID, HEADING002_ID]

    def test_iter_nodes_accepts_a_node_subtree(
        self, structured_cnd_path: Path,
    ) -> None:
        cnd = _load(structured_cnd_path)
        section = cnd.nodes[0].children[0]
        assert isinstance(section, HeadingNode)

        ids = [visit.node.id for visit in iter_nodes([section])]

        assert ids == [HEADING002_ID, PARA001_ID, FIGURE001_ID, TABLE001_ID]

    def test_consumer_can_filter_by_node_type(
        self, minimal_cnd_path: Path,
    ) -> None:
        cnd = _load(minimal_cnd_path)

        texts = [
            visit.node.text
            for visit in cnd
            if isinstance(visit.node, ParagraphNode)
        ]

        assert texts == ["Premier paragraphe du document."]

    def test_table_nodes_are_included(self, structured_cnd_path: Path) -> None:
        cnd = _load(structured_cnd_path)

        tables = [
            visit.node
            for visit in cnd
            if isinstance(visit.node, TableNode)
        ]

        assert len(tables) == 1
        assert tables[0].id == TABLE001_ID


class TestFigureDescent:
    def test_iter_descends_into_figure_children(
        self, structured_cnd_path: Path,
    ) -> None:
        cnd = _load(structured_cnd_path)

        table_visit = next(
            visit for visit in cnd if isinstance(visit.node, TableNode)
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
        self, structured_cnd_path: Path,
    ) -> None:
        cnd = _load(structured_cnd_path)

        ids = [
            visit.node.id
            for visit in cnd.iter(
                stop_predicate=lambda node, _ctx: node.type == "figure",
            )
        ]

        assert FIGURE001_ID in ids
        assert TABLE001_ID not in ids


class TestDerivedPositions:
    """Reading-order positions (1-based x/y pairs) derived by the traversal
    engine — NodeLocation carries only `page`; everything else is computed."""

    def test_positions_on_structured_cnd(
        self, structured_cnd_path: Path,
    ) -> None:
        cnd = _load(structured_cnd_path)

        by_id = {v.node.id: v.ctx for v in cnd}

        # 5 nodes total, all beginning on page 1.
        para = by_id[PARA001_ID]
        assert (para.doc_index, para.doc_count) == (3, 5)
        assert (para.sibling_index, para.sibling_count) == (1, 2)
        assert (para.page_index, para.page_count) == (3, 5)

        table = by_id[TABLE001_ID]
        assert (table.doc_index, table.doc_count) == (5, 5)
        assert (table.sibling_index, table.sibling_count) == (1, 1)
        assert (table.page_index, table.page_count) == (5, 5)

        root = by_id[HEADING001_ID]
        assert (root.doc_index, root.sibling_index) == (1, 1)

    def test_page_positions_reset_per_page(
        self, comprehensive_cnd_path: Path,
    ) -> None:
        cnd = _load(comprehensive_cnd_path)

        for visit in cnd:
            assert 1 <= visit.ctx.page_index <= visit.ctx.page_count
            assert 1 <= visit.ctx.doc_index <= visit.ctx.doc_count
            assert 1 <= visit.ctx.sibling_index <= visit.ctx.sibling_count

        firsts = {}
        for visit in cnd:
            firsts.setdefault(visit.node.location.page, visit.ctx.page_index)
        assert all(index == 1 for index in firsts.values())

    def test_pruning_does_not_shift_positions(
        self, structured_cnd_path: Path,
    ) -> None:
        cnd = _load(structured_cnd_path)
        full = {v.node.id: v.ctx for v in cnd}

        pruned = {
            v.node.id: v.ctx
            for v in cnd.iter(
                stop_predicate=lambda node, _ctx: node.type == "heading"
                and node.level >= 2,
            )
        }

        # Positions are document facts: the nodes still visited report the
        # same indices and totals as in the unpruned walk.
        for node_id, ctx in pruned.items():
            assert (ctx.doc_index, ctx.doc_count) == (
                full[node_id].doc_index,
                full[node_id].doc_count,
            )
            assert (ctx.page_index, ctx.page_count) == (
                full[node_id].page_index,
                full[node_id].page_count,
            )

    def test_position_totals_helper(self, structured_cnd_path: Path) -> None:
        from cnd.core.nodes import position_totals

        cnd = _load(structured_cnd_path)
        doc_count, page_counts = position_totals(cnd.nodes)
        assert doc_count == 5
        assert page_counts == {1: 5}


class TestTraversalConformance:
    """The walk-order vectors spec §8 makes normative.

    Traversal is per-language by construction (docs/adr/0019), so two
    implementations can disagree invisibly — nothing in the file records
    the order they chose. These vectors are what make that detectable.
    """

    VECTORS = Path(__file__).parent.parent / "fixtures" / "traversal.json"

    def _computed(self) -> dict:
        fixtures_dir = Path(__file__).parent.parent / "fixtures"
        return {
            path.name: [
                {"id": str(v.node.id), "type": v.node.type, "depth": v.ctx.depth}
                for v in Cnd.model_validate_json(path.read_text()).iter()
            ]
            for path in sorted(fixtures_dir.glob("*.cnd"))
        }

    def test_vectors_match_the_committed_file(self) -> None:
        assert self._computed() == json.loads(self.VECTORS.read_text()), (
            "fixtures/traversal.json is out of sync — the walk order changed. "
            "If that was deliberate it is a spec change (§8), not a "
            "regeneration."
        )

    def test_pool_entries_never_enter_the_walk(self, rich_content_cnd_path) -> None:
        """Spec §8: a traversal yields nodes only. Pool entries are
        reached by resolving a link, never by iterating."""
        cnd = Cnd.model_validate_json(rich_content_cnd_path.read_text())
        pool_ids = {e.id for e in (*cnd.bibliography, *cnd.footnotes)}

        assert pool_ids, "precondition: the fixture has pool entries"
        assert pool_ids.isdisjoint({v.node.id for v in cnd.iter()})

    def test_a_node_precedes_its_children(self, full_coverage_cnd_path) -> None:
        cnd = Cnd.model_validate_json(full_coverage_cnd_path.read_text())
        seen: set = set()

        for visit in cnd.iter():
            if visit.ctx.parent is not None:
                assert visit.ctx.parent.id in seen
            seen.add(visit.node.id)
