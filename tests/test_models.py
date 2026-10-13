"""The 0.5 node model (docs/proposals/0013)."""

from uuid import uuid4

import pytest
from pydantic import TypeAdapter, ValidationError

from cnd.core.cnd import CND_VERSION, BibEntry, DocMetadata, Footnote
from cnd.core.nodes import (
    KNOWN_ADMONITION_KINDS,
    KNOWN_TABLE_KINDS,
    AdmonitionNode,
    Cell,
    CndNode,
    FigureNode,
    LayoutNode,
    ListItem,
    ListNode,
    ParagraphNode,
    QuoteNode,
    TableNode,
    TermItem,
    TermsNode,
    edges_of,
    texts_of,
)
from cnd.core.text import NodeRef
from factories import rt

NODE = TypeAdapter(CndNode)


def _para(value: str = "p", **kw) -> ParagraphNode:
    return ParagraphNode(id=uuid4(), type="paragraph", text=rt(value, **kw))


def test_the_format_version_is_0_5_0() -> None:
    assert CND_VERSION == "0.5.0"


def test_a_paragraph_text_must_be_rich_text() -> None:
    with pytest.raises(ValidationError):
        NODE.validate_python({"id": str(uuid4()), "type": "paragraph", "text": "plain"})


def test_link_families_left_the_node_base() -> None:
    assert "refs" not in ParagraphNode.model_fields
    assert "refs" in type(rt("x")).model_fields


def test_new_node_types_parse() -> None:
    for payload in (
        {"type": "admonition", "kind": "warning", "children": []},
        {"type": "layout", "cells": []},
    ):
        node = NODE.validate_python({"id": str(uuid4()), **payload})
        assert node.type == payload["type"]


def test_containers_hold_nodes_in_children() -> None:
    item = ListItem(checked=True, children=[_para("a")])
    cell = Cell(row=0, col=0, children=[_para("b")])
    term = TermItem(term=rt("T"), children=[_para("c")])
    assert item.children[0].text.value == "a"
    assert cell.children[0].text.value == "b"
    assert term.children[0].text.value == "c"


def test_a_nested_list_carries_its_own_kind() -> None:
    inner = ListNode(id=uuid4(), type="list", ordered=False, items=[ListItem(children=[_para("x")])])
    outer = ListNode(id=uuid4(), type="list", ordered=True, items=[ListItem(children=[_para("y"), inner])])
    assert outer.ordered and not outer.items[0].children[1].ordered


def test_removed_fields_are_gone() -> None:
    assert "tight" not in ListNode.model_fields and "tight" not in TermsNode.model_fields
    assert "content_kind" not in TableNode.model_fields and "raw" not in TableNode.model_fields
    assert "block" not in QuoteNode.model_fields and "text" not in QuoteNode.model_fields
    assert "number" not in FigureNode.model_fields and "counter_label" not in FigureNode.model_fields


def test_open_vocabularies_accept_free_values() -> None:
    assert AdmonitionNode(id=uuid4(), type="admonition", kind="example").kind == "example"
    assert TableNode(id=uuid4(), type="table", kind="schedule").kind == "schedule"
    assert KNOWN_ADMONITION_KINDS == {"note", "tip", "important", "warning", "caution"}
    assert KNOWN_TABLE_KINDS == {"data", "content"}


def test_texts_and_edges_of_a_figure() -> None:
    fig = FigureNode(
        id=uuid4(), type="figure",
        caption=rt("See it", refs=[NodeRef(label="a")]),
        description=rt("Bars", refs=[NodeRef(label="b")]),
    )
    assert [t.value for t in texts_of(fig)] == ["See it", "Bars"]
    assert [e.label for e in edges_of(fig)] == ["a", "b"]


def test_texts_of_terms_are_the_terms_only() -> None:
    terms = TermsNode(id=uuid4(), type="terms", items=[TermItem(term=rt("T"), children=[_para("d")])])
    assert [t.value for t in texts_of(terms)] == ["T"]


def test_document_metadata_and_pools() -> None:
    doc = DocMetadata(title="T", status="Approved", version="1.2", extra={"client": "ACME"})
    assert doc.extra["client"] == "ACME"
    entry = BibEntry(id=uuid4(), label="k", formatted=rt("Knuth"))
    note = Footnote(id=uuid4(), label="fn", children=[_para("n")])
    assert entry.formatted.value == "Knuth" and note.children[0].text.value == "n"


def test_mutable_defaults_are_not_shared_between_instances() -> None:
    from cnd.core.text import Mark, RichText

    a, b = RichText(value="a"), RichText(value="b")
    a.marks.append(Mark(start=0, end=1, kind="strong"))
    assert b.marks == []
