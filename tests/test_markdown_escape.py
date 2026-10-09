"""Markdown escaping for free text (Review Focus 1 and 5)."""

import pytest

from cnd.core.markdown_escape import escape_block, escape_inline


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("plain words", "plain words"),
        ("my_var_name", "my_var_name"),
        ("_lead and trail_", "\\_lead and trail\\_"),
        ("docs/**/*.md", "docs/\\*\\*/\\*.md"),
        ("a `tick`", "a \\`tick\\`"),
        ("see [x]", "see \\[x\\]"),
        ("~~gone~~", "\\~\\~gone\\~\\~"),
        ("<topic> and <reason>", "\\<topic> and \\<reason>"),
        ("1 < 2 and a<b", "1 < 2 and a\\<b"),
        ("&amp; &#123; & x", "\\&amp; \\&#123; & x"),
        ("C:\\Users\\me", "C:\\Users\\me"),
        ("end\\*", "end\\\\\\*"),
    ],
)
def test_escape_inline(raw: str, expected: str) -> None:
    assert escape_inline(raw) == expected


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("1. Keep the folders", "1\\. Keep the folders"),
        ("12) twelve", "12\\) twelve"),
        ("2026. A year", "2026\\. A year"),
        ("# not a heading", "\\# not a heading"),
        ("#hashtag", "#hashtag"),
        ("> not a quote", "\\> not a quote"),
        ("- not a bullet", "\\- not a bullet"),
        ("+ not a bullet", "\\+ not a bullet"),
        ("---", "\\---"),
        ("===", "\\==="),
        ("first line\n2. second", "first line\n2\\. second"),
        ("a - b", "a - b"),
    ],
)
def test_escape_block(raw: str, expected: str) -> None:
    assert escape_block(raw) == expected
