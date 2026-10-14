"""The declaration schema and models (docs/adr/0019, non-normative).

Two things carry weight here. The schema-regression test is the payoff of
generating the schema from the models rather than hand-writing it (ADR
0004): the committed file cannot drift from what the models say. And the
absence tests pin the declaration's defining property — that it carries
none of the state the builder derives — which a "does it validate" test
would not catch, since adding a stray field still validates.
"""

import json
from pathlib import Path

import pytest
import yaml
from jsonschema import Draft202012Validator
from pydantic import ValidationError

from cnd.declaration import (
    DECLARATION_VERSION,
    DeclParagraphNode,
    Declaration,
    RichText,
)

ROOT = Path(__file__).parent.parent
SCHEMA_PATH = ROOT / "schema" / "cnd-declaration.schema.json"
FIXTURES = ROOT / "fixtures" / "declaration"


def _committed_schema() -> dict:
    return json.loads(SCHEMA_PATH.read_text())


def _declarations() -> list[Path]:
    return sorted(FIXTURES.glob("*.decl.yaml"))


class TestSchema:
    def test_schema_matches_generated_model(self) -> None:
        committed = _committed_schema()
        generated = Declaration.model_json_schema()
        for key in ("$schema", "$id", "title"):
            generated[key] = committed[key]

        assert generated == committed, (
            "schema/cnd-declaration.schema.json is out of sync with "
            "Declaration.model_json_schema() — regenerate and re-commit it."
        )

    def test_fixtures_validate_against_the_schema(self) -> None:
        validator = Draft202012Validator(_committed_schema())
        assert _declarations(), "expected at least one .decl.yaml fixture"

        for path in _declarations():
            raw = yaml.safe_load(path.read_text())
            errors = list(validator.iter_errors(raw))
            assert not errors, f"{path.name}: {errors}"

    def test_fixtures_parse_as_declarations(self) -> None:
        for path in _declarations():
            Declaration.model_validate(yaml.safe_load(path.read_text()))


class TestNothingTheBuilderDerivesIsCarried:
    """The declaration's defining property (ADR 0019): a producer supplies
    authored content, never the state the builder resolves. A schema that
    merely *allowed* these fields to be absent would not prove it — these
    assert they cannot be *present*."""

    # The counter word is NOT here: it has an authored half the builder
    # cannot derive, so the declaration keeps it as `numbering.name`.
    # `number` stays — its resolved-ordinal form is dropped; the list-item
    # override lives on DeclListItem, not a node.
    DERIVED_NODE_FIELDS = ("id", "location", "number", "heading_path")

    def _node_properties(self) -> set[str]:
        schema = _committed_schema()
        names: set[str] = set()
        for name, definition in schema["$defs"].items():
            if name.startswith("Decl") and name.endswith("Node"):
                names |= set(definition.get("properties", {}))
        return names

    def test_no_node_type_carries_a_derived_field(self) -> None:
        present = self._node_properties()
        leaked = present & set(self.DERIVED_NODE_FIELDS)

        assert not leaked, f"declaration nodes carry derived fields: {leaked}"

    def test_the_top_level_carries_no_id_built_at_or_cnd_version(self) -> None:
        top = set(_committed_schema()["properties"])

        assert top.isdisjoint({"id", "built_at", "cnd_version"})

    def test_pool_entries_carry_no_id(self) -> None:
        defs = _committed_schema()["$defs"]

        assert "id" not in defs["DeclBibEntry"]["properties"]
        assert "id" not in defs["DeclFootnote"]["properties"]

    def test_the_entries_that_hold_nodes_carry_no_id(self) -> None:
        """List items, term items and cells hold nodes; they are declared
        fresh so that their children carry no id either."""
        defs = _committed_schema()["$defs"]

        for entry in ("DeclListItem", "DeclTermItem", "DeclCell"):
            assert "id" not in defs[entry]["properties"], entry
        assert "ParagraphNode" not in defs, "a CND node leaked into the schema"

    def test_numbering_carries_no_value(self) -> None:
        """The value is the counter engine's; only the word is authored."""
        numbering = _committed_schema()["$defs"]["DeclNumbering"]

        assert set(numbering["properties"]) == {"name"}


class TestUnknownFieldsAreRejected:
    """A stray field is a rejection, not a silent drop — the point of an
    authored form that is hand-corrected before building (spec §12)."""

    def _decl(self, node: dict) -> dict:
        return {
            "declaration_version": DECLARATION_VERSION,
            "doc": {"title": "T"},
            "nodes": [node],
        }

    def test_a_derived_field_on_a_node_is_rejected(self) -> None:
        """The exact failure the prose promises: `location` cannot merely
        be absent, it cannot be present."""
        with pytest.raises(ValidationError, match="location"):
            Declaration.model_validate(
                self._decl({"type": "paragraph", "text": "x", "location": {"page": 1}})
            )

    def test_a_typo_on_an_optional_key_is_rejected_not_dropped(self) -> None:
        """`capton` for `caption` would vanish silently under the default
        config; here it raises, which is why strict was chosen."""
        with pytest.raises(ValidationError, match="capton"):
            Declaration.model_validate(
                self._decl(
                    {"type": "figure", "kind": "image", "capton": "A diagram"}
                )
            )

    def test_a_top_level_typo_is_rejected(self) -> None:
        with pytest.raises(ValidationError, match="bibliografy"):
            Declaration.model_validate(
                {
                    "declaration_version": DECLARATION_VERSION,
                    "doc": {"title": "T"},
                    "nodes": [],
                    "bibliografy": [],
                }
            )

    def test_the_committed_schema_forbids_extras_on_nodes(self) -> None:
        heading = _committed_schema()["$defs"]["DeclHeadingNode"]
        assert heading.get("additionalProperties") is False

    def test_the_extension_bag_still_holds_arbitrary_keys(self) -> None:
        """`extra=forbid` guards the model's own fields, not the contents
        of a dict-typed one."""
        decl = Declaration.model_validate(
            self._decl(
                {"type": "paragraph", "text": "x", "state_metadata": {"anything": 1}}
            )
        )
        assert decl.nodes[0].state_metadata == {"anything": 1}

    def test_strictness_is_partial_at_the_reused_value_objects(self) -> None:
        """A documented limit, pinned so it is a known boundary and not a
        surprise: a stray key *inside* a reused CND value object (here a
        rich text) is not caught, because forbidding on it would change
        CND parsing (docs: `_Strict`)."""
        decl = Declaration.model_validate(
            self._decl(
                {"type": "paragraph", "text": {"value": "x", "marsk": []}}
            )
        )
        assert decl.nodes[0].text.value == "x"

    def test_a_typo_inside_a_cell_is_now_rejected(self) -> None:
        """Cells hold nodes, so the declaration declares its own strict
        cell: the boundary moved past it."""
        with pytest.raises(ValidationError, match="txet"):
            Declaration.model_validate(
                self._decl(
                    {"type": "table", "cells": [{"row": 0, "col": 0, "txet": "x"}]}
                )
            )

    def test_a_typo_inside_a_list_item_is_rejected(self) -> None:
        with pytest.raises(ValidationError, match="chekced"):
            Declaration.model_validate(
                self._decl({"type": "list", "items": [{"chekced": True}]})
            )

    def test_a_numbering_value_is_rejected(self) -> None:
        """A declaration cannot smuggle in the value the engine resolves."""
        with pytest.raises(ValidationError, match="value"):
            Declaration.model_validate(
                self._decl(
                    {"type": "figure", "numbering": {"name": "Listing", "value": "3"}}
                )
            )

    def test_the_0_4_fields_are_rejected(self) -> None:
        """`counter_label`, a node-level `refs` and a list item's `text`
        were 0.4 shapes; a 0.4 declaration fails loudly, not silently."""
        for node in (
            {"type": "figure", "counter_label": "Listing"},
            {"type": "paragraph", "text": "x", "refs": [{"label": "a"}]},
            {"type": "list", "items": [{"text": "x"}]},
        ):
            with pytest.raises(ValidationError):
                Declaration.model_validate(self._decl(node))


class TestWhatTheDeclarationKeeps:
    def test_the_label_is_kept_as_the_durable_identity(self) -> None:
        """The one identity a declaration supplies (ADR 0015/0017)."""
        heading = _committed_schema()["$defs"]["DeclHeadingNode"]

        assert "label" in heading["properties"]

    def test_a_list_item_keeps_number_as_an_override(self) -> None:
        """Absent means sequential; present means an authored start/skip —
        the authored half of the CND's resolved ordinal, kept; the derived
        half dropped."""
        item = _committed_schema()["$defs"]["DeclListItem"]["properties"]

        assert "number" in item

    def test_numbering_is_kept_on_every_counter_bearing_node(self) -> None:
        """The authored counter word — with no `kind` on a heading or
        equation it is purely authored, so dropping it while keeping the
        list-number override would split the same authored/derived line two
        opposite ways."""
        defs = _committed_schema()["$defs"]

        for node in ("DeclHeadingNode", "DeclMathNode", "DeclFigureNode"):
            assert "numbering" in defs[node]["properties"], node

    def test_the_resolved_number_is_still_stripped_from_those_nodes(self) -> None:
        """`numbering.name` is kept but `number` (the running counter value)
        stays out — it has no authored half on a heading/math/figure."""
        defs = _committed_schema()["$defs"]

        for node in ("DeclHeadingNode", "DeclMathNode", "DeclFigureNode"):
            assert "number" not in defs[node]["properties"], node

    def test_source_provenance_is_kept(self) -> None:
        """Provenance is not resolved presentation state; a producer knows
        what it converted from."""
        assert "source" in _committed_schema()["properties"]


class TestVersioning:
    def test_the_declaration_carries_its_own_version(self) -> None:
        """ADR 0019 §3: versioned independently of `cnd_version`, so the
        first evolution does not break every producer silently."""
        assert "declaration_version" in _committed_schema()["properties"]
        assert DECLARATION_VERSION != "0.3.0"

    def test_the_version_is_required_like_cnd_version(self) -> None:
        """Absence must mean "unknown → error", not "latest" — the silent
        assumption the field exists to prevent (Fable review). Required,
        matching the CND's required `cnd_version`."""
        assert "declaration_version" in _committed_schema()["required"]

        with pytest.raises(ValidationError, match="declaration_version"):
            Declaration.model_validate({"doc": {"title": "T"}, "nodes": []})

    def test_a_present_version_parses(self) -> None:
        built = Declaration.model_validate(
            yaml.safe_load(next(iter(_declarations())).read_text())
        )
        assert built.declaration_version == DECLARATION_VERSION


#: Every RichText slot of the CND, as (declaration model, field).
RICH_TEXT_SLOTS = [
    ("DeclHeadingNode", "text"),
    ("DeclParagraphNode", "text"),
    ("DeclQuoteNode", "attribution"),
    ("DeclFigureNode", "caption"),
    ("DeclFigureNode", "description"),
    ("DeclAdmonitionNode", "title"),
    ("DeclTermItem", "term"),
    ("DeclBibEntry", "formatted"),
]


class TestShorthand:
    """Wherever the CND holds a RichText, a declaration accepts a plain
    string or the full object (docs/proposals/0013, "Declaration")."""

    @pytest.mark.parametrize(("model", "field"), RICH_TEXT_SLOTS)
    def test_the_schema_accepts_both_forms(self, model: str, field: str) -> None:
        prop = _committed_schema()["$defs"][model]["properties"][field]
        forms = {
            option.get("type") or option.get("$ref") for option in prop["anyOf"]
        }

        assert {"string", "#/$defs/RichText"} <= forms

    def test_a_string_and_its_object_build_the_same_text(self) -> None:
        short = DeclParagraphNode(type="paragraph", text="Hello")
        full = DeclParagraphNode(type="paragraph", text={"value": "Hello"})

        assert short.text == full.text == RichText(value="Hello")

    def test_the_object_form_carries_marks_and_every_link_family(self) -> None:
        """The full form is the CND's own RichText, so hyperlinks are
        declarable too (the gap ADR 0024 left open)."""
        decl = Declaration.model_validate(
            {
                "declaration_version": DECLARATION_VERSION,
                "doc": {"title": "T"},
                "nodes": [
                    {
                        "type": "paragraph",
                        "text": {
                            "value": "See the site.",
                            "marks": [{"start": 0, "end": 3, "kind": "strong"}],
                            "links": [
                                {"href": "https://example.org", "text_span": [8, 12]}
                            ],
                        },
                    }
                ],
            }
        )
        text = decl.nodes[0].text

        assert text.marks[0].kind == "strong"
        assert text.links[0].href == "https://example.org"

    def test_the_value_is_kept_byte_for_byte(self) -> None:
        raw = "  two  spaces\tand a tab \n trailing "
        assert DeclParagraphNode(type="paragraph", text=raw).text.value == raw
