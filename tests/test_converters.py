"""Outbound converter tests (docs/proposals/0007).

Golden full-document outputs live in ``tests/golden/`` and are
regenerated with ``uv run python scripts/regen_converters_golden.py``.
They pin converter output so a change is a reviewable diff; they are
**not** normative — spec §7 makes rendering and conversion informative.
"""

from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID

import pytest

from cnd.converters import (
    ConversionResult,
    HtmlConverter,
    HtmlNodeRenderer,
    MarkdownConverter,
    format_bib_entry,
    iter_body,
)
from cnd.core.cnd import BibEntry, Cnd, DocMetadata, Footnote
from cnd.core.nodes import CiteRef, FigureNode, ImageNode, NodeRef, ParagraphNode
from cnd.core.render import MarkdownRenderer

FIXTURES_DIR = Path(__file__).parent.parent / "fixtures"
GOLDEN_DIR = Path(__file__).parent / "golden"

ALL_FIXTURES = [
    "minimal",
    "structured",
    "comprehensive",
    "rich_content",
    "full_coverage",
    "unpaginated",
]

# full_coverage exercises both pools; comprehensive has neither;
# unpaginated carries the one fixture entry with ``formatted=None``.
GOLDEN_CASES = [
    ("full_coverage", MarkdownConverter),
    ("full_coverage", HtmlConverter),
    ("comprehensive", MarkdownConverter),
    ("comprehensive", HtmlConverter),
    ("unpaginated", MarkdownConverter),
    ("unpaginated", HtmlConverter),
    ("minimal", MarkdownConverter),
]


def load(stem: str) -> Cnd:
    return Cnd.model_validate_json((FIXTURES_DIR / f"{stem}.cnd").read_text("utf-8"))


# -- golden documents ---------------------------------------------------


@pytest.mark.parametrize(
    ("stem", "converter_cls"),
    GOLDEN_CASES,
    ids=[f"{stem}-{cls.extension}" for stem, cls in GOLDEN_CASES],
)
def test_golden_document(stem: str, converter_cls: type) -> None:
    expected = (GOLDEN_DIR / f"{stem}.{converter_cls.extension}").read_text("utf-8")
    result = converter_cls().convert(load(stem))
    assert result.text == expected


@pytest.mark.parametrize("stem", ALL_FIXTURES)
@pytest.mark.parametrize("converter_cls", [MarkdownConverter, HtmlConverter])
def test_every_fixture_converts_without_defect_warnings(
    stem: str, converter_cls: type
) -> None:
    """No fixture is a defective document, so none warns about a link.

    The bibliography fallback is not a defect — ``formatted`` is nullable
    since 0.3.0 — so that warning is allowed through.
    """
    result = converter_cls().convert(load(stem))
    assert isinstance(result, ConversionResult)
    assert result.text
    assert [w for w in result.warnings if "formatted" not in w] == []


# -- assembly -----------------------------------------------------------


def test_markdown_front_matter_carries_doc_metadata() -> None:
    text = MarkdownConverter().convert(load("full_coverage")).text
    head = text.split("---\n")[1]
    assert 'title: "Rapport d\'essais du banc de mesure' in head
    assert '  - "Équipe CND"' in head
    assert "date: 2026-07-15" in head
    assert 'lang: "fr"' in head
    assert 'cnd_version: "0.3.0"' in head


def test_figure_children_render_once() -> None:
    """A figure is a wrapper: its renderer owns the children, the walk prunes
    them. The wrapped image must not appear twice."""
    text = MarkdownConverter().convert(load("full_coverage")).text
    assert text.count("figures/banc.png") == 1
    html = HtmlConverter().convert(load("full_coverage")).text
    assert html.count("figures/banc.png") == 1


def test_iter_body_prunes_figure_subtrees() -> None:
    cnd = load("full_coverage")
    walked = [visit.node for visit in iter_body(cnd)]
    figures = [node for node in walked if isinstance(node, FigureNode)]
    assert figures, "fixture must contain figures"
    for figure in figures:
        for child in figure.children:
            assert child not in walked


def test_pool_sections_present_when_pools_are() -> None:
    text = MarkdownConverter().convert(load("full_coverage")).text
    assert "## Footnotes" in text
    assert "[^fn-unit]: Toutes les valeurs" in text
    assert "## Bibliography" in text
    assert "- **nguyen2023** — Nguyen, T. (2023)." in text


def test_pool_sections_absent_when_pools_are() -> None:
    for converter_cls in (MarkdownConverter, HtmlConverter):
        text = converter_cls().convert(load("comprehensive")).text
        assert "Footnotes" not in text
        assert "Bibliography" not in text


def test_pool_sections_use_pool_order() -> None:
    cnd = load("full_coverage")
    text = MarkdownConverter().convert(cnd).text
    labels = [entry.label for entry in cnd.bibliography]
    positions = [text.index(f"- **{label}**") for label in labels]
    assert positions == sorted(positions)


def test_section_titles_are_overridable() -> None:
    converter = MarkdownConverter(
        footnotes_title="Notes", bibliography_title="Références"
    )
    text = converter.convert(load("full_coverage")).text
    assert "## Notes" in text
    assert "## Références" in text


# -- markers ------------------------------------------------------------


def test_markers_follow_text_span_order() -> None:
    text = MarkdownConverter().convert(load("full_coverage")).text
    line = next(
        line for line in text.splitlines() if line.startswith("[@durand2025, p. 42]")
    )
    # spans: cites[4,11], footnotes[12,21], refs[48,65], cites[68,77];
    # the span-less refs edge sorts last (spec §8).
    assert line == "[@durand2025, p. 42] [^fn-unit] [tab-mesures] @durand2025 [fig-atom]"


def test_silent_citation_emits_no_marker() -> None:
    text = MarkdownConverter().convert(load("full_coverage")).text
    line = next(line for line in text.splitlines() if line.startswith("[grid-layout]"))
    # form="none" on the fourth cites edge: three markers, not four.
    assert line == "[grid-layout] [^fn-proto] [@nguyen2023] @durand2025 @nguyen2023"


def test_html_markers_are_links_to_pool_anchors() -> None:
    text = HtmlConverter().convert(load("full_coverage")).text
    assert '<a class="cnd-cite" href="#durand2025">[durand2025, p. 42]</a>' in text
    assert '<sup class="cnd-footnote"><a href="#fn-unit">fn-unit</a></sup>' in text
    assert '<li id="fn-unit">' in text
    assert '<li id="durand2025">' in text


def test_unresolvable_label_warns_and_degrades() -> None:
    cnd = _tiny_cnd(
        nodes=[
            ParagraphNode(
                type="paragraph",
                id=UUID("00000000-0000-4000-f000-000000000001"),
                text="Dangling.",
                refs=[NodeRef(label="nowhere")],
            )
        ]
    )
    result = MarkdownConverter().convert(cnd)
    assert "[nowhere]" in result.text
    assert any("unresolved refs label 'nowhere'" in w for w in result.warnings)

    html = HtmlConverter().convert(cnd)
    assert '<span class="cnd-unresolved">[nowhere]</span>' in html.text


def test_wrong_family_domain_warns() -> None:
    """A ``cites`` edge that resolves to a footnote is out of domain."""
    cnd = _tiny_cnd(
        nodes=[
            ParagraphNode(
                type="paragraph",
                id=UUID("00000000-0000-4000-f000-000000000002"),
                text="Mis-filed.",
                cites=[CiteRef(label="fn-a")],
            )
        ],
        footnotes=[
            Footnote(
                id=UUID("00000000-0000-4000-f000-000000000003"),
                label="fn-a",
                text="A note.",
            )
        ],
    )
    result = MarkdownConverter().convert(cnd)
    assert any("outside its family domain" in w for w in result.warnings)


# -- bibliography -------------------------------------------------------


def test_formatted_is_preferred_verbatim() -> None:
    entry = BibEntry(
        id=UUID("00000000-0000-4000-f000-000000000010"),
        label="smith2024",
        formatted="Smith, J. (2024). A styled reference. Journal, 1(1), 1–2.",
        authors=["Ignored, X."],
        title="Ignored title",
    )
    reference, warning = format_bib_entry(entry)
    assert reference == "Smith, J. (2024). A styled reference. Journal, 1(1), 1–2."
    assert warning is None


def test_unformatted_entry_falls_back_to_lifted_fields() -> None:
    """The composed fallback, field by field, on a CND built here — the
    fixture corpus is the conformance corpus and is never edited to suit a
    test."""
    entry = BibEntry(
        id=UUID("00000000-0000-4000-f000-000000000011"),
        label="lee2020",
        authors=["Lee, K.", "Ito, S."],
        title="Structured only",
        year=2020,
        container="Proceedings of Nothing",
        doi="10.1000/xyz",
        url="https://example.org/lee2020",
    )
    reference, warning = format_bib_entry(entry)
    assert reference == (
        "Lee, K., Ito, S.. (2020). Structured only. Proceedings of Nothing. "
        "doi:10.1000/xyz. https://example.org/lee2020"
    )
    assert warning is not None
    assert "no 'formatted' string" in warning


def test_unformatted_entry_warns_through_the_converter() -> None:
    cnd = _tiny_cnd(
        nodes=[
            ParagraphNode(
                type="paragraph",
                id=UUID("00000000-0000-4000-f000-000000000012"),
                text="Cited.",
                cites=[CiteRef(label="lee2020")],
            )
        ],
        bibliography=[
            BibEntry(
                id=UUID("00000000-0000-4000-f000-000000000013"),
                label="lee2020",
                authors=["Lee, K."],
                title="Structured only",
                year=2020,
            )
        ],
    )
    result = MarkdownConverter().convert(cnd)
    assert "- **lee2020** — Lee, K.. (2020). Structured only" in result.text
    assert any("no 'formatted' string" in w for w in result.warnings)


def test_unformatted_fixture_entry_warns_and_composes() -> None:
    """``unpaginated.cnd`` carries the corpus's one ``formatted=None`` entry."""
    result = MarkdownConverter().convert(load("unpaginated"))
    assert (
        "- **rivest1978** — Rivest, R.. (1978). On data banks and privacy "
        "homomorphisms" in result.text
    )
    assert any("rivest1978" in w and "no 'formatted' string" in w
               for w in result.warnings)


def test_entry_with_only_a_fields_blob_degrades_to_its_label() -> None:
    entry = BibEntry(
        id=UUID("00000000-0000-4000-f000-000000000014"),
        label="opaque",
        fields={"type": "book", "title": {"nested": "unread"}},
    )
    reference, warning = format_bib_entry(entry)
    assert reference == "opaque"
    assert warning is not None


# -- renderer injection -------------------------------------------------


def test_injected_renderer_changes_body_verbosity() -> None:
    cnd = load("full_coverage")
    terse = MarkdownConverter(MarkdownRenderer(tables="placeholder")).convert(cnd)
    assert "[[figure:" in terse.text
    assert "| Capteur | Nominal |" not in terse.text
    assert MarkdownConverter().default_renderer().tables == "inline"


def test_html_renderer_escapes_and_anchors() -> None:
    renderer = HtmlNodeRenderer()
    node = ParagraphNode(
        type="paragraph",
        id=UUID("00000000-0000-4000-f000-000000000020"),
        label="p-esc",
        text="a < b & c > d",
    )
    assert renderer.render(node) == (
        '<p id="p-esc">a &lt; b &amp; c &gt; d</p>'
    )


def test_html_image_without_path_degrades() -> None:
    renderer = HtmlNodeRenderer()
    node = ImageNode(
        type="image",
        id=UUID("00000000-0000-4000-f000-000000000021"),
        alt="No file",
    )
    assert renderer.render(node) == (
        '<span class="cnd-missing-image">No file</span>'
    )


def test_html_document_is_standalone() -> None:
    text = HtmlConverter().convert(load("minimal")).text
    assert text.startswith("<!DOCTYPE html>")
    assert text.rstrip().endswith("</html>")
    assert "<head>" in text and "</head>" in text
    assert "<style>" in text


def test_converter_metadata() -> None:
    assert MarkdownConverter.extension == "md"
    assert MarkdownConverter.media_type == "text/markdown"
    assert HtmlConverter.extension == "html"
    assert HtmlConverter.media_type == "text/html"


def test_conversion_result_str_is_the_document() -> None:
    result = MarkdownConverter().convert(load("minimal"))
    assert str(result) == result.text


# -- helpers ------------------------------------------------------------


def _tiny_cnd(*, nodes, bibliography=(), footnotes=()) -> Cnd:
    return Cnd(
        id=UUID("00000000-0000-4000-f000-000000000000"),
        cnd_version="0.3.0",
        built_at=datetime(2026, 7, 23, tzinfo=timezone.utc),
        doc=DocMetadata(title="Ad-hoc"),
        nodes=list(nodes),
        bibliography=list(bibliography),
        footnotes=list(footnotes),
    )
