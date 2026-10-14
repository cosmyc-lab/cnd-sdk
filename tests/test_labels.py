"""Labels written into the converters' output: hostile labels stay
inert, and every footnote reference still resolves to its definition."""

from datetime import datetime, timezone
from html.parser import HTMLParser
from urllib.parse import unquote
from uuid import uuid4

import pytest
from markdown_it import MarkdownIt
from mdit_py_plugins.footnote import footnote_plugin

from factories import para, rt

from cnd.converters import HtmlConverter, MarkdownConverter
from cnd.converters.markdown import markdown_label
from cnd.core.cnd import BibEntry, Cnd, DocMetadata, Footnote
from cnd.core.text import CiteRef, FootnoteRef, NodeRef

HOSTILE = [
    "x](ms-msdt:e)",
    '"](javascript:alert(1)) [y',
    "a b",
    "]] [[",
    "<img src=x onerror=alert(1)>",
    "a b\u0085c\nd\r# e",
    "p%20q",
    "p q",
    "^x",
    "_x_",
    "fig-é",
]


def _cnd(labels: list[str], *, supplement: str | None = None) -> Cnd:
    targets = [para(f"target {i}", label=f"t{i}-{label}") for i, label in enumerate(labels)]
    text = rt(
        "body",
        refs=[NodeRef(label=f"t{i}-{label}") for i, label in enumerate(labels)],
        footnotes=[FootnoteRef(label=f"fn{i}-{label}") for i, label in enumerate(labels)],
        cites=[CiteRef(label=f"b{i}-{label}", supplement=supplement) for i, label in enumerate(labels)]
        + [CiteRef(label=f"b{i}-{label}", form="prose", supplement=supplement)
           for i, label in enumerate(labels)],
    )
    return Cnd(
        cnd_version="0.5.0",
        built_at=datetime(2026, 10, 13, tzinfo=timezone.utc),
        doc=DocMetadata(title="T"),
        nodes=[para(text), *targets],
        footnotes=[Footnote(id=uuid4(), label=f"fn{i}-{label}", children=[para("note")])
                   for i, label in enumerate(labels)],
        bibliography=[BibEntry(id=uuid4(), label=f"b{i}-{label}", formatted=rt("Ref."))
                      for i, label in enumerate(labels)],
    )


def _tokens(markdown: str) -> list:
    body = markdown.split("---\n", 2)[-1]
    tokens = MarkdownIt("commonmark").use(footnote_plugin).parse(body)
    flat = list(tokens)
    for token in tokens:
        flat.extend(token.children or [])
    return flat


class TestMarkdownLabels:
    @pytest.mark.parametrize("label", HOSTILE)
    def test_a_hostile_label_stays_inert(self, label: str) -> None:
        out = MarkdownConverter().convert(_cnd([label])).text
        types = [t.type for t in _tokens(out)]
        assert "link_open" not in types
        assert not {"html_inline", "html_block", "image"} & set(types)
        assert types.count("heading_open") == 2  # Footnotes, Bibliography

    def test_every_footnote_reference_resolves(self) -> None:
        out = MarkdownConverter().convert(_cnd(HOSTILE)).text
        tokens = _tokens(out)
        refs = [t for t in tokens if t.type == "footnote_ref"]
        defs = [t for t in tokens if t.type == "footnote_open"]
        assert len(refs) == len(defs) == len(HOSTILE)
        assert {t.meta["id"] for t in refs} == {t.meta["id"] for t in defs}
        body = out.split("---\n", 2)[-1]
        rendered = MarkdownIt("commonmark").use(footnote_plugin).render(body)
        assert "[^" not in rendered

    @pytest.mark.parametrize("supplement", [
        "x](ms-msdt:e)", "<img src=x onerror=alert(1)>", "p.\n\n# 4",
    ])
    def test_a_hostile_cite_supplement_stays_inert(self, supplement: str) -> None:
        out = MarkdownConverter().convert(_cnd(["k"], supplement=supplement)).text
        types = [t.type for t in _tokens(out)]
        assert "link_open" not in types
        assert not {"html_inline", "html_block"} & set(types)
        assert types.count("heading_open") == 2

    @pytest.mark.parametrize("label", ["fig-1", "eq:2", "fig_1", "durand2025", "fig-é", "ünïcode.v2"])
    def test_ordinary_labels_are_unchanged(self, label: str) -> None:
        assert markdown_label(label) == label

    @pytest.mark.parametrize(
        "pair",
        [
            ("Fn", "fn"),
            ("FIG-1", "fig-1"),
            ("ß", "ss"),
            ("ß", "SS"),
            ("\u212a", "k"),  # KELVIN SIGN folds to k
            ("ς", "σ"),  # final sigma folds to sigma
            ("Ünïcode", "ünïcode"),
            ("ﬁx", "fix"),  # the fi ligature folds to "fi"
        ],
    )
    def test_labels_differing_only_by_case_stay_apart(self, pair: tuple[str, str]) -> None:
        """CommonMark and GFM match labels after Unicode case folding, so
        two distinct labels must not fold to one mapped label (CND-38)."""
        a, b = pair
        assert markdown_label(a).casefold() != markdown_label(b).casefold()

    def test_mapped_labels_are_fixed_points_of_case_folding_except_hex(self) -> None:
        """Every kept character folds to itself; only the upper-case hex
        digits of an escape fold, and those decode the same either way."""
        for label in HOSTILE + ["Fn", "ß", "\u212a", "ς", "ﬁx", "Ünïcode.v2"]:
            mapped = markdown_label(label)
            assert unquote(mapped.casefold()) == unquote(mapped) == label

    def test_no_two_characters_meet_under_any_label_normalization(self) -> None:
        """Every code point of the Basic Multilingual Plane, as a one-character
        label, stays distinct under Python case folding and under
        markdown-it's ``normalizeReference`` (lower then upper), which is
        how a JavaScript-based reader compares labels. Dotless ``ı`` and
        ``i`` meet under the second one only."""
        from markdown_it.common.utils import normalizeReference

        chars = [chr(cp) for cp in range(0x10000) if not 0xD800 <= cp <= 0xDFFF]
        mapped = [markdown_label(ch) for ch in chars]
        assert len({m.casefold() for m in mapped}) == len(chars)
        assert len({normalizeReference(m) for m in mapped}) == len(chars)

    def test_dotless_i_stays_apart_from_i(self) -> None:
        from markdown_it.common.utils import normalizeReference

        assert normalizeReference(markdown_label("\u0131")) != normalizeReference(markdown_label("i"))

    def test_case_variants_resolve_to_their_own_footnote(self) -> None:
        """Footnotes ``Fn`` and ``fn`` keep separate definitions under a
        case-insensitive reader: no two definition labels fold alike."""
        labels = ["Fn", "fn", "ß", "ss", "SS"]
        defs = {markdown_label(label).casefold() for label in labels}
        assert len(defs) == len(labels)

    def test_the_mapping_is_injective(self) -> None:
        """``unquote`` undoes it, so no two labels map to one."""
        labels = HOSTILE + ["a%b", "a%25b", "a b", "a%20b", "\x00", "\U0001f600", "a\tb", "a b"]
        for label in labels:
            mapped = markdown_label(label)
            assert unquote(mapped) == label
            assert not any(ch.isspace() or ch in "[]^<>&\\`*\"'()!" for ch in mapped)
        assert len({markdown_label(label) for label in labels}) == len(set(labels))


class _Tags(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.tags: list[str] = []
        self.hrefs: list[str] = []

    def handle_starttag(self, tag, attrs) -> None:
        self.tags.append(tag)
        self.hrefs.extend(value for name, value in attrs if name == "href")


class TestHtmlLabels:
    @pytest.mark.parametrize("label", HOSTILE)
    def test_a_hostile_label_adds_no_element(self, label: str) -> None:
        plain = HtmlConverter().convert(_cnd(["k"])).text
        hostile = HtmlConverter().convert(_cnd([label])).text
        expected, got = _Tags(), _Tags()
        expected.feed(plain)
        got.feed(hostile)
        assert got.tags == expected.tags
        assert got.hrefs and all(href.startswith("#") for href in got.hrefs)
