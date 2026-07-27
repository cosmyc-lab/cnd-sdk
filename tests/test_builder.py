"""The builder — the declarative door's enforcement bottleneck (docs/adr/0019).

What is tested here is the derivation contract of spec §12: everything a
declaration deliberately omits (ids, heading_path, resolved ordinals,
counters) comes back on the built CND, and everything authored passes
through untouched.
"""

from datetime import timezone

import pytest

from cnd.builder import BuildError, build
from cnd.core.cnd import CND_VERSION
from cnd.declaration import DECLARATION_VERSION, Declaration


def _decl(nodes: list[dict], **top) -> Declaration:
    """A minimal declaration around ``nodes``; ``top`` overrides top-level keys."""
    payload = {
        "declaration_version": DECLARATION_VERSION,
        "doc": {"title": "T"},
        "nodes": nodes,
        **top,
    }
    return Declaration.model_validate(payload)


class TestTranscription:
    def test_stamps_version_time_and_fresh_ids(self) -> None:
        decl = _decl(
            [
                {"type": "heading", "level": 1, "text": "A", "children": [
                    {"type": "paragraph", "text": "body"},
                ]},
            ],
            bibliography=[{"label": "k1", "title": "W", "year": 2020}],
            footnotes=[{"label": "f1", "text": "note"}],
        )

        cnd = build(decl)

        assert cnd.cnd_version == CND_VERSION
        assert cnd.built_at.tzinfo is not None
        assert cnd.built_at.utcoffset().total_seconds() == 0
        ids = {v.node.id for v in cnd.iter()}
        ids |= {cnd.id, cnd.bibliography[0].id, cnd.footnotes[0].id}
        assert len(ids) == 5  # heading, paragraph, doc, bib entry, footnote

    def test_two_builds_mint_different_ids(self) -> None:
        decl = _decl([{"type": "paragraph", "text": "p"}])
        first, second = build(decl), build(decl)
        assert first.nodes[0].id != second.nodes[0].id

    def test_text_passes_through_byte_for_byte(self) -> None:
        # Weird spacing is the point: any normalization shifts text_spans.
        text = "  two  spaces\tand a tab \n trailing "
        decl = _decl([{"type": "paragraph", "text": text}])
        assert build(decl).nodes[0].text == text

    def test_heading_path_is_ancestors_plus_self_bare_when_unnumbered(self) -> None:
        decl = _decl(
            [
                {"type": "heading", "level": 1, "text": "Top", "children": [
                    {"type": "heading", "level": 2, "text": "Sub", "children": [
                        {"type": "paragraph", "text": "p"},
                    ]},
                ]},
            ]
        )

        cnd = build(decl)

        top = cnd.nodes[0]
        sub = top.children[0]
        assert top.heading_path == ["Top"]
        assert sub.heading_path == ["Top", "Sub"]
        assert top.number is None and sub.number is None

    def test_never_paginated_and_authored_fields_survive(self) -> None:
        decl = _decl(
            [
                {"type": "figure", "kind": "code", "label": "lst-a",
                 "counter_label": "Listing", "caption": "cap", "children": [
                    {"type": "code", "text": "x\n", "lang": "text"},
                 ]},
                {"type": "paragraph", "text": "see", "refs": [{"label": "lst-a"}],
                 "state_metadata": {"k": "v"}},
            ],
            source={"type": "markdown", "hash": "sha256:00", "uri": "a.md"},
        )

        cnd = build(decl)

        assert cnd.paginated is False
        assert all(v.node.location is None for v in cnd.iter())
        figure = cnd.nodes[0]
        assert figure.counter_label == "Listing"  # authored, passed through
        assert figure.number is None              # engine off by default
        assert cnd.nodes[1].refs[0].label == "lst-a"
        assert cnd.nodes[1].state_metadata == {"k": "v"}
        assert cnd.source is not None and cnd.source.uri == "a.md"

    def test_every_declaration_node_type_transcribes(self) -> None:
        decl = _decl(
            [
                {"type": "heading", "level": 1, "text": "H"},
                {"type": "paragraph", "text": "p", "lang": "en"},
                {"type": "table", "kind": "grid",
                 "cells": [{"row": 0, "col": 0, "text": "c"}]},
                {"type": "quote", "text": "q", "attribution": "A"},
                {"type": "code", "text": "c", "lang": "py", "block": False},
                {"type": "math", "text": "x", "block": True},
                {"type": "figure", "caption": "f"},
                {"type": "image", "path": "i.png", "alt": "alt"},
                {"type": "list", "ordered": False, "items": [{"text": "i"}]},
                {"type": "terms", "items": [{"term": "t", "description": "d"}]},
            ]
        )

        cnd = build(decl)

        assert [n.type for n in cnd.nodes] == [
            "heading", "paragraph", "table", "quote", "code",
            "math", "figure", "image", "list", "terms",
        ]
        assert cnd.nodes[2].cells[0].text == "c"
        assert cnd.nodes[4].block is False
        assert cnd.nodes[9].items[0].term == "t"


class TestListOrdinals:
    def test_sequential_from_one_when_no_overrides(self) -> None:
        decl = _decl(
            [{"type": "list", "ordered": True, "items": [
                {"text": "a"}, {"text": "b"}, {"text": "c"},
            ]}]
        )
        numbers = [i.number for i in build(decl).nodes[0].items]
        assert numbers == [1, 2, 3]

    def test_override_rebases_the_rest_of_the_list(self) -> None:
        # Mid-list override: following items count on from it, not from
        # their positional index (the rule pinned on DeclListItem).
        decl = _decl(
            [{"type": "list", "ordered": True, "items": [
                {"text": "a"}, {"text": "b", "number": 7}, {"text": "c"},
            ]}]
        )
        numbers = [i.number for i in build(decl).nodes[0].items]
        assert numbers == [1, 7, 8]

    def test_start_override_on_first_item(self) -> None:
        # markdown's "3." on the first item of an ordered list.
        decl = _decl(
            [{"type": "list", "ordered": True, "items": [
                {"text": "a", "number": 3}, {"text": "b"},
            ]}]
        )
        numbers = [i.number for i in build(decl).nodes[0].items]
        assert numbers == [3, 4]

    def test_nested_levels_count_independently(self) -> None:
        decl = _decl(
            [{"type": "list", "ordered": True, "items": [
                {"text": "a", "children": [{"text": "a1"}, {"text": "a2"}]},
                {"text": "b"},
            ]}]
        )
        items = build(decl).nodes[0].items
        assert [i.number for i in items] == [1, 2]
        assert [i.number for i in items[0].children] == [1, 2]

    def test_unordered_list_drops_overrides(self) -> None:
        decl = _decl(
            [{"type": "list", "ordered": False, "items": [
                {"text": "a", "number": 5}, {"text": "b"},
            ]}]
        )
        assert [i.number for i in build(decl).nodes[0].items] == [None, None]

    def test_resolution_is_independent_of_numbering_flag(self) -> None:
        decl = _decl(
            [{"type": "list", "ordered": True, "items": [{"text": "a"}]}]
        )
        assert build(decl).nodes[0].items[0].number == 1
        assert build(decl, numbering=True).nodes[0].items[0].number == 1
