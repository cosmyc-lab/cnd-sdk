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

import yaml
from jsonschema import Draft202012Validator

from cnd.declaration import DECLARATION_VERSION, Declaration

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

    DERIVED_NODE_FIELDS = ("id", "location", "number", "counter_label", "heading_path")

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

    def test_source_provenance_is_kept(self) -> None:
        """Provenance is not resolved presentation state; a producer knows
        what it converted from."""
        assert "source" in _committed_schema()["properties"]


class TestVersioning:
    def test_the_declaration_carries_its_own_version(self) -> None:
        """ADR 0019 §3: versioned independently of `cnd_version`, so the
        first evolution does not break every producer silently."""
        assert "declaration_version" in _committed_schema()["properties"]

    def test_the_version_defaults_and_is_not_the_format_version(self) -> None:
        built = Declaration.model_validate(
            yaml.safe_load(next(iter(_declarations())).read_text())
        )
        assert built.declaration_version == DECLARATION_VERSION
        assert DECLARATION_VERSION != "0.3.0"
