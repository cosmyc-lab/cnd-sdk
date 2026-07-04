import json
from pathlib import Path

from jsonschema import Draft202012Validator

from cnd import CndManifest

ROOT = Path(__file__).parent.parent
SCHEMA_PATH = ROOT / "spec" / "schema" / "cnd-manifest.schema.json"
FIXTURES_DIR = ROOT / "fixtures"


def _committed_schema() -> dict:
    return json.loads(SCHEMA_PATH.read_text())


def test_schema_matches_generated_model():
    committed = _committed_schema()
    generated = CndManifest.model_json_schema()
    generated["$schema"] = committed["$schema"]
    generated["$id"] = committed["$id"]
    generated["title"] = committed["title"]
    assert generated == committed, (
        "spec/schema/cnd-manifest.schema.json is out of sync with "
        "CndManifest.model_json_schema() — regenerate and re-commit it."
    )


def test_fixtures_validate_against_schema():
    validator = Draft202012Validator(_committed_schema())
    fixtures = sorted(FIXTURES_DIR.glob("*.json"))
    assert fixtures, "expected at least one fixture in fixtures/"
    for path in fixtures:
        raw = json.loads(path.read_text())
        errors = list(validator.iter_errors(raw))
        assert not errors, f"{path.name} fails schema validation: {errors}"


def test_fixtures_parse_as_cnd_manifest():
    for path in sorted(FIXTURES_DIR.glob("*.json")):
        CndManifest.model_validate_json(path.read_text())
