import json
from pathlib import Path

from jsonschema import Draft202012Validator

from cnd import Cnd

ROOT = Path(__file__).parent.parent
SCHEMA_PATH = ROOT / "schema" / "cnd.schema.json"
FIXTURES_DIR = ROOT / "fixtures"


def _committed_schema() -> dict:
    return json.loads(SCHEMA_PATH.read_text())


def test_schema_matches_generated_model():
    committed = _committed_schema()
    generated = Cnd.model_json_schema()
    generated["$schema"] = committed["$schema"]
    generated["$id"] = committed["$id"]
    generated["title"] = committed["title"]
    assert generated == committed, (
        "schema/cnd.schema.json is out of sync with "
        "Cnd.model_json_schema() — regenerate and re-commit it."
    )


def test_fixtures_validate_against_schema():
    validator = Draft202012Validator(_committed_schema())
    fixtures = sorted(FIXTURES_DIR.glob("*.cnd"))
    assert fixtures, "expected at least one fixture in fixtures/"
    for path in fixtures:
        raw = json.loads(path.read_text())
        errors = list(validator.iter_errors(raw))
        assert not errors, f"{path.name} fails schema validation: {errors}"


def test_fixtures_parse_as_cnd():
    for path in sorted(FIXTURES_DIR.glob("*.cnd")):
        Cnd.model_validate_json(path.read_text())
