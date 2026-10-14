"""SDK writers omit default-valued fields (docs/proposals/0013, "RichText
and the link families": every list defaults to empty and may be omitted).

``Cnd.to_json`` is the one place the SDK serializes a CND for a caller.
Two properties make the omission safe, and both are pinned here over the
whole fixture corpus: the written CND parses back to the same model, and
its content hash does not move (spec §10 drops defaults before hashing).
"""

import json
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

import pytest

from factories import para, rt

from cnd import Cnd, DocMetadata, HeadingNode, content_hash, node_hash

FIXTURES = Path(__file__).parent.parent / "fixtures"
CORPUS = sorted(FIXTURES.glob("*.cnd"))


def _load(path: Path) -> Cnd:
    return Cnd.model_validate_json(path.read_text())


def _cnd(nodes, **kwargs) -> Cnd:
    return Cnd(
        cnd_version="0.5.0",
        built_at=datetime(2026, 10, 14, tzinfo=timezone.utc),
        doc=DocMetadata(title="T"),
        nodes=nodes,
        **kwargs,
    )


@pytest.mark.parametrize("path", CORPUS, ids=lambda p: p.name)
class TestRoundTrip:
    def test_parse_of_write_is_the_same_cnd(self, path: Path) -> None:
        cnd = _load(path)
        # Compare dumps, not models: pydantic's __eq__ also compares the
        # private caches (labels, positions) a walk fills in.
        again = Cnd.model_validate_json(cnd.to_json())
        assert again.model_dump(mode="json") == cnd.model_dump(mode="json")

    def test_the_content_hash_does_not_move(self, path: Path) -> None:
        cnd = _load(path)
        again = Cnd.model_validate_json(cnd.to_json())
        assert content_hash(again) == content_hash(cnd)
        assert [node_hash(v.node) for v in again.iter_all()] == [
            node_hash(v.node) for v in cnd.iter_all()
        ]


class TestWhatIsOmitted:
    def test_a_plain_paragraph_is_its_value_alone(self) -> None:
        written = json.loads(_cnd([para("Hello.")]).to_json())
        assert written["nodes"][0]["text"] == {"value": "Hello."}

    def test_empty_pools_and_default_fields_are_omitted(self) -> None:
        written = json.loads(_cnd([para("x")]).to_json())
        assert "bibliography" not in written and "footnotes" not in written
        assert "source" not in written
        node = written["nodes"][0]
        assert set(node) == {"id", "type", "text"}

    def test_the_explicit_fixture_writes_like_the_plain_one(self) -> None:
        """elements_explicit.cnd spells every default out; written, it is
        the same document as elements.cnd, byte for byte."""
        explicit = _load(FIXTURES / "elements_explicit.cnd")
        plain = _load(FIXTURES / "elements.cnd")
        assert explicit.to_json() == plain.to_json()


class TestWhatAlwaysStays:
    def test_identity_version_and_build_time_stay(self) -> None:
        written = json.loads(_cnd([]).to_json())
        assert {"id", "cnd_version", "built_at", "doc", "nodes"} <= set(written)
        assert written["nodes"] == []

    def test_the_node_type_stays(self) -> None:
        written = json.loads(_cnd([para("x")]).to_json())
        assert written["nodes"][0]["type"] == "paragraph"

    def test_a_required_empty_list_stays(self) -> None:
        """``heading_path`` is required: an empty one is written, never
        dropped (spec §10, "A required field is never dropped")."""
        heading = HeadingNode(
            type="heading", id=uuid4(), level=1, text=rt("H"), heading_path=[]
        )
        written = json.loads(_cnd([heading]).to_json())
        assert written["nodes"][0]["heading_path"] == []

    def test_a_free_form_object_is_written_as_is(self) -> None:
        """Defaults are a schema concept: inside ``state_metadata`` an empty
        list or a null is content, and stays."""
        node = para("x", state_metadata={"children": [], "x": None})
        written = json.loads(_cnd([node]).to_json())
        assert written["nodes"][0]["state_metadata"] == {"children": [], "x": None}

    def test_an_empty_value_stays(self) -> None:
        written = json.loads(_cnd([para("")]).to_json())
        assert written["nodes"][0]["text"] == {"value": ""}


class TestFormat:
    def test_indent_and_unicode(self) -> None:
        text = _cnd([para("Système")]).to_json()
        assert "Système" in text
        assert text.startswith('{\n  "id": ')

    def test_compact_form(self) -> None:
        assert "\n" not in _cnd([para("x")]).to_json(indent=None)
