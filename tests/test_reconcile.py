"""Reconciliation — matching v1 and the diff built on it (docs/adr/0018).

Two kinds of test live here. The per-pass tests pin *which* key matched a
pair, and each is built so that only the pass under test can match the
node in question — a labelled node that is unchanged and in place would
match under pass 2 as well, and would prove nothing about pass 1. The
scenario tests pin the classification a consumer sees, including the
failure the ADR documents rather than hides.
"""

import json
from datetime import datetime
from pathlib import Path
from uuid import UUID, uuid4

import pytest

from cnd import (
    BibEntry,
    Cnd,
    DocMetadata,
    Footnote,
    HeadingNode,
    NodeRef,
    ParagraphNode,
    validate,
)
from cnd.reconcile import (
    MATCHER_VERSION,
    ReconcileError,
    reconcile,
    CndDiff,
    diff,
    entries,
    match_nodes,
)


def _para(text: str, *, label: str | None = None, id: UUID | None = None):
    return ParagraphNode(
        type="paragraph", id=id or uuid4(), text=text, label=label
    )


def _heading(text: str, *, children=None, label: str | None = None):
    return HeadingNode(
        type="heading",
        id=uuid4(),
        level=1,
        text=text,
        label=label,
        heading_path=[text],
        children=list(children or []),
    )


def _cnd(nodes, *, bibliography=(), footnotes=()) -> Cnd:
    return Cnd(
        cnd_version="0.3.0",
        built_at=datetime(2026, 7, 23),
        doc=DocMetadata(title="T"),
        nodes=list(nodes),
        bibliography=list(bibliography),
        footnotes=list(footnotes),
    )


def _rebuild(cnd: Cnd) -> Cnd:
    """The same document built again: identical content, fresh ids.

    This is the situation reconciliation exists for — ids are not durable
    (docs/adr/0015), so a rebuild produces a CND whose every id is new.
    """
    rebuilt = cnd.model_copy(deep=True)
    for visit in rebuilt.iter():
        visit.node.id = uuid4()
    for entry in (*rebuilt.bibliography, *rebuilt.footnotes):
        entry.id = uuid4()
    return rebuilt


def _by_text(report: CndDiff, text: str):
    """The single change whose new-side node carries ``text``."""
    found = [
        change
        for change in report.nodes
        if change.new is not None and getattr(change.new.node, "text", None) == text
    ]
    assert len(found) == 1, f"expected one change for {text!r}, got {len(found)}"
    return found[0]


# --- structural paths -------------------------------------------------


def test_structural_path_is_absolute_sibling_indices():
    cnd = _cnd(
        [
            _para("first"),
            _heading("Section", children=[_para("nested"), _para("also nested")]),
        ]
    )
    assert [entry.path for entry in entries(cnd)] == [(1,), (2,), (2, 1), (2, 2)]


# --- one test per matching pass ---------------------------------------


def test_pass_1_label_matches_a_node_that_moved_and_was_edited():
    """Only the label can match this node: its hash changed and its slot
    moved, which defeats passes 2, 3 and 4."""
    old = _cnd([_para("intro"), _para("body", label="par-body")])
    new = _cnd(
        [
            _para("intro"),
            _para("inserted"),
            _para("body, rewritten", label="par-body"),
        ]
    )

    matching = match_nodes(old, new)
    labelled = [m for m in matching.matches if m.new.label == "par-body"]
    assert len(labelled) == 1
    assert labelled[0].matched_by == "label"
    assert diff(old, new).changed[0].new.label == "par-body"


def test_pass_2_hash_and_path_beats_reading_order_on_a_tie():
    """Two nodes share a hash; the path is what decides which one is which.

    Pass 3 alone would pair the surviving duplicate with the *first* old
    duplicate (reading order); pass 2 pairs it with the one in the same
    slot, so the inherited old node differs between the two answers.
    """
    first = _para("duplicate")
    second = _para("duplicate")
    old = _cnd([first, second])
    new = _cnd([_para("brand new"), _para("duplicate")])

    matching = match_nodes(old, new)
    paired = [m for m in matching.matches if m.new.path == (2,)]
    assert len(paired) == 1
    assert paired[0].matched_by == "hash+path"
    assert paired[0].old.node.id == second.id


def test_pass_3_hash_alone_recovers_a_node_an_insertion_shifted():
    old = _cnd([_para("alpha"), _para("beta")])
    new = _cnd([_para("inserted"), _para("alpha"), _para("beta")])

    matching = match_nodes(old, new)
    assert {m.matched_by for m in matching.matches} == {"hash"}
    assert [m.new.node.text for m in matching.matches] == ["alpha", "beta"]


def test_pass_4_path_and_type_matches_an_edit_in_place():
    """Unlabelled, edited (so no hash pass can fire), same slot and type."""
    old = _cnd([_para("keep me"), _para("original wording")])
    new = _cnd([_para("keep me"), _para("edited wording")])

    matching = match_nodes(old, new)
    by_pass = {m.matched_by: m for m in matching.matches}
    assert by_pass["path+type"].new.node.text == "edited wording"
    assert by_pass["hash+path"].new.node.text == "keep me"


def test_pass_4_does_not_match_a_different_type_in_the_same_slot():
    old = _cnd([_para("was a paragraph")])
    new = _cnd([_heading("Now a heading")])

    matching = match_nodes(old, new)
    assert matching.matches == ()
    assert len(matching.unmatched_old) == 1
    assert len(matching.unmatched_new) == 1


def test_pass_5_leaves_a_genuinely_new_node_unmatched():
    old = _cnd([_para("alpha")])
    new = _cnd([_para("alpha"), _para("appended")])

    report = diff(old, new)
    assert [change.new.node.text for change in report.added] == ["appended"]
    assert report.removed == ()


def test_equal_hash_ties_break_by_reading_order():
    """Three identical paragraphs shrink to two: the survivors take the
    first two old nodes, in reading order."""
    olds = [_para("same"), _para("same"), _para("same")]
    old = _cnd(olds)
    new = _cnd([_para("same"), _para("same")])

    matching = match_nodes(old, new)
    assert [m.old.node.id for m in matching.matches] == [olds[0].id, olds[1].id]
    assert [entry.node.id for entry in matching.unmatched_old] == [olds[2].id]


# --- scenarios --------------------------------------------------------


def test_rebuild_with_fresh_ids_is_entirely_unchanged():
    old = _cnd(
        [
            _para("intro"),
            _heading("Section", children=[_para("nested")]),
        ],
        bibliography=[BibEntry(id=uuid4(), label="smith2024", formatted="Smith 2024")],
        footnotes=[Footnote(id=uuid4(), label="fn-a", text="a note")],
    )
    new = _rebuild(old)

    report = diff(old, new)
    assert len(report.unchanged) == len(report.nodes) == 3
    assert report.is_empty
    assert report.matcher_version == MATCHER_VERSION
    # Every node was matched to a *different* id: the point of the pass.
    assert all(
        change.old.node.id != change.new.node.id for change in report.unchanged
    )


def test_editing_one_node_leaves_the_others_alone():
    old = _cnd([_para("alpha"), _para("beta"), _para("gamma")])
    new = _cnd([_para("alpha"), _para("beta, revised"), _para("gamma")])

    report = diff(old, new)
    assert [change.new.node.text for change in report.changed] == ["beta, revised"]
    assert [change.new.node.text for change in report.unchanged] == ["alpha", "gamma"]
    assert report.added == report.removed == ()
    assert _by_text(report, "beta, revised").matched_by == "path+type"


def test_inserting_at_the_top_shifts_the_rest_without_losing_them():
    """The inserted node is added; the shifted ones are recovered by pass 3
    and reported as moved — not as added/removed pairs."""
    old = _cnd([_para("alpha"), _para("beta")])
    new = _cnd([_para("inserted"), _para("alpha"), _para("beta")])

    report = diff(old, new)
    assert [change.new.node.text for change in report.added] == ["inserted"]
    assert [change.new.node.text for change in report.moved] == ["alpha", "beta"]
    assert report.removed == ()
    assert all(change.matched_by == "hash" for change in report.moved)


def test_moving_a_node_into_a_section_is_a_move_not_a_rewrite():
    body = _para("body")
    old = _cnd([body, _heading("Section")])
    new = _cnd([_heading("Section", children=[_para("body")])])

    report = diff(old, new)
    # The heading moved up a slot too, so both nodes are moved; only the
    # re-parented one is the subject here.
    assert {change.new.node.text for change in report.moved} == {"Section", "body"}
    change = _by_text(report, "body")
    assert change.status == "moved"
    assert change.old.path == (1,)
    assert change.new.path == (1, 1)
    assert change.old.node.id == body.id


def test_a_changed_node_that_also_moved_is_reported_as_changed():
    """``changed`` dominates ``moved``: the edit is the fact to act on."""
    old = _cnd([_para("alpha"), _para("beta", label="par-beta")])
    new = _cnd([_para("beta, revised", label="par-beta"), _para("alpha")])

    report = diff(old, new)
    assert [change.new.node.label for change in report.changed] == ["par-beta"]
    assert [change.new.node.text for change in report.moved] == ["alpha"]


def test_documented_limitation_edit_plus_insertion_above_defeats_the_matcher():
    """ADR 0018's documented failure, asserted rather than worked around.

    ``beta`` is edited *and* pushed down a slot by an insertion. It misses
    passes 2-3 (its content changed) and pass 4 (its slot moved), so it
    comes back as an added node with the old one removed. Labelling it
    would have made it exact — that is the whole point of the ADR 0015
    line between durable and best-effort identity.
    """
    old = _cnd([_para("alpha"), _para("beta"), _para("gamma")])
    new = _cnd(
        [_para("inserted"), _para("alpha"), _para("beta, revised"), _para("gamma")]
    )

    report = diff(old, new)
    assert sorted(change.new.node.text for change in report.added) == [
        "beta, revised",
        "inserted",
    ]
    assert [change.old.node.text for change in report.removed] == ["beta"]
    assert [change.new.node.text for change in report.moved] == ["alpha", "gamma"]
    assert report.changed == ()


def test_the_same_case_with_a_label_is_matched_exactly():
    """The counterpart to the limitation above: a label defeats it."""
    old = _cnd([_para("alpha"), _para("beta", label="par-beta"), _para("gamma")])
    new = _cnd(
        [
            _para("inserted"),
            _para("alpha"),
            _para("beta, revised", label="par-beta"),
            _para("gamma"),
        ]
    )

    report = diff(old, new)
    assert [change.new.node.text for change in report.added] == ["inserted"]
    assert report.removed == ()
    assert _by_text(report, "beta, revised").matched_by == "label"


def test_diff_order_is_new_reading_order_then_removals():
    old = _cnd([_para("alpha"), _para("dropped"), _para("gamma")])
    new = _cnd([_para("alpha"), _para("gamma")])

    report = diff(old, new)
    statuses = [change.status for change in report.nodes]
    assert statuses == ["unchanged", "moved", "removed"]


# --- pools ------------------------------------------------------------


def test_pool_entries_match_on_their_label_exactly():
    old = _cnd(
        [_para("alpha")],
        bibliography=[
            BibEntry(id=uuid4(), label="smith2024", formatted="Smith, 2024"),
            BibEntry(id=uuid4(), label="dropped2020", formatted="Gone, 2020"),
        ],
        footnotes=[Footnote(id=uuid4(), label="fn-a", text="a note")],
    )
    new = _cnd(
        [_para("alpha")],
        bibliography=[
            # Same label, rewritten: changed, never added/removed.
            BibEntry(id=uuid4(), label="smith2024", formatted="Smith, J. (2024)"),
            BibEntry(id=uuid4(), label="nguyen2023", formatted="Nguyen, 2023"),
        ],
        footnotes=[Footnote(id=uuid4(), label="fn-a", text="a note")],
    )

    report = diff(old, new)
    bib = report.bibliography
    assert [change.label for change in bib.changed] == ["smith2024"]
    assert [change.label for change in bib.added] == ["nguyen2023"]
    assert [change.label for change in bib.removed] == ["dropped2020"]
    assert [change.label for change in report.footnotes.unchanged] == ["fn-a"]
    assert not report.is_empty


def test_reordering_a_pool_changes_nothing():
    entry_a = BibEntry(id=uuid4(), label="a2020", formatted="A, 2020")
    entry_b = BibEntry(id=uuid4(), label="b2021", formatted="B, 2021")
    old = _cnd([_para("alpha")], bibliography=[entry_a, entry_b])
    new = _cnd([_para("alpha")], bibliography=[entry_b, entry_a])

    report = diff(old, new)
    assert len(report.bibliography.unchanged) == 2
    assert report.is_empty


@pytest.mark.parametrize("empty_side", ["old", "new"])
def test_diffing_against_an_empty_document(empty_side: str):
    populated = _cnd([_para("alpha"), _para("beta")])
    blank = _cnd([])
    old, new = (blank, populated) if empty_side == "old" else (populated, blank)

    report = diff(old, new)
    expected = "added" if empty_side == "old" else "removed"
    assert [change.status for change in report.nodes] == [expected, expected]


class TestConformanceVectors:
    """`(old, new) -> expected matching` vectors (docs/adr/0018, 0020 §4).

    Matching v1 is a versioned reference algorithm rather than a normative
    rule, and that is precisely why it needs vectors: a normative rule can
    be read off the spec, a heuristic can only be reproduced by pinning its
    output. A second implementation claiming "matching v1" reproduces these
    or it is running a different algorithm.
    """

    VECTORS = Path(__file__).parent.parent / "fixtures" / "matching.json"
    CASES = Path(__file__).parent.parent / "fixtures" / "reconcile"

    def _expected(self) -> dict:
        return json.loads(self.VECTORS.read_text())

    def _case(self, name: str) -> tuple[Cnd, Cnd]:
        directory = self.CASES / name
        return (
            Cnd.model_validate_json((directory / "old.cnd").read_text()),
            Cnd.model_validate_json((directory / "new.cnd").read_text()),
        )

    def test_every_case_reproduces_its_vector(self) -> None:
        expected = self._expected()
        assert expected["cases"], "precondition: the corpus has cases"

        for name, case in expected["cases"].items():
            old, new = self._case(name)
            report = diff(old, new)
            actual = [
                {
                    "status": change.status,
                    "matched_by": change.matched_by,
                    "old_id": str(change.old.node.id) if change.old else None,
                    "new_id": str(change.new.node.id) if change.new else None,
                }
                for change in report.nodes
            ]
            assert actual == case["nodes"], (
                f"{name}: matching drifted. If that was deliberate it is a "
                "new matcher version (ADR 0018), not a regeneration."
            )

    def test_the_vectors_declare_the_matcher_version(self) -> None:
        """A vector set without its version is unusable: matching v2 would
        legitimately produce different output."""
        assert self._expected()["matcher_version"] == MATCHER_VERSION

    def test_every_case_directory_has_a_vector(self) -> None:
        directories = {p.name for p in self.CASES.iterdir() if p.is_dir()}

        assert directories == set(self._expected()["cases"])

    def test_each_case_pair_is_itself_a_valid_cnd(self) -> None:
        """A vector built on a non-conformant CND would pin nonsense."""
        for name in self._expected()["cases"]:
            for cnd in self._case(name):
                assert validate(cnd) == [], name

    def test_the_documented_failure_is_pinned_as_a_failure(self) -> None:
        """ADR 0018's combined case: edited *and* shifted. The vector must
        record it missing, so nobody 'fixes' the corpus to hide it."""
        case = self._expected()["cases"]["06-combined-case-fails"]
        statuses = [node["status"] for node in case["nodes"]]

        assert "added" in statuses and "removed" in statuses

    def test_a_label_survives_edit_and_move_together(self) -> None:
        """The one exact claim the matcher makes."""
        case = self._expected()["cases"]["01-label-survives-edit-and-move"]
        labelled = [n for n in case["nodes"] if n["matched_by"] == "label"]

        assert len(labelled) == 1
        assert labelled[0]["status"] == "changed"


def _doc(nodes, **kwargs) -> Cnd:
    return Cnd(
        cnd_version="0.3.0",
        built_at=datetime(2026, 7, 23),
        doc=DocMetadata(title="T"),
        nodes=nodes,
        **kwargs,
    )


def _p(node_id: UUID, text: str, label: str | None = None) -> ParagraphNode:
    return ParagraphNode(id=node_id, type="paragraph", text=text, label=label)


class TestReconcile:
    """Id inheritance (docs/adr/0018)."""

    def test_a_matched_node_takes_the_previous_id(self) -> None:
        previous = _doc([_p(UUID(int=1), "alpha")])
        new = _doc([_p(UUID(int=99), "alpha")])

        result = reconcile(new, previous)

        assert [n.node.id for n in result.cnd.iter()] == [UUID(int=1)]
        assert result.inherited == 1 and result.minted == 0

    def test_an_unmatched_node_keeps_its_fresh_id(self) -> None:
        previous = _doc([_p(UUID(int=1), "alpha")])
        new = _doc([_p(UUID(int=1), "alpha"), _p(UUID(int=99), "brand new")])

        result = reconcile(new, previous)

        assert UUID(int=99) in {n.node.id for n in result.cnd.iter()}
        assert result.inherited == 1 and result.minted == 1

    def test_the_input_is_not_mutated(self) -> None:
        """A CND is an immutable build artifact; a pass that rewrote its
        argument in place would make the caller's own copy lie."""
        previous = _doc([_p(UUID(int=1), "alpha")])
        new = _doc([_p(UUID(int=99), "alpha")])

        reconcile(new, previous)

        assert [n.node.id for n in new.iter()] == [UUID(int=99)]

    def test_pool_entries_inherit_too(self) -> None:
        previous = _doc(
            [_p(UUID(int=1), "a")],
            footnotes=[Footnote(id=UUID(int=10), label="fn", text="note")],
        )
        new = _doc(
            [_p(UUID(int=1), "a")],
            footnotes=[Footnote(id=UUID(int=90), label="fn", text="edited")],
        )

        result = reconcile(new, previous)

        assert result.cnd.footnotes[0].id == UUID(int=10)

    def test_edges_need_no_rewriting(self) -> None:
        """Edges name their target by label (ADR 0017), so the remap never
        chases an id through a link family — the reason this is one final
        pass rather than a graph rewrite."""
        previous = _doc(
            [_p(UUID(int=1), "target", label="t"), _p(UUID(int=2), "source")]
        )
        new = _doc(
            [
                _p(UUID(int=91), "target", label="t"),
                ParagraphNode(
                    id=UUID(int=92),
                    type="paragraph",
                    text="source",
                    refs=[NodeRef(label="t")],
                ),
            ]
        )

        result = reconcile(new, previous)

        source = [n.node for n in result.cnd.iter() if n.node.refs][0]
        assert source.refs[0].label == "t"
        assert result.cnd.resolve("t").id == UUID(int=1)

    def test_only_exact_refuses_heuristic_pairings(self) -> None:
        """A caller who would rather mint a fresh id than inherit one on a
        heuristic's word."""
        previous = _doc([_p(UUID(int=1), "alpha"), _p(UUID(int=2), "beta", label="b")])
        new = _doc([_p(UUID(int=91), "alpha"), _p(UUID(int=92), "beta", label="b")])

        full = reconcile(new, previous)
        exact = reconcile(new, previous, only_exact=True)

        assert full.inherited == 2
        assert exact.inherited == 1
        assert exact.cnd.resolve("b").id == UUID(int=2)


class TestReconcileGuards:
    """The two assertions ADR 0018 requires before any remap is applied.

    Both are properties of the *matcher*. They are checked in `reconcile`
    rather than assumed precisely so a future matcher version that broke
    one fails loudly instead of corrupting a document.
    """

    def test_an_inherited_id_may_not_collide_with_a_kept_one(self) -> None:
        """Constructible: the node that inherits `previous`' id sits beside
        one whose fresh id already *is* that id. Applying the remap would
        give two nodes the same id and break global uniqueness (spec §2)."""
        previous = _doc([_p(UUID(int=1), "alpha")])
        new = _doc([_p(UUID(int=91), "alpha"), _p(UUID(int=1), "unmatched")])

        with pytest.raises(ReconcileError, match="collides"):
            reconcile(new, previous)

    def test_a_non_injective_remap_is_refused(self) -> None:
        """The matcher cannot produce this today — each old entry is
        consumed once — so the guard is exercised directly. A guard that
        can only be reached by a future bug still has to be known to
        work."""
        from cnd.reconcile.inherit import _check

        cnd = _doc([_p(UUID(int=91), "a"), _p(UUID(int=92), "b")])
        remap = {UUID(int=91): UUID(int=1), UUID(int=92): UUID(int=1)}

        with pytest.raises(ReconcileError, match="not injective"):
            _check(cnd, remap)

    def test_a_clean_remap_passes_both_guards(self) -> None:
        previous = _doc([_p(UUID(int=1), "alpha"), _p(UUID(int=2), "beta")])
        new = _doc([_p(UUID(int=91), "alpha"), _p(UUID(int=92), "beta")])

        assert reconcile(new, previous).inherited == 2


class TestReconcileAgainstTheCorpus:
    def test_every_vector_pair_reconciles_without_tripping_a_guard(self) -> None:
        cases = Path(__file__).parent.parent / "fixtures" / "reconcile"
        for directory in sorted(p for p in cases.iterdir() if p.is_dir()):
            previous = Cnd.model_validate_json((directory / "old.cnd").read_text())
            new = Cnd.model_validate_json((directory / "new.cnd").read_text())

            result = reconcile(new, previous)

            assert validate(result.cnd) == [], directory.name
            ids = [v.node.id for v in result.cnd.iter()]
            assert len(set(ids)) == len(ids), f"{directory.name}: duplicate ids"
