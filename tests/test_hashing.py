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
    NodeLocation,
    ParagraphNode,
    SourceInfo,
    content_hash,
    node_hash,
)

FIXTURES = Path(__file__).parent.parent / "fixtures"
VECTORS = FIXTURES / "hashes.json"


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


def _heading(text: str = "H", children=(), **kwargs) -> HeadingNode:
    return HeadingNode(
        id=uuid4(),
        type="heading",
        level=1,
        text=text,
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

    def test_the_resolved_number_is_excluded(self) -> None:
        """The case that would break silently: inserting a heading
        renumbers every following node, and a hash covering `number`
        would report each of them as changed."""
        assert node_hash(_heading("H", number="2.1")) == node_hash(
            _heading("H", number="3.1")
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

        assert node_hash(_para("x", refs=[NodeRef(label="a")])) != node_hash(
            _para("x", refs=[NodeRef(label="b")])
        )


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
            _cnd([_heading("A", number="1"), _heading("B", number="2")])
        ) == content_hash(
            _cnd([_heading("A", number="2"), _heading("B", number="3")])
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
        a = _cnd([_para("x")], footnotes=[Footnote(id=uuid4(), label="a", text="one")])
        b = _cnd([_para("x")], footnotes=[Footnote(id=uuid4(), label="a", text="two")])

        assert content_hash(a) != content_hash(b)

    def test_an_edited_bibliography_entry_changes_the_document_hash(self) -> None:
        a = _cnd([_para("x")], bibliography=[BibEntry(id=uuid4(), label="s", title="A")])
        b = _cnd([_para("x")], bibliography=[BibEntry(id=uuid4(), label="s", title="B")])

        assert content_hash(a) != content_hash(b)

    def test_a_pool_entry_id_is_excluded(self) -> None:
        """Pool ids are as non-durable as node ids (docs/adr/0015)."""
        a = _cnd([_para("x")], footnotes=[Footnote(id=uuid4(), label="a", text="n")])
        b = _cnd([_para("x")], footnotes=[Footnote(id=uuid4(), label="a", text="n")])

        assert content_hash(a) == content_hash(b)

    def test_reparenting_changes_the_document_hash(self) -> None:
        """Reading order and every node-local hash are identical here;
        only the nesting differs, and nesting is structure."""
        flat = _cnd([_heading("H"), _para("a")])
        nested = _cnd([_heading("H", children=[_para("a")])])

        assert content_hash(flat) != content_hash(nested)


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
                "node_hashes": [node_hash(v.node) for v in cnd.iter()],
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
