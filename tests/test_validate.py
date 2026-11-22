"""Every invariant `validate()` enforces, proved by a CND that breaks it.

A rule with only a passing case is not tested — it is asserted. Each
class below builds the smallest CND that violates one rule, so a
regression names itself.
"""

from datetime import datetime
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from factories import cell, para, rt
from pydantic import ValidationError

from cnd import (
    BibEntry,
    Cnd,
    DocMetadata,
    Footnote,
    FootnoteRef,
    HeadingNode,
    LayoutNode,
    ListNode,
    Mark,
    NodeLocation,
    NodeRef,
    ParagraphNode,
    TableNode,
    validate,
)
from cnd.core.text import CiteRef, LinkRef

FIXTURES = Path(__file__).parent.parent / "fixtures"


def _cnd(nodes, **kwargs) -> Cnd:
    return Cnd(
        cnd_version="0.5.0",
        built_at=datetime(2026, 7, 22),
        doc=DocMetadata(title="T"),
        nodes=nodes,
        **kwargs,
    )


_EDGE_FAMILIES = ("refs", "cites", "footnotes", "links")


def _para(text: str = "p", **kwargs) -> ParagraphNode:
    """A paragraph; edge families go into its RichText, the rest on the node."""
    edges = {k: kwargs.pop(k) for k in _EDGE_FAMILIES if k in kwargs}
    return ParagraphNode(id=uuid4(), type="paragraph", text=rt(text, **edges), **kwargs)


def _rules(cnd: Cnd) -> list[str]:
    return [v.rule for v in validate(cnd)]


class TestValidCorpus:
    def test_every_fixture_validates(self) -> None:
        """Every committed CND, the declaration and reconciliation fixtures
        included, parses under the closed models and breaks no rule."""
        paths = sorted(FIXTURES.rglob("*.cnd"))
        assert len(paths) > 20
        for path in paths:
            cnd = Cnd.model_validate_json(path.read_text())
            assert validate(cnd) == [], f"{path.relative_to(FIXTURES)}: {validate(cnd)}"


class TestLabelUniqueness:
    def test_two_nodes_may_not_share_a_label(self) -> None:
        cnd = _cnd([_para(label="dup"), _para(label="dup")])

        assert _rules(cnd) == ["label-not-unique"]

    def test_a_node_may_not_collide_with_a_pool_entry(self) -> None:
        cnd = _cnd(
            [_para(label="shared")],
            footnotes=[Footnote(id=uuid4(), label="shared", children=[_para("n")])],
        )

        assert _rules(cnd) == ["label-not-unique"]

    def test_unlabelled_nodes_never_collide(self) -> None:
        assert _rules(_cnd([_para(), _para(), _para()])) == []


class TestLinkDomains:
    def test_an_edge_to_a_label_nothing_carries_is_unresolved(self) -> None:
        cnd = _cnd([_para(refs=[NodeRef(label="absent")])])

        assert _rules(cnd) == ["link-unresolved"]

    def test_a_cite_may_not_resolve_to_a_node(self) -> None:
        """The label exists — labels are globally unique, so `resolve()`
        finds it. The family is what makes it wrong."""
        cnd = _cnd(
            [
                _para(label="sec-a"),
                _para(cites=[CiteRef(label="sec-a")]),
            ]
        )

        assert _rules(cnd) == ["link-wrong-domain"]

    def test_a_footnote_edge_may_not_resolve_to_a_bibliography_entry(self) -> None:
        cnd = _cnd(
            [_para(footnotes=[FootnoteRef(label="smith")])],
            bibliography=[BibEntry(id=uuid4(), label="smith", formatted=rt("Smith."))],
        )

        assert _rules(cnd) == ["link-wrong-domain"]

    def test_a_ref_may_not_resolve_to_a_pool_entry(self) -> None:
        cnd = _cnd(
            [_para(refs=[NodeRef(label="fn-a")])],
            footnotes=[Footnote(id=uuid4(), label="fn-a", children=[_para("n")])],
        )

        assert _rules(cnd) == ["link-wrong-domain"]

    def test_links_are_not_validated_against_the_label_index(self) -> None:
        """A `links` href naming nothing is valid: spec §5's normative
        resolution rule is scoped to the three label-keyed families."""
        cnd = _cnd([_para(links=[LinkRef(href="cnd://nothing-here")])])

        assert validate(cnd) == []

    def test_each_family_resolving_in_its_own_domain_is_clean(self) -> None:
        cnd = _cnd(
            [
                _para(label="target"),
                _para(
                    refs=[NodeRef(label="target")],
                    cites=[CiteRef(label="smith")],
                    footnotes=[FootnoteRef(label="fn-a")],
                ),
            ],
            bibliography=[BibEntry(id=uuid4(), label="smith", formatted=rt("Smith."))],
            footnotes=[Footnote(id=uuid4(), label="fn-a", children=[_para("n")])],
        )

        assert _rules(cnd) == []


class TestPagination:
    def test_all_located_is_valid(self) -> None:
        page = NodeLocation(page=1)
        assert _rules(_cnd([_para(location=page), _para(location=page)])) == []

    def test_none_located_is_valid(self) -> None:
        assert _rules(_cnd([_para(), _para()])) == []

    def test_a_partially_paginated_cnd_is_a_violation(self) -> None:
        cnd = _cnd([_para(location=NodeLocation(page=1)), _para()])

        assert _rules(cnd) == ["pagination-partial"]

    def test_the_violation_names_the_minority(self) -> None:
        """One unlocated node among many located ones is the anomaly; the
        report points at it rather than at the whole document."""
        page = NodeLocation(page=1)
        odd = _para("odd")
        cnd = _cnd([_para(location=page), _para(location=page), odd])

        [violation] = validate(cnd)

        assert str(odd.id) in violation.where
        assert "carry a location" in violation.message

    def test_a_child_without_a_location_is_caught(self) -> None:
        """Pagination is a whole-tree property, not a root-list one."""
        cnd = _cnd(
            [
                HeadingNode(
                    id=uuid4(),
                    type="heading",
                    level=1,
                    text=rt("H"),
                    heading_path=["H"],
                    location=NodeLocation(page=1),
                    children=[_para()],
                )
            ]
        )

        assert _rules(cnd) == ["pagination-partial"]


class TestBibliographyFloor:
    def test_an_entry_with_neither_formatted_nor_fields_is_empty(self) -> None:
        cnd = _cnd([_para()], bibliography=[BibEntry(id=uuid4(), label="a")])

        assert _rules(cnd) == ["bib-entry-empty"]

    def test_formatted_alone_satisfies_the_floor(self) -> None:
        cnd = _cnd(
            [_para()],
            bibliography=[BibEntry(id=uuid4(), label="a", formatted=rt("Smith, J."))],
        )

        assert _rules(cnd) == []

    def test_a_structured_field_alone_satisfies_the_floor(self) -> None:
        cnd = _cnd(
            [_para()],
            bibliography=[BibEntry(id=uuid4(), label="a", title="On data banks")],
        )

        assert _rules(cnd) == []

    def test_the_lossless_fields_dict_alone_satisfies_the_floor(self) -> None:
        cnd = _cnd(
            [_para()],
            bibliography=[BibEntry(id=uuid4(), label="a", fields={"type": "book"})],
        )

        assert _rules(cnd) == []


class TestReporting:
    def test_all_violations_are_returned_not_just_the_first(self) -> None:
        cnd = _cnd(
            [
                _para(label="dup"),
                _para(label="dup", refs=[NodeRef(label="absent")]),
            ],
            bibliography=[BibEntry(id=UUID(int=1), label="empty")],
        )

        assert set(_rules(cnd)) == {
            "label-not-unique",
            "link-unresolved",
            "bib-entry-empty",
        }

    def test_a_violation_renders_readably(self) -> None:
        cnd = _cnd([_para(refs=[NodeRef(label="absent")])])

        [violation] = validate(cnd)

        assert str(violation).startswith("[link-unresolved] @absent on paragraph ")


def _doc(nodes, **kw):
    return Cnd(
        cnd_version="0.5.0",
        built_at=datetime(2026, 10, 13),
        doc=kw.pop("doc", DocMetadata(title="T")),
        nodes=nodes,
        **kw,
    )


def _p(text, label=None):
    return ParagraphNode(id=uuid4(), type="paragraph", label=label, text=text)


class TestMarks:
    def test_a_valid_text_has_no_violation(self) -> None:
        text = rt("ab cd", marks=[Mark(start=0, end=2, kind="strong"), Mark(start=1, end=4, kind="emph")])
        assert _rules(_doc([_p(text)])) == []

    def test_bounds(self) -> None:
        for start, end in ((2, 2), (-1, 1), (0, 6)):
            text = rt("hello", marks=[Mark(start=start, end=end, kind="strong")])
            assert "mark-out-of-bounds" in _rules(_doc([_p(text)]))

    def test_an_empty_mark_says_so(self) -> None:
        text = rt("hello", marks=[Mark(start=2, end=2, kind="strong")])
        [violation] = validate(_doc([_p(text)]))
        assert violation.rule == "mark-out-of-bounds"
        assert "is empty" in violation.message
        assert "outside" not in violation.message

    def test_an_out_of_range_mark_says_outside(self) -> None:
        text = rt("hello", marks=[Mark(start=0, end=6, kind="strong")])
        [violation] = validate(_doc([_p(text)]))
        assert "is outside a text of 5 code points" in violation.message

    def test_canonical_order(self) -> None:
        text = rt("abcd", marks=[Mark(start=2, end=3, kind="emph"), Mark(start=0, end=1, kind="emph")])
        assert "mark-not-canonical" in _rules(_doc([_p(text)]))

    def test_same_kind_marks_that_touch_must_be_merged(self) -> None:
        text = rt("abcd", marks=[Mark(start=0, end=2, kind="strong"), Mark(start=2, end=4, kind="strong")])
        assert "mark-same-kind-overlap" in _rules(_doc([_p(text)]))

    def test_nothing_reaches_inside_an_atomic_mark(self) -> None:
        inside = rt("a = b", marks=[Mark(start=0, end=5, kind="math"), Mark(start=1, end=2, kind="strong")])
        partial_edge = rt("call fn now", marks=[Mark(start=5, end=7, kind="code")],
                          links=[{"href": "https://x.test", "text_span": [6, 11]}])
        for text in (inside, partial_edge):
            assert "mark-atomic-crossed" in _rules(_doc([_p(text)]))

    def test_a_span_covering_the_whole_atomic_mark_is_allowed(self) -> None:
        text = rt("run code now", marks=[Mark(start=0, end=12, kind="strong"), Mark(start=4, end=8, kind="code")],
                  links=[{"href": "https://x.test", "text_span": [4, 8]}])
        assert "mark-atomic-crossed" not in _rules(_doc([_p(text)]))


class TestSpansAndMetadata:
    def test_text_span_out_of_bounds(self) -> None:
        text = rt("short", links=[{"href": "https://x.test", "text_span": [2, 9]}])
        assert "text-span-out-of-bounds" in _rules(_doc([_p(text)]))

    def test_a_reversed_text_span_is_reported(self) -> None:
        text = rt("short", links=[{"href": "https://x.test", "text_span": [4, 2]}])
        assert "text-span-out-of-bounds" in _rules(_doc([_p(text)]))

    @pytest.mark.parametrize("span", [[1], [1, 2, 3], [-3, 4], [2, -1], []])
    @pytest.mark.parametrize("edge", [NodeRef, CiteRef, FootnoteRef])
    def test_a_malformed_text_span_is_a_shape_error(self, span, edge) -> None:
        """Two non-negative offsets is the shape (spec §5: "`[start, end)`
        array of 2 ints", "0 ≤ start"); the schema carries it, so a
        malformed span is refused on parse. Only the bound that depends on
        the text, ``end ≤ len(value)``, is left to ``validate()``."""
        with pytest.raises(ValidationError, match="text_span"):
            edge(label="x", text_span=span)
        with pytest.raises(ValidationError, match="text_span"):
            rt("short", links=[{"href": "https://x.test", "text_span": span}])

    def test_an_empty_label_edge_with_a_bad_span_is_reported(self) -> None:
        text = rt("short", refs=[NodeRef(label="", text_span=[2, 9])])
        assert "text-span-out-of-bounds" in _rules(_doc([_p(text)]))

    def test_extra_must_not_shadow_a_field(self) -> None:
        cnd = _doc([], doc=DocMetadata(title="T", status="Draft", extra={"status": "Final", "client": "A"}))
        assert _rules(cnd) == ["doc-extra-shadows-field"]


class TestFootnoteContent:
    def test_ids_are_unique_across_body_footnotes_and_pools(self) -> None:
        shared = uuid4()
        body = ParagraphNode(id=shared, type="paragraph", text=rt("body", footnotes=[{"label": "fn"}]))
        note = Footnote(id=uuid4(), label="fn", children=[ParagraphNode(id=shared, type="paragraph", text=rt("n"))])
        assert "id-not-unique" in _rules(_doc([body], footnotes=[note]))
        clash = Footnote(id=shared, label="fn", children=[])
        assert "id-not-unique" in _rules(_doc([body], footnotes=[clash]))

    def test_labels_inside_footnotes_join_global_uniqueness(self) -> None:
        note = Footnote(id=uuid4(), label="fn", children=[_p(rt("n"), label="dup")])
        cnd = _doc([_p(rt("body", footnotes=[{"label": "fn"}]), label="dup")], footnotes=[note])
        assert "label-not-unique" in _rules(cnd)

    def test_edges_inside_footnotes_must_resolve(self) -> None:
        note = Footnote(id=uuid4(), label="fn", children=[_p(rt("see", refs=[NodeRef(label="nowhere")]))])
        cnd = _doc([_p(rt("body", footnotes=[{"label": "fn"}]))], footnotes=[note])
        assert "link-unresolved" in _rules(cnd)

    def test_edges_inside_a_bibliography_entry_are_checked(self) -> None:
        entry = BibEntry(id=uuid4(), label="k", formatted=rt("K", refs=[NodeRef(label="nowhere")]))
        assert "link-unresolved" in _rules(_doc([], bibliography=[entry]))

    def test_the_elements_fixture_is_valid(self, elements_cnd_path) -> None:
        assert validate(Cnd.model_validate_json(elements_cnd_path.read_text())) == []


class TestCndVersion:
    """A CND built in code under another format version is not conformant
    to this one (spec §9, §11): the shape can coincide, the meaning not."""

    @pytest.mark.parametrize("version", ["0.4.0", "9.9.9"])
    def test_another_version_is_a_violation(self, version: str) -> None:
        cnd = _cnd([]).model_copy(update={"cnd_version": version})
        [violation] = validate(cnd)
        assert violation.rule == "cnd-version-unsupported"
        assert version in violation.where
        assert "0.5.0" in violation.message

    def test_the_current_version_is_fine(self) -> None:
        assert validate(_cnd([])) == []


def _heading(text: str, level: int, path: list[str], children=()) -> HeadingNode:
    return HeadingNode(
        id=uuid4(), type="heading", level=level, text=rt(text),
        heading_path=path, children=list(children),
    )


class TestHeadingLevel:
    """A heading level is 1 or more, with no upper bound (spec §6.1): a
    source such as Typst nests deeper than six. The schema carries the
    minimum, so a level below it is a shape error."""

    @pytest.mark.parametrize("level", [0, -1])
    def test_a_level_below_one_is_refused(self, level: int) -> None:
        with pytest.raises(ValidationError, match="level"):
            _heading("H", level, ["H"])

    @pytest.mark.parametrize("level", [1, 6, 7, 12])
    def test_any_level_from_one_up_is_valid(self, level: int) -> None:
        assert _rules(_cnd([_heading("H", level, ["H"])])) == []

    def test_the_schema_states_the_minimum_only(self) -> None:
        import json

        schema = json.loads((FIXTURES.parent / "schema" / "cnd.schema.json").read_text())
        level = schema["$defs"]["HeadingNode"]["properties"]["level"]
        assert level["minimum"] == 1
        assert "maximum" not in level


class TestHeadingPath:
    """A heading's ``heading_path`` is the path of its nearest enclosing
    heading plus one element for itself, through any container; a
    footnote's headings start a path of their own. What an element holds
    (numbered or bare text) is the producer's, and is not checked."""

    def test_a_consistent_tree_is_valid(self) -> None:
        deepest = _heading("D", 3, ["1 A", "B", "D"])
        inner = _heading("B", 2, ["1 A", "B"], [deepest])
        listed = ListNode(
            id=uuid4(), type="list",
            items=[{"children": [_heading("C", 2, ["1 A", "C"])]}],
        )
        outer = _heading("A", 1, ["1 A"], [inner, listed])
        assert _rules(_cnd([outer, _heading("E", 1, ["E"])])) == []

    def test_a_top_level_heading_has_a_one_element_path(self) -> None:
        assert _rules(_cnd([_heading("A", 1, ["Root", "A"])])) == ["heading-path-mismatch"]

    def test_an_empty_path_is_a_mismatch(self) -> None:
        assert _rules(_cnd([_heading("A", 1, [])])) == ["heading-path-mismatch"]

    def test_a_child_must_extend_its_parent_path(self) -> None:
        child = _heading("B", 2, ["Other", "B"])
        cnd = _cnd([_heading("A", 1, ["A"], [child])])

        [violation] = validate(cnd)

        assert violation.rule == "heading-path-mismatch"
        assert str(child.id) in violation.where

    def test_a_skipped_ancestor_is_a_mismatch(self) -> None:
        child = _heading("B", 2, ["B"])
        assert _rules(_cnd([_heading("A", 1, ["A"], [child])])) == ["heading-path-mismatch"]

    def test_the_path_threads_through_a_table_cell(self) -> None:
        table = TableNode(
            id=uuid4(), type="table",
            cells=[cell(0, 0, children=[_heading("In cell", 2, ["In cell"])])],
        )
        assert _rules(_cnd([_heading("A", 1, ["A"], [table])])) == ["heading-path-mismatch"]
        table.cells[0].children[0].heading_path = ["A", "In cell"]
        assert _rules(_cnd([_heading("A", 1, ["A"], [table])])) == []

    def test_a_footnote_heading_starts_its_own_path(self) -> None:
        good = Footnote(id=uuid4(), label="fn", children=[_heading("N", 1, ["N"])])
        bad = Footnote(id=uuid4(), label="fn2", children=[_heading("N2", 1, ["A", "N2"])])
        body = _heading("A", 1, ["A"], [_p(rt("x", footnotes=[{"label": "fn"}, {"label": "fn2"}]))])

        assert _rules(_cnd([body], footnotes=[good, bad])) == ["heading-path-mismatch"]

    def test_one_wrong_heading_is_reported_once_not_for_its_subtree(self) -> None:
        """A child is checked against its parent's path as written, so a
        wrong parent does not cascade into its consistent descendants."""
        child = _heading("B", 2, ["X", "Wrong", "B"])
        parent = _heading("A", 1, ["X", "Wrong"], [child])

        [violation] = validate(_cnd([parent]))

        assert violation.rule == "heading-path-mismatch"
        assert str(parent.id) in violation.where


def _table(*cells, kind=TableNode) -> TableNode:
    return kind(id=uuid4(), type="table" if kind is TableNode else "layout", cells=list(cells))


class TestCellGrid:
    """A grid position is covered by at most one cell, spans included."""

    @pytest.mark.parametrize(("row", "col"), [(-1, 0), (0, -1)])
    def test_a_negative_coordinate_is_refused(self, row: int, col: int) -> None:
        with pytest.raises(ValidationError):
            cell(row, col)

    def test_the_schema_states_the_coordinate_minimum(self) -> None:
        import json

        schema = json.loads((FIXTURES.parent / "schema" / "cnd.schema.json").read_text())
        props = schema["$defs"]["Cell"]["properties"]
        assert props["row"]["minimum"] == 0
        assert props["col"]["minimum"] == 0

    @pytest.mark.parametrize("kind", [TableNode, LayoutNode])
    def test_a_full_grid_with_spans_is_valid(self, kind) -> None:
        grid = _table(
            cell(0, 0, "a", colspan=2), cell(0, 2, "b"),
            cell(1, 0, "c", rowspan=2), cell(1, 1, "d"), cell(1, 2, "e"),
            cell(2, 1, "f", colspan=2),
            kind=kind,
        )
        assert _rules(_cnd([grid])) == []

    @pytest.mark.parametrize("kind", [TableNode, LayoutNode])
    def test_two_cells_at_the_same_position(self, kind) -> None:
        grid = _table(cell(0, 0, "a"), cell(0, 1, "b"), cell(0, 0, "c"), kind=kind)

        [violation] = validate(_cnd([grid]))

        assert violation.rule == "cell-overlap"
        assert str(grid.id) in violation.where
        assert "cell 2" in violation.where

    def test_a_colspan_reaching_over_the_next_cell(self) -> None:
        grid = _table(cell(0, 0, "a", colspan=2), cell(0, 1, "b"))
        assert _rules(_cnd([grid])) == ["cell-overlap"]

    def test_a_rowspan_reaching_over_a_cell_below(self) -> None:
        grid = _table(cell(0, 0, "a", rowspan=3), cell(0, 1, "b"), cell(2, 0, "c"))
        assert _rules(_cnd([grid])) == ["cell-overlap"]

    def test_two_spanning_cells_crossing(self) -> None:
        grid = _table(cell(0, 1, "a", rowspan=3), cell(1, 0, "b", colspan=3))
        assert _rules(_cnd([grid])) == ["cell-overlap"]

    def test_each_overlapping_cell_is_reported(self) -> None:
        grid = _table(cell(0, 0, "a", colspan=3), cell(0, 1, "b"), cell(0, 2, "c"))
        assert _rules(_cnd([grid])) == ["cell-overlap", "cell-overlap"]

    def test_a_huge_span_is_checked_without_expanding_it(self) -> None:
        """Rectangles are compared, never filled in, so a span of a
        billion rows costs what a span of one does."""
        import time

        far = 10**9
        clean = _table(cell(0, 0, "a", rowspan=far, colspan=far), cell(far, far, "b"))
        clash = _table(cell(0, 0, "a", rowspan=far, colspan=far), cell(far - 1, 5, "b"))
        start = time.perf_counter()
        assert _rules(_cnd([clean])) == []
        assert _rules(_cnd([clash])) == ["cell-overlap"]
        assert time.perf_counter() - start < 1

    def test_a_grid_inside_a_footnote_is_checked(self) -> None:
        note = Footnote(id=uuid4(), label="fn", children=[_table(cell(0, 0, "a"), cell(0, 0, "b"))])
        body = _p(rt("x", footnotes=[{"label": "fn"}]))
        assert _rules(_cnd([body], footnotes=[note])) == ["cell-overlap"]

    def test_many_cells_in_one_row_stay_fast(self) -> None:
        import time

        grid = _table(*(cell(0, col) for col in range(20_000)), cell(0, 19_999))
        start = time.perf_counter()
        assert _rules(_cnd([grid])) == ["cell-overlap"]
        assert time.perf_counter() - start < 10  # catches quadratic growth, not speed
