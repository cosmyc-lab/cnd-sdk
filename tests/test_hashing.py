"""Content hashing (docs/adr/0016).

The tests that matter here are the *negative* ones: a hash is only
useful if it stays put under the changes it declares irrelevant. A test
that a hash changes when the text changes proves almost nothing.
"""

import json
import unicodedata
from datetime import datetime
from pathlib import Path
from uuid import uuid4

import pytest

from cnd import (
    BibEntry,
    Cnd,
    DocMetadata,
    Footnote,
    HeadingNode,
    Cell,
    LayoutNode,
    ListItem,
    ListNode,
    NodeLocation,
    Numbering,
    ParagraphNode,
    SourceInfo,
    TableNode,
    TermItem,
    TermsNode,
    content_hash,
    node_hash,
)
from cnd.core.hashing import _digest
from factories import rt

FIXTURES = Path(__file__).parent.parent / "fixtures"
VECTORS = FIXTURES / "hashes.json"


def _cnd(nodes, **kwargs) -> Cnd:
    return Cnd(
        cnd_version="0.5.0",
        built_at=datetime(2026, 7, 22),
        doc=DocMetadata(title="T"),
        nodes=nodes,
        **kwargs,
    )


def _para(text: str = "p", **kwargs) -> ParagraphNode:
    return ParagraphNode(id=uuid4(), type="paragraph", text=rt(text), **kwargs)


def _heading(text: str = "H", children=(), **kwargs) -> HeadingNode:
    return HeadingNode(
        id=uuid4(),
        type="heading",
        level=1,
        text=rt(text),
        heading_path=[text],
        children=list(children),
        **kwargs,
    )


class TestExcludedFromNodeHash:
    """Resolved presentation state must not move the hash."""

    def test_the_id_is_excluded(self) -> None:
        assert node_hash(_para("same")) == node_hash(_para("same"))

    def test_the_location_is_excluded(self) -> None:
        assert node_hash(_para("x", location=NodeLocation(page=1))) == node_hash(
            _para("x", location=NodeLocation(page=9))
        )
        assert node_hash(_para("x")) == node_hash(
            _para("x", location=NodeLocation(page=1))
        )

    def test_the_resolved_numbering_is_excluded(self) -> None:
        """The case that would break silently: inserting a heading
        renumbers every following node, and a hash covering `numbering`
        would report each of them as changed."""
        assert node_hash(_heading("H", numbering=Numbering(value="2.1"))) == node_hash(
            _heading("H", numbering=Numbering(value="3.1"))
        )

    def test_the_counter_name_is_excluded(self) -> None:
        """The counter word is part of `numbering` — it changes with the
        document language, not with the authored content."""
        assert node_hash(
            _heading("H", numbering=Numbering(value="1", name="Section"))
        ) == node_hash(_heading("H", numbering=Numbering(value="1", name="Abschnitt")))
        assert node_hash(_heading("H", numbering=Numbering(value="1"))) == node_hash(
            _heading("H", numbering=Numbering(value="1", name="Section"))
        )

    def test_children_are_excluded(self) -> None:
        """A heading whose subsection changed has not itself changed."""
        assert node_hash(_heading("H", children=[_para("a")])) == node_hash(
            _heading("H", children=[_para("b")])
        )


class TestCoveredByNodeHash:
    def test_the_text_is_covered(self) -> None:
        assert node_hash(_para("a")) != node_hash(_para("b"))

    def test_the_label_is_covered(self) -> None:
        assert node_hash(_para("x", label="a")) != node_hash(_para("x", label="b"))

    def test_the_type_is_covered(self) -> None:
        assert node_hash(_para("H")) != node_hash(_heading("H"))

    def test_link_labels_are_covered(self) -> None:
        from cnd import NodeRef

        def para(label):
            return ParagraphNode(
                id=uuid4(),
                type="paragraph",
                text=rt("x", refs=[NodeRef(label=label)]),
            )

        assert node_hash(para("a")) != node_hash(para("b"))


class TestUnicodeNormalisation:
    def test_nfc_and_nfd_of_the_same_text_hash_equal(self) -> None:
        nfd = unicodedata.normalize("NFD", "étalonnage")
        nfc = unicodedata.normalize("NFC", "étalonnage")

        assert nfd != nfc, "precondition: the two forms differ byte-wise"
        assert node_hash(_para(nfd)) == node_hash(_para(nfc))

    def test_normalisation_applies_to_keys_too(self) -> None:
        """JCS orders keys by code unit, so an unnormalised key would both
        order and serialise differently for the same name."""
        nfd_key = unicodedata.normalize("NFD", "clé")
        nfc_key = unicodedata.normalize("NFC", "clé")

        assert node_hash(_para("x", state_metadata={nfd_key: 1})) == node_hash(
            _para("x", state_metadata={nfc_key: 1})
        )


class TestContentHash:
    def test_built_at_is_excluded(self) -> None:
        a = _cnd([_para("x")])
        b = _cnd([_para("x")])
        b.built_at = datetime(2030, 1, 1)

        assert content_hash(a) == content_hash(b)

    def test_the_source_block_is_excluded(self) -> None:
        """The same content reached from two input formats is the same
        content; `source.hash` answers the other question."""
        a = _cnd([_para("x")], source=SourceInfo(type="typst", hash="sha256:aa"))
        b = _cnd([_para("x")], source=SourceInfo(type="markdown", hash="sha256:bb"))

        assert content_hash(a) == content_hash(b)

    def test_doc_metadata_is_covered(self) -> None:
        a = _cnd([_para("x")])
        b = _cnd([_para("x")])
        b.doc = DocMetadata(title="Other")

        assert content_hash(a) != content_hash(b)

    def test_reading_order_is_covered(self) -> None:
        assert content_hash(_cnd([_para("a"), _para("b")])) != content_hash(
            _cnd([_para("b"), _para("a")])
        )

    def test_renumbering_alone_does_not_change_the_document_hash(self) -> None:
        assert content_hash(
            _cnd([_heading("A", numbering=Numbering(value="1")), _heading("B", numbering=Numbering(value="2"))])
        ) == content_hash(
            _cnd([_heading("A", numbering=Numbering(value="2")), _heading("B", numbering=Numbering(value="3"))])
        )

    def test_repagination_alone_does_not_change_the_document_hash(self) -> None:
        page1, page2 = NodeLocation(page=1), NodeLocation(page=2)

        assert content_hash(_cnd([_para("a", location=page1)])) == content_hash(
            _cnd([_para("a", location=page2)])
        )

    def test_the_format_version_is_excluded(self) -> None:
        """The same content expressed under two format versions is the
        same content."""
        a = _cnd([_para("x")])
        b = _cnd([_para("x")])
        b.cnd_version = "9.9.9"

        assert content_hash(a) == content_hash(b)

    def test_a_rewritten_footnote_changes_the_document_hash(self) -> None:
        """The pools sit out of the tree for referencing reasons, not
        because they are metadata — their text is authored content."""
        a = _cnd([_para("x")], footnotes=[Footnote(id=uuid4(), label="a", children=[_para("one")])])
        b = _cnd([_para("x")], footnotes=[Footnote(id=uuid4(), label="a", children=[_para("two")])])

        assert content_hash(a) != content_hash(b)

    def test_an_edited_bibliography_entry_changes_the_document_hash(self) -> None:
        a = _cnd([_para("x")], bibliography=[BibEntry(id=uuid4(), label="s", title="A")])
        b = _cnd([_para("x")], bibliography=[BibEntry(id=uuid4(), label="s", title="B")])

        assert content_hash(a) != content_hash(b)

    def test_a_pool_entry_id_is_excluded(self) -> None:
        """Pool ids are as non-durable as node ids (docs/adr/0015)."""
        a = _cnd([_para("x")], footnotes=[Footnote(id=uuid4(), label="a", children=[_para("n")])])
        b = _cnd([_para("x")], footnotes=[Footnote(id=uuid4(), label="a", children=[_para("n")])])

        assert content_hash(a) == content_hash(b)

    def test_reparenting_changes_the_document_hash(self) -> None:
        """Reading order and every node-local hash are identical here;
        only the nesting differs, and nesting is structure."""
        flat = _cnd([_heading("H"), _para("a")])
        nested = _cnd([_heading("H", children=[_para("a")])])

        assert content_hash(flat) != content_hash(nested)


class TestDefaultsAreDropped:
    def test_hash_equals_the_minimal_payload(self) -> None:
        """Omitted and default-valued fields never enter the preimage, so a
        future optional field cannot move an existing hash."""
        assert node_hash(_para("x")) == _digest(
            {"type": "paragraph", "text": {"value": "x"}}
        )

    def test_explicit_empty_lists_hash_like_omitted_ones(self) -> None:
        with_lists = ParagraphNode.model_validate(
            {
                "id": str(uuid4()),
                "type": "paragraph",
                "text": {"value": "x", "marks": [], "refs": []},
            }
        )
        assert node_hash(with_lists) == node_hash(_para("x"))


class TestNestedNodesAreExcluded:
    def test_a_list_does_not_change_when_an_item_text_does(self) -> None:
        a = ListNode(id=uuid4(), type="list", items=[ListItem(children=[_para("one")])])
        b = ListNode(id=uuid4(), type="list", items=[ListItem(children=[_para("two")])])
        assert node_hash(a) == node_hash(b)

    def test_a_list_changes_when_a_checkbox_does(self) -> None:
        a = ListNode(id=uuid4(), type="list", items=[ListItem(checked=False)])
        b = ListNode(id=uuid4(), type="list", items=[ListItem(checked=True)])
        assert node_hash(a) != node_hash(b)

    def test_a_table_does_not_change_when_a_cell_content_does(self) -> None:
        a = TableNode(
            id=uuid4(), type="table", cells=[Cell(row=0, col=0, children=[_para("1")])]
        )
        b = TableNode(
            id=uuid4(), type="table", cells=[Cell(row=0, col=0, children=[_para("2")])]
        )
        assert node_hash(a) == node_hash(b)

    def test_a_term_is_the_terms_node_own_content(self) -> None:
        a = TermsNode(id=uuid4(), type="terms", items=[TermItem(term=rt("A"))])
        b = TermsNode(id=uuid4(), type="terms", items=[TermItem(term=rt("B"))])
        assert node_hash(a) != node_hash(b)

    def test_state_metadata_children_key_is_content(self) -> None:
        a = _para("x", state_metadata={"children": 1})
        b = _para("x", state_metadata={"children": 2})
        assert node_hash(a) != node_hash(b)

    def test_numbering_is_excluded(self) -> None:
        assert node_hash(_heading("H", numbering=Numbering(value="2.1"))) == node_hash(
            _heading("H", numbering=Numbering(value="3.1", name="Section"))
        )


class TestDocumentHashSeesStructure:
    def test_moving_a_paragraph_between_cells_changes_the_document(self) -> None:
        def grid(first, second):
            return LayoutNode(
                id=uuid4(),
                type="layout",
                cells=[
                    Cell(row=0, col=0, children=first),
                    Cell(row=0, col=1, children=second),
                ],
            )

        a = _cnd([grid([_para("x"), _para("y")], [])])
        b = _cnd([grid([_para("x")], [_para("y")])])
        assert content_hash(a) != content_hash(b)

    def test_editing_footnote_content_changes_the_document(self) -> None:
        def note(value):
            return Footnote(id=uuid4(), label="fn", children=[_para(value)])

        assert content_hash(_cnd([], footnotes=[note("a")])) != content_hash(
            _cnd([], footnotes=[note("b")])
        )


class TestNotSerialised:
    def test_no_hash_field_reaches_the_wire(self) -> None:
        cnd = _cnd([_para("x")])

        dumped = json.loads(cnd.model_dump_json())

        assert "content_hash" not in dumped
        assert all("node_hash" not in node for node in dumped["nodes"])


class TestConformanceVectors:
    """CND -> expected-hash vectors, so a non-Python implementation can
    prove it reproduces the same bytes (docs/adr/0016, docs/adr/0020)."""

    def _computed(self) -> dict:
        vectors = {}
        for path in sorted(FIXTURES.glob("*.cnd")):
            cnd = Cnd.model_validate_json(path.read_text())
            vectors[path.name] = {
                "content_hash": content_hash(cnd),
                "node_hashes": [node_hash(v.node) for v in cnd.iter_all()],
            }
        return vectors

    def test_vectors_match_the_committed_file(self) -> None:
        assert VECTORS.exists(), (
            "fixtures/hashes.json is missing — regenerate it with "
            "scripts/regen_hashes.py"
        )
        assert self._computed() == json.loads(VECTORS.read_text()), (
            "fixtures/hashes.json is out of sync. If a field moved in or out "
            "of the hashable subset this is expected — regenerate it. "
            "Otherwise the canonicalisation drifted, which breaks every "
            "implementation calibrated against the corpus."
        )

    def test_hashing_is_deterministic_across_reloads(self) -> None:
        assert self._computed() == self._computed()

    @pytest.mark.parametrize("name", [p.name for p in sorted(FIXTURES.glob("*.cnd"))])
    def test_every_fixture_has_a_vector(self, name: str) -> None:
        assert name in json.loads(VECTORS.read_text())


class TestExplicitDefaultsTwin:
    """``elements_explicit.cnd`` is ``elements.cnd`` with every default written
    out. Spec section 10 drops a field the schema declares with a default, so
    the two must hash alike: this is what lets another implementation prove it
    applies the rule rather than copying the SDK's field list."""

    def _load(self, name: str) -> Cnd:
        return Cnd.model_validate_json((FIXTURES / name).read_text())

    def test_the_twin_spells_out_what_the_original_omits(self) -> None:
        plain = (FIXTURES / "elements.cnd").read_text()
        explicit = (FIXTURES / "elements_explicit.cnd").read_text()
        assert len(explicit) > len(plain)
        assert '"marks": []' in explicit
        assert json.loads(explicit) != json.loads(plain)

    def test_the_content_hash_is_the_same(self) -> None:
        assert content_hash(self._load("elements_explicit.cnd")) == content_hash(
            self._load("elements.cnd")
        )

    def test_every_node_hash_matches_in_walk_order(self) -> None:
        plain = [node_hash(v.node) for v in self._load("elements.cnd").iter_all()]
        explicit = [
            node_hash(v.node) for v in self._load("elements_explicit.cnd").iter_all()
        ]
        assert explicit == plain
        assert len(plain) > 0
