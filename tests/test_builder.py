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
from cnd.core.cnd import CND_VERSION, Cnd
from cnd.core.nodes import HeadingNode, Numbering
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


def _p(text: str) -> dict:
    """A declared paragraph, in the string shorthand."""
    return {"type": "paragraph", "text": text}


def _item(text: str, **kwargs) -> dict:
    """A declared list item holding one paragraph."""
    return {"children": [_p(text)], **kwargs}


class TestTranscription:
    def test_stamps_version_time_and_fresh_ids(self) -> None:
        decl = _decl(
            [
                {"type": "heading", "level": 1, "text": "A", "children": [
                    {"type": "paragraph", "text": "body"},
                ]},
            ],
            bibliography=[{"label": "k1", "title": "W", "year": 2020}],
            footnotes=[{"label": "f1", "children": [_p("note")]}],
        )

        cnd = build(decl)

        assert cnd.cnd_version == CND_VERSION
        assert cnd.built_at.tzinfo is not None
        assert cnd.built_at.utcoffset().total_seconds() == 0
        ids = {v.node.id for v in cnd.iter_all()}
        ids |= {cnd.id, cnd.bibliography[0].id, cnd.footnotes[0].id}
        # heading, paragraph, footnote paragraph, doc, bib entry, footnote
        assert len(ids) == 6

    def test_two_builds_mint_different_ids(self) -> None:
        decl = _decl([{"type": "paragraph", "text": "p"}])
        first, second = build(decl), build(decl)
        assert first.nodes[0].id != second.nodes[0].id

    def test_text_passes_through_byte_for_byte(self) -> None:
        # Weird spacing is the point: any normalization shifts text_spans.
        text = "  two  spaces\tand a tab \n trailing "
        decl = _decl([{"type": "paragraph", "text": text}])
        assert build(decl).nodes[0].text.value == text

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
        assert top.numbering is None and sub.numbering is None

    def test_never_paginated_and_authored_fields_survive(self) -> None:
        decl = _decl(
            [
                {"type": "figure", "kind": "code", "label": "lst-a",
                 "numbering": {"name": "Listing"}, "caption": "cap", "children": [
                    {"type": "code", "text": "x\n", "lang": "text"},
                 ]},
                {"type": "paragraph",
                 "text": {"value": "see", "refs": [{"label": "lst-a"}]},
                 "state_metadata": {"k": "v"}},
            ],
            source={"type": "markdown", "hash": "sha256:00", "uri": "a.md"},
        )

        cnd = build(decl, numbering=True)

        assert cnd.paginated is False
        assert all(v.node.location is None for v in cnd.iter_all())
        figure = cnd.nodes[0]
        # The authored word passes through; the engine supplies the value.
        assert figure.numbering == Numbering(value="1", name="Listing")
        assert cnd.nodes[1].text.refs[0].label == "lst-a"
        assert cnd.nodes[1].state_metadata == {"k": "v"}
        assert cnd.source is not None and cnd.source.uri == "a.md"

    def test_every_declaration_node_type_transcribes(self) -> None:
        decl = _decl(
            [
                {"type": "heading", "level": 1, "text": "H"},
                {"type": "paragraph", "text": {"value": "p", "lang": "en"}},
                {"type": "table", "kind": "data",
                 "cells": [{"row": 0, "col": 0, "children": [_p("c")]}]},
                {"type": "quote", "attribution": "A", "children": [_p("q")]},
                {"type": "code", "text": "c", "lang": "py", "title": "a.py"},
                {"type": "math", "text": "x"},
                {"type": "figure", "caption": "f", "description": "d"},
                {"type": "image", "path": "i.png", "alt": "alt"},
                {"type": "list", "ordered": False,
                 "items": [_item("i", checked=True)]},
                {"type": "terms", "items": [{"term": "t", "children": [_p("d")]}]},
                {"type": "admonition", "kind": "warning", "title": "W",
                 "children": [_p("w")]},
                {"type": "layout",
                 "cells": [{"row": 0, "col": 1, "children": [_p("l")]}]},
            ]
        )

        cnd = build(decl)

        assert [n.type for n in cnd.nodes] == [
            "heading", "paragraph", "table", "quote", "code", "math",
            "figure", "image", "list", "terms", "admonition", "layout",
        ]
        assert cnd.nodes[1].text.lang == "en"
        assert cnd.nodes[2].kind == "data"
        assert cnd.nodes[2].cells[0].children[0].text.value == "c"
        assert cnd.nodes[3].attribution.value == "A"
        assert cnd.nodes[4].title == "a.py"
        assert cnd.nodes[6].description.value == "d"
        assert cnd.nodes[8].items[0].checked is True
        assert cnd.nodes[9].items[0].term.value == "t"
        assert cnd.nodes[10].kind == "warning"
        assert cnd.nodes[11].cells[0].col == 1

    def test_every_nested_node_gets_a_fresh_id(self) -> None:
        """Nodes in items, term items, cells, containers and footnotes are
        nodes in every respect: each one is minted an id."""
        decl = _decl(
            [
                {"type": "list", "items": [_item("in an item")]},
                {"type": "terms", "items": [{"term": "t", "children": [_p("def")]}]},
                {"type": "table", "cells": [{"row": 0, "col": 0, "children": [_p("c")]}]},
                {"type": "admonition", "kind": "note", "children": [_p("a")]},
            ],
            footnotes=[{"label": "fn", "children": [_p("note"), _p("more")]}],
        )

        cnd = build(decl)

        walked = list(cnd.iter_all())
        assert len(walked) == 10
        assert len({v.node.id for v in walked}) == 10

    def test_a_heading_nested_in_a_container_knows_its_ancestors(self) -> None:
        decl = _decl(
            [
                {"type": "heading", "level": 1, "text": "Top", "children": [
                    {"type": "list", "items": [
                        {"children": [{"type": "heading", "level": 2, "text": "In"}]},
                    ]},
                ]},
            ]
        )

        inner = build(decl).nodes[0].children[0].items[0].children[0]

        assert inner.heading_path == ["Top", "In"]

    def test_a_built_text_is_not_shared_with_the_declaration(self) -> None:
        decl = _decl([_p("x")])
        cnd = build(decl)

        cnd.nodes[0].text.value = "changed"

        assert decl.nodes[0].text.value == "x"


class TestNoSharedState:
    """The CND never shares a mutable object with its declaration: two
    builds of one declaration are two independent documents."""

    def test_mutating_the_declaration_after_a_build_leaves_the_cnd_alone(
        self,
    ) -> None:
        from cnd.reconcile import diff

        decl = _decl(
            [{"type": "paragraph", "text": "a",
              "state_metadata": {"review": {"status": "draft"}}},
             {"type": "math", "text": "x",
              "raw": {"format": "typst", "value": "$x$"}}],
            source={"type": "markdown", "hash": "sha256:00", "uri": "a.md"},
            doc={"title": "T", "keywords": ["core"]},
        )
        c1 = build(decl)

        decl.nodes[0].state_metadata["review"]["status"] = "final"
        decl.nodes[1].raw.value = "$y$"
        decl.source.uri = "b.md"
        decl.doc.keywords.append("docs")
        c2 = build(decl)

        assert c1.nodes[0].state_metadata == {"review": {"status": "draft"}}
        assert c1.nodes[1].raw.value == "$x$"
        assert c1.source.uri == "a.md"
        assert c1.doc.keywords == ["core"]
        report = diff(c1, c2)
        assert len(report.changed) == 2


class TestListOrdinals:
    def test_sequential_from_one_when_no_overrides(self) -> None:
        decl = _decl(
            [{"type": "list", "ordered": True, "items": [
                _item("a"), _item("b"), _item("c"),
            ]}]
        )
        numbers = [i.number for i in build(decl).nodes[0].items]
        assert numbers == [1, 2, 3]

    def test_override_rebases_the_rest_of_the_list(self) -> None:
        # Mid-list override: following items count on from it, not from
        # their positional index (the rule pinned on DeclListItem).
        decl = _decl(
            [{"type": "list", "ordered": True, "items": [
                _item("a"), _item("b", number=7), _item("c"),
            ]}]
        )
        numbers = [i.number for i in build(decl).nodes[0].items]
        assert numbers == [1, 7, 8]

    def test_start_override_on_first_item(self) -> None:
        # markdown's "3." on the first item of an ordered list.
        decl = _decl(
            [{"type": "list", "ordered": True, "items": [
                _item("a", number=3), _item("b"),
            ]}]
        )
        numbers = [i.number for i in build(decl).nodes[0].items]
        assert numbers == [3, 4]

    def test_nested_levels_count_independently(self) -> None:
        decl = _decl(
            [{"type": "list", "ordered": True, "items": [
                {"children": [
                    _p("a"),
                    {"type": "list", "ordered": True,
                     "items": [_item("a1"), _item("a2")]},
                ]},
                _item("b"),
            ]}]
        )
        items = build(decl).nodes[0].items
        assert [i.number for i in items] == [1, 2]
        assert [i.number for i in items[0].children[1].items] == [1, 2]

    def test_unordered_list_drops_overrides(self) -> None:
        decl = _decl(
            [{"type": "list", "ordered": False, "items": [
                _item("a", number=5), _item("b"),
            ]}]
        )
        assert [i.number for i in build(decl).nodes[0].items] == [None, None]

    def test_resolution_is_independent_of_numbering_flag(self) -> None:
        decl = _decl(
            [{"type": "list", "ordered": True, "items": [_item("a")]}]
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
            [{"type": "paragraph",
              "text": {"value": "a", "refs": [{"label": "ghost"}]}}]
        )
        violations = self._violations(decl)
        assert [v.rule for v in violations] == ["link-unresolved"]
        assert "@ghost" in violations[0].where

    def test_wrong_domain_edge_is_a_build_error(self) -> None:
        # cites → a node label: resolves, but not in the family's domain.
        decl = _decl(
            [
                {"type": "paragraph", "text": "a", "label": "not-a-bib"},
                {"type": "paragraph",
                 "text": {"value": "b", "cites": [{"label": "not-a-bib"}]}},
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
            [{"type": "paragraph",
              "text": {"value": "a", "refs": [{"label": "ghost"}]}}]
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

    def test_a_violation_in_a_footnote_is_named_by_its_note(self) -> None:
        """Positions inside a footnote count within it (spec §8), so the
        handle names the note: ``@fn-a#2`` is its second node."""
        decl = _decl(
            [{"type": "paragraph",
              "text": {"value": "a", "footnotes": [{"label": "fn-a"}]}}],
            footnotes=[{"label": "fn-a", "children": [
                _p("fine"),
                {"type": "paragraph",
                 "text": {"value": "b", "refs": [{"label": "ghost"}]}},
            ]}],
        )
        [violation] = self._violations(decl)
        assert violation.rule == "link-unresolved"
        assert "@fn-a#2" in violation.where
        assert not re.search(UUID_HEX, violation.where)

    def test_a_bad_mark_is_a_build_error(self) -> None:
        """The full text form can carry offsets; the builder checks them
        like any other invariant."""
        decl = _decl(
            [{"type": "paragraph",
              "text": {"value": "ab", "marks": [{"start": 1, "end": 9, "kind": "emph"}]}}]
        )
        assert [v.rule for v in self._violations(decl)] == ["mark-out-of-bounds"]

    def test_authored_numbering_with_the_engine_off_is_a_build_error(self) -> None:
        """A CND cannot carry a counter word without a value, and the
        declaration never drops authored content silently."""
        decl = _decl(
            [{"type": "figure", "label": "lst-a", "numbering": {"name": "Listing"},
              "children": [{"type": "code", "text": "x"}]}]
        )
        [violation] = self._violations(decl)
        assert violation.rule == "numbering-without-engine"
        assert "@lst-a" in violation.where
        assert build(decl, numbering=True).nodes[0].numbering.name == "Listing"

    def test_a_0_1_0_declaration_is_refused(self) -> None:
        decl = _decl([_p("a")]).model_copy(update={"declaration_version": "0.1.0"})
        [violation] = self._violations(decl)
        assert violation.rule == "declaration-version-unsupported"
        # The message is version-aware: it names the refused version and
        # the one this builder supports.
        assert "0.1.0" in violation.where
        assert DECLARATION_VERSION in violation.message

    def test_error_message_joins_all_violations(self) -> None:
        decl = _decl(
            [
                {"type": "paragraph",
                 "text": {"value": "a", "refs": [{"label": "g1"}]}},
                {"type": "paragraph",
                 "text": {"value": "b", "refs": [{"label": "g2"}]}},
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
        assert a.numbering.value == "1"
        assert [h.numbering.value for h in a.children] == ["1.1", "1.2"]
        assert b.numbering.value == "2"
        assert b.children[0].numbering.value == "2.1"

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
        assert cnd.nodes[0].children[0].numbering.value == "1.0.1"

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
                     "cells": [{"row": 0, "col": 0, "children": [_p("x")]}]},
                ]},
                {"type": "figure", "kind": "image", "caption": "c"},
            ]
        )
        cnd = build(decl, numbering=True)
        assert [f.numbering.value for f in cnd.nodes] == ["1", "1", "2"]

    def test_math_nodes_numbered_inline_math_marks_not(self) -> None:
        """Every math node is a block in 0.5; inline math is a mark inside
        a paragraph, which no counter sees."""
        decl = _decl(
            [
                {"type": "math", "text": "a"},
                {"type": "paragraph", "text": {
                    "value": "b", "marks": [{"start": 0, "end": 1, "kind": "math"}],
                }},
                {"type": "math", "text": "c"},
            ]
        )
        cnd = build(decl, numbering=True)
        assert [cnd.nodes[0].numbering.value, cnd.nodes[2].numbering.value] == [
            "(1)", "(2)",
        ]

    def test_footnote_content_counts_after_the_body(self) -> None:
        """The engine runs in full-walk order: the body, then each note."""
        decl = _decl(
            [
                {"type": "math", "text": "a"},
                {"type": "paragraph",
                 "text": {"value": "x", "footnotes": [{"label": "fn"}]}},
                {"type": "math", "text": "b"},
            ],
            footnotes=[{"label": "fn", "children": [
                {"type": "math", "label": "eq-note", "text": "c"},
            ]}],
        )
        cnd = build(decl, numbering=True)
        assert cnd.footnotes[0].children[0].numbering.value == "(3)"

    def test_counter_word_is_never_invented(self) -> None:
        decl = _decl([{"type": "figure", "kind": "image", "caption": "a"}])
        figure = build(decl, numbering=True).nodes[0]
        assert figure.numbering == Numbering(value="1", name=None)


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

        assert _scrub(json.loads(built.to_json())) == _scrub(expected)

    @pytest.mark.parametrize("name", ["article.cnd", "numbered.cnd"])
    def test_every_heading_path_matches_the_walk(self, name: str) -> None:
        """The heading path the builder derives is the one the walk sees:
        each heading's path is its context's path plus itself."""
        cnd = Cnd.model_validate_json((FIXTURES / name).read_text())
        headings = [v for v in cnd.iter_all() if isinstance(v.node, HeadingNode)]

        assert headings
        for visit in headings:
            assert visit.node.heading_path[:-1] == visit.ctx.heading_path
