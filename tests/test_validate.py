"""Every invariant `validate()` enforces, proved by a CND that breaks it.

A rule with only a passing case is not tested — it is asserted. Each
class below builds the smallest CND that violates one rule, so a
regression names itself.
"""

from datetime import datetime
from pathlib import Path
from uuid import UUID, uuid4

from cnd import (
    BibEntry,
    Cnd,
    DocMetadata,
    Footnote,
    FootnoteRef,
    HeadingNode,
    NodeLocation,
    NodeRef,
    ParagraphNode,
    validate,
)
from cnd.core.nodes import CiteRef

FIXTURES = Path(__file__).parent.parent / "fixtures"


def _cnd(nodes, **kwargs) -> Cnd:
    return Cnd(
        cnd_version="0.3.0",
        built_at=datetime(2026, 7, 22),
        doc=DocMetadata(title="T"),
        nodes=nodes,
        **kwargs,
    )


def _para(text: str = "p", **kwargs) -> ParagraphNode:
    return ParagraphNode(id=uuid4(), type="paragraph", text=text, **kwargs)


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
            footnotes=[Footnote(id=uuid4(), label="shared", text="n")],
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
            bibliography=[BibEntry(id=uuid4(), label="smith", formatted="Smith.")],
        )

        assert _rules(cnd) == ["link-wrong-domain"]

    def test_a_ref_may_not_resolve_to_a_pool_entry(self) -> None:
        cnd = _cnd(
            [_para(refs=[NodeRef(label="fn-a")])],
            footnotes=[Footnote(id=uuid4(), label="fn-a", text="n")],
        )

        assert _rules(cnd) == ["link-wrong-domain"]

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
            bibliography=[BibEntry(id=uuid4(), label="smith", formatted="Smith.")],
            footnotes=[Footnote(id=uuid4(), label="fn-a", text="n")],
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
                    text="H",
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
            bibliography=[BibEntry(id=uuid4(), label="a", formatted="Smith, J.")],
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
