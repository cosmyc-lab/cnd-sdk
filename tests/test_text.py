"""Rich text value objects (docs/proposals/0013)."""

import pytest
from pydantic import ValidationError

from cnd.core.text import (
    ATOMIC_MARK_KINDS,
    KNOWN_MARK_KINDS,
    CiteRef,
    FootnoteRef,
    LinkRef,
    Mark,
    NodeRef,
    Numbering,
    RawSource,
    RichText,
)


def test_a_bare_value_is_a_complete_rich_text() -> None:
    text = RichText.model_validate({"value": "plain"})
    assert text.marks == [] and text.refs == [] and text.links == []
    assert text.lang is None


def test_edges_flatten_the_four_families_in_order() -> None:
    text = RichText(
        value="abcdef",
        refs=[NodeRef(label="r")],
        cites=[CiteRef(label="c")],
        footnotes=[FootnoteRef(label="f")],
        links=[LinkRef(href="https://example.com")],
    )
    assert [type(e).__name__ for e in text.edges()] == [
        "NodeRef", "CiteRef", "FootnoteRef", "LinkRef",
    ]


def test_mark_kind_is_an_open_vocabulary() -> None:
    mark = Mark(start=0, end=1, kind="smallcaps")
    assert mark.kind == "smallcaps"
    assert "smallcaps" not in KNOWN_MARK_KINDS


def test_known_and_atomic_mark_kinds() -> None:
    assert KNOWN_MARK_KINDS == {
        "strong", "emph", "code", "strike", "sup", "sub",
        "underline", "highlight", "math",
    }
    assert ATOMIC_MARK_KINDS == {"code", "math"}


def test_a_math_mark_carries_its_source() -> None:
    mark = Mark(start=0, end=3, kind="math", raw=RawSource(format="typst", value="x^2"))
    assert mark.raw.value == "x^2"


def test_a_string_is_not_a_rich_text() -> None:
    with pytest.raises(ValidationError):
        RichText.model_validate("plain")


def test_numbering_requires_a_value() -> None:
    assert Numbering(value="3").name is None
    with pytest.raises(ValidationError):
        Numbering.model_validate({"name": "Figure"})
