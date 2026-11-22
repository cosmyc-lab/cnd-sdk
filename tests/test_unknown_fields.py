"""A CND object carries the fields the format defines and nothing else.

A key the models do not know used to be dropped without a word, so a
producer's typo (``captoin`` for ``caption``) or a field from another
format version vanished on parse and the CND still validated. Every
object of a CND now refuses an unknown key, as the declaration already
did for its own nodes. The free-form bags (``state_metadata``,
``BibEntry.fields``, ``doc.extra``) are dict-typed and still hold any
key.
"""

import copy
import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from cnd import Cnd

ROOT = Path(__file__).parent.parent
FIXTURES = ROOT / "fixtures"
SCHEMA = ROOT / "schema" / "cnd.schema.json"

_FREE_FORM_BAGS = {"state_metadata", "fields", "extra"}
_STRAY = "zz_unknown_field"


def _object_paths(value, path=()):
    """Every JSON object of a CND, with its path, outside the free-form bags."""
    if isinstance(value, dict):
        yield path, value
        for key, child in value.items():
            if key not in _FREE_FORM_BAGS:
                yield from _object_paths(child, (*path, key))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            yield from _object_paths(child, (*path, index))


def _injection_cases():
    """One case per distinct object shape across every fixture: the stray
    key goes into that one object and nowhere else."""
    cases, seen = [], set()
    for fixture in sorted(FIXTURES.rglob("*.cnd")):
        raw = json.loads(fixture.read_text())
        for path, obj in _object_paths(raw):
            parent = next((p for p in reversed(path) if isinstance(p, str)), "$")
            shape = (parent, tuple(sorted(obj)))
            if shape in seen:
                continue
            seen.add(shape)
            cases.append(
                pytest.param(fixture, path, id=f"{fixture.relative_to(FIXTURES)}:{'.'.join(map(str, path)) or '$'}")
            )
    return cases


def _set_stray(raw: dict, path: tuple) -> dict:
    out = copy.deepcopy(raw)
    target = out
    for step in path:
        target = target[step]
    target[_STRAY] = 1
    return out


@pytest.mark.parametrize(("fixture", "path"), _injection_cases())
def test_an_unknown_key_on_any_object_is_rejected(fixture: Path, path: tuple) -> None:
    raw = json.loads(fixture.read_text())
    Cnd.model_validate(raw)  # the fixture itself parses

    with pytest.raises(ValidationError, match=_STRAY):
        Cnd.model_validate(_set_stray(raw, path))


def test_the_injection_reaches_every_kind_of_object() -> None:
    """Guard on the test above: the fixtures exercise marks, edges, cells,
    items, pools and metadata, not only nodes."""
    parents = {
        next((p for p in reversed(path) if isinstance(p, str)), "$")
        for fixture in FIXTURES.rglob("*.cnd")
        for path, _ in _object_paths(json.loads(fixture.read_text()))
    }
    assert {
        "$", "doc", "date", "source", "nodes", "children", "text", "marks",
        "refs", "cites", "footnotes", "links", "cells", "items", "term",
        "numbering", "location", "raw", "bibliography", "formatted",
    } <= parents


def test_the_free_form_bags_still_hold_any_key() -> None:
    raw = json.loads((FIXTURES / "minimal.cnd").read_text())
    raw["doc"]["extra"] = {"client": "A"}
    raw["nodes"][0]["state_metadata"] = {"anything": {"nested": [1, 2]}}

    cnd = Cnd.model_validate(raw)

    assert cnd.nodes[0].state_metadata == {"anything": {"nested": [1, 2]}}
    assert cnd.doc.extra == {"client": "A"}


def test_the_committed_schema_closes_every_object() -> None:
    schema = json.loads(SCHEMA.read_text())
    assert schema.get("additionalProperties") is False
    open_defs = [
        name
        for name, definition in schema["$defs"].items()
        if definition.get("type") == "object"
        and definition.get("additionalProperties") is not False
    ]
    assert open_defs == []
