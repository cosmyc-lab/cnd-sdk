"""Regenerate the converter golden documents in ``tests/golden/``.

Golden outputs are converter output committed verbatim, so a change in
converter output shows up as a reviewable diff. They are **not**
normative (spec §7): nothing in the format depends on their shape.

    uv run python scripts/regen_converters_golden.py
"""

from pathlib import Path

from cnd.converters import HtmlConverter, MarkdownConverter
from cnd.core.cnd import Cnd

ROOT = Path(__file__).resolve().parent.parent
FIXTURES = ROOT / "fixtures"
GOLDEN = ROOT / "tests" / "golden"

#: (fixture stem, converter class) pairs the golden corpus covers.
CASES = [
    ("full_coverage", MarkdownConverter),
    ("full_coverage", HtmlConverter),
    ("comprehensive", MarkdownConverter),
    ("comprehensive", HtmlConverter),
    ("unpaginated", MarkdownConverter),
    ("unpaginated", HtmlConverter),
    ("minimal", MarkdownConverter),
]


def golden_path(stem: str, converter_cls: type) -> Path:
    return GOLDEN / f"{stem}.{converter_cls.extension}"


def main() -> None:
    GOLDEN.mkdir(parents=True, exist_ok=True)
    for stem, converter_cls in CASES:
        cnd = Cnd.model_validate_json((FIXTURES / f"{stem}.cnd").read_text("utf-8"))
        result = converter_cls().convert(cnd)
        path = golden_path(stem, converter_cls)
        path.write_text(result.text, encoding="utf-8")
        print(f"wrote {path.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
