"""The builder — the declarative door's enforcement bottleneck (docs/adr/0019).

What is tested here is the derivation contract of spec §12: everything a
declaration deliberately omits (ids, heading_path, resolved ordinals,
counters) comes back on the built CND, and everything authored passes
through untouched.
"""

import json
import re
from pathlib import Path

import pytest
import yaml
from pydantic import ValidationError

from cnd.builder import BuildError, build
from cnd.core.cnd import CND_VERSION
from cnd.declaration import DECLARATION_VERSION, Declaration

FIXTURES = Path(__file__).parent.parent / "fixtures" / "declaration"


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


UUID_HEX = "[0-9a-f]{8}-"  # enough to spot a leaked UUID in a message


class TestBuildErrors:
    def _violations(self, decl: Declaration) -> list:
        with pytest.raises(BuildError) as excinfo:
            build(decl)
        return excinfo.value.violations

    def test_duplicate_label_is_a_build_error(self) -> None:
        decl = _decl(
            [
                {"type": "paragraph", "text": "a", "label": "dup"},
                {"type": "paragraph", "text": "b", "label": "dup"},
            ]
        )
        violations = self._violations(decl)
        assert [v.rule for v in violations] == ["label-not-unique"]
        assert "@dup" in violations[0].where

    def test_unresolved_ref_is_a_build_error(self) -> None:
        decl = _decl(
            [{"type": "paragraph", "text": "a", "refs": [{"label": "ghost"}]}]
        )
        violations = self._violations(decl)
        assert [v.rule for v in violations] == ["link-unresolved"]
        assert "@ghost" in violations[0].where

    def test_wrong_domain_edge_is_a_build_error(self) -> None:
        # cites → a node label: resolves, but not in the family's domain.
        decl = _decl(
            [
                {"type": "paragraph", "text": "a", "label": "not-a-bib"},
                {"type": "paragraph", "text": "b",
                 "cites": [{"label": "not-a-bib"}]},
            ]
        )
        assert [v.rule for v in self._violations(decl)] == ["link-wrong-domain"]

    def test_empty_bib_entry_is_a_build_error(self) -> None:
        decl = _decl(
            [{"type": "paragraph", "text": "a"}],
            bibliography=[{"label": "k1"}],  # no formatted, no structured field
        )
        assert [v.rule for v in self._violations(decl)] == ["bib-entry-empty"]

    def test_unsupported_declaration_version(self) -> None:
        decl = _decl([{"type": "paragraph", "text": "a"}])
        decl = decl.model_copy(update={"declaration_version": "9.9.9"})
        violations = self._violations(decl)
        assert [v.rule for v in violations] == ["declaration-version-unsupported"]
        assert "9.9.9" in violations[0].where

    def test_where_is_label_first_never_a_minted_uuid(self) -> None:
        # An unlabelled node in violation: named by reading-order position.
        decl = _decl(
            [{"type": "paragraph", "text": "a", "refs": [{"label": "ghost"}]}]
        )
        [violation] = self._violations(decl)
        assert not re.search(UUID_HEX, violation.where)
        assert not re.search(UUID_HEX, violation.message)
        assert "#1" in violation.where  # first node in reading order

    def test_level_zero_heading_is_rejected_at_parse(self) -> None:
        # `level` is constrained to >= 1 at the model (declaration.py): a
        # level-0 heading is unrepresentable, not a counter-engine crash
        # at build time (`_Counters.heading` would IndexError on it).
        with pytest.raises(ValidationError):
            _decl([{"type": "heading", "level": 0, "text": "bad"}])

    def test_error_message_joins_all_violations(self) -> None:
        decl = _decl(
            [
                {"type": "paragraph", "text": "a", "refs": [{"label": "g1"}]},
                {"type": "paragraph", "text": "b", "refs": [{"label": "g2"}]},
            ]
        )
        with pytest.raises(BuildError) as excinfo:
            build(decl)
        assert "g1" in str(excinfo.value) and "g2" in str(excinfo.value)


class TestCounterEngine:
    def test_headings_dotted_with_reset(self) -> None:
        decl = _decl(
            [
                {"type": "heading", "level": 1, "text": "A", "children": [
                    {"type": "heading", "level": 2, "text": "A1"},
                    {"type": "heading", "level": 2, "text": "A2"},
                ]},
                {"type": "heading", "level": 1, "text": "B", "children": [
                    {"type": "heading", "level": 2, "text": "B1"},
                ]},
            ]
        )
        cnd = build(decl, numbering=True)
        a, b = cnd.nodes
        assert a.number == "1"
        assert [h.number for h in a.children] == ["1.1", "1.2"]
        assert b.number == "2"
        assert b.children[0].number == "2.1"

    def test_skipped_level_shows_zero(self) -> None:
        # Level jumps 1 → 3: the pinned house style shows the gap as 0
        # rather than papering over it.
        decl = _decl(
            [
                {"type": "heading", "level": 1, "text": "A", "children": [
                    {"type": "heading", "level": 3, "text": "deep"},
                ]},
            ]
        )
        cnd = build(decl, numbering=True)
        assert cnd.nodes[0].children[0].number == "1.0.1"

    def test_heading_path_elements_carry_the_number(self) -> None:
        decl = _decl(
            [
                {"type": "heading", "level": 1, "text": "Top", "children": [
                    {"type": "heading", "level": 2, "text": "Sub"},
                ]},
            ]
        )
        sub = build(decl, numbering=True).nodes[0].children[0]
        assert sub.heading_path == ["1 Top", "1.1 Sub"]

    def test_figures_count_per_kind_with_inference(self) -> None:
        decl = _decl(
            [
                {"type": "figure", "kind": "image", "caption": "a"},
                # kind=None wrapping a table: inferred as "table", so it
                # must NOT advance the image counter.
                {"type": "figure", "caption": "b", "children": [
                    {"type": "table",
                     "cells": [{"row": 0, "col": 0, "text": "x"}]},
                ]},
                {"type": "figure", "kind": "image", "caption": "c"},
            ]
        )
        cnd = build(decl, numbering=True)
        assert [f.number for f in cnd.nodes] == ["1", "1", "2"]

    def test_block_math_numbered_inline_math_not(self) -> None:
        decl = _decl(
            [
                {"type": "math", "text": "a", "block": True},
                {"type": "math", "text": "b", "block": False},
                {"type": "math", "text": "c", "block": True},
            ]
        )
        cnd = build(decl, numbering=True)
        assert [m.number for m in cnd.nodes] == ["(1)", None, "(2)"]

    def test_counter_label_is_never_invented(self) -> None:
        decl = _decl([{"type": "figure", "kind": "image", "caption": "a"}])
        figure = build(decl, numbering=True).nodes[0]
        assert figure.number == "1"
        assert figure.counter_label is None


def _scrub(obj):
    """The fixture comparison rule (ADR 0020 §4, declaration → CND):
    equal after erasing every ``id`` and ``built_at``. Byte-equality is
    impossible (ids are minted fresh, ADR 0015) and the content hash
    deliberately excludes ``number`` (ADR 0016), so neither can verify
    the builder — structural comparison over the scrubbed dump does."""
    if isinstance(obj, dict):
        return {k: _scrub(v) for k, v in obj.items() if k not in {"id", "built_at"}}
    if isinstance(obj, list):
        return [_scrub(item) for item in obj]
    return obj


class TestGoldenFixtures:
    @pytest.mark.parametrize(
        ("decl_name", "cnd_name", "numbering"),
        [
            ("article.decl.yaml", "article.cnd", False),
            ("numbered.decl.yaml", "numbered.cnd", True),
        ],
    )
    def test_declaration_builds_to_the_committed_cnd(
        self, decl_name: str, cnd_name: str, numbering: bool,
    ) -> None:
        decl = Declaration.model_validate(
            yaml.safe_load((FIXTURES / decl_name).read_text())
        )
        expected = json.loads((FIXTURES / cnd_name).read_text())

        built = build(decl, numbering=numbering)

        assert _scrub(json.loads(built.model_dump_json())) == _scrub(expected)
