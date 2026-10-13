"""Every invariant `validate()` enforces, proved by a CND that breaks it.

A rule with only a passing case is not tested — it is asserted. Each
class below builds the smallest CND that violates one rule, so a
regression names itself.
"""

from datetime import datetime
from pathlib import Path
from uuid import UUID, uuid4

from factories import rt

from cnd import (
    BibEntry,
    Cnd,
    DocMetadata,
    Footnote,
    FootnoteRef,
    HeadingNode,
    Mark,
    NodeLocation,
    NodeRef,
    ParagraphNode,
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
        for path in sorted(FIXTURES.glob("*.cnd")):
            cnd = Cnd.model_validate_json(path.read_text())
            assert validate(cnd) == [], f"{path.name}: {validate(cnd)}"


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
