"""Regenerate the declaration -> CND golden fixtures in
``fixtures/declaration/``.

These are "expected CND" artifacts (docs/adr/0019, docs/adr/0020 §4):
the committed CND a given declaration must build to. The comparison in
``tests/test_builder.py::TestGoldenFixtures`` is a scrubbed dict equality
(every ``id`` and ``built_at`` erased on both sides, since those are
freshly minted every run) rather than a byte diff, so hand-editing a
committed fixture to add a field is easy to get away with — but it
leaves the file's key order and its ``id``/``built_at`` values
disagreeing with what the builder actually emits, which shows up as
needless churn the next time this script runs, or in ``cnd build |
diff``. Regenerating from the builder keeps the fixture an honest,
reproducible snapshot of real output rather than a hand-maintained copy
of one.

    uv run python scripts/regen_declaration_golden.py
"""

import json
from pathlib import Path

import yaml

from cnd.builder import build
from cnd.declaration import Declaration

ROOT = Path(__file__).resolve().parent.parent
FIXTURES = ROOT / "fixtures" / "declaration"

#: (declaration fixture, CND golden fixture, numbering) triples — kept in
#: sync with tests/test_builder.py::TestGoldenFixtures's parametrize list.
CASES = [
    ("article.decl.yaml", "article.cnd", False),
    ("numbered.decl.yaml", "numbered.cnd", True),
]


def main() -> None:
    for decl_name, cnd_name, numbering in CASES:
        decl = Declaration.model_validate(
            yaml.safe_load((FIXTURES / decl_name).read_text("utf-8"))
        )
        built = build(decl, numbering=numbering)
        path = FIXTURES / cnd_name
        path.write_text(
            json.dumps(json.loads(built.model_dump_json()), indent=2, ensure_ascii=False)
            + "\n",
            encoding="utf-8",
        )
        print(f"wrote {path.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
