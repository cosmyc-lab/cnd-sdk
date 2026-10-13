"""The converters on 0.5 documents: blocks rendered once, markers read
from every text of a block, pools holding blocks, document metadata
(docs/proposals/0013)."""

from datetime import datetime, timezone
from uuid import uuid4

import pytest
from markdown_it import MarkdownIt

from factories import cell, item, para, rt

from cnd.converters import HtmlConverter, MarkdownConverter, iter_body, resolve_markers
from cnd.converters.markdown import format_bib_entry
from cnd.core.cnd import BibEntry, Cnd, DocMetadata, Footnote
from cnd.core.nodes import (
    AdmonitionNode,
    FigureNode,
    HeadingNode,
    LayoutNode,
    ListNode,
    QuoteNode,
    TableNode,
)
from cnd.core.render import MarkdownRenderer
from cnd.core.text import FootnoteRef, LinkRef, Mark, NodeRef


def _cnd(nodes, **kwargs) -> Cnd:
    doc = kwargs.pop("doc", DocMetadata(title="T"))
    return Cnd(
        cnd_version="0.5.0",
        built_at=datetime(2026, 10, 13, tzinfo=timezone.utc),
        doc=doc,
        nodes=nodes,
        **kwargs,
    )


def _heading(*children) -> HeadingNode:
    return HeadingNode(
        type="heading", id=uuid4(), level=1, text=rt("H"), heading_path=["H"],
        children=list(children),
    )


def _containers() -> list:
    lst = ListNode(type="list", id=uuid4(), items=[item("in a list")])
    table = TableNode(
        type="table", id=uuid4(), kind="content",
        cells=[cell(0, 0, "head", is_header=True), cell(1, 0, "in a cell")],
    )
    quote = QuoteNode(type="quote", id=uuid4(), children=[para("in a quote")])
    return [lst, table, quote]


class TestRenderOnce:
    @pytest.mark.parametrize("converter_cls", [MarkdownConverter, HtmlConverter])
    def test_nested_content_renders_once(self, converter_cls) -> None:
        text = converter_cls().convert(_cnd([_heading(*_containers())])).text
        for phrase in ("in a list", "in a cell", "in a quote"):
            assert text.count(phrase) == 1, phrase

    def test_iter_body_descends_only_into_headings(self) -> None:
        heading = _heading(*_containers())
        walked = [visit.node for visit in iter_body(_cnd([heading]))]
        assert walked == [heading, *heading.children]


class TestMarkers:
    def test_markers_of_nested_paragraphs_reach_the_block(self) -> None:
        target = para("target", label="t")
        lst = ListNode(
            type="list", id=uuid4(),
            items=[item(para(rt("see it", refs=[NodeRef(label="t", text_span=[4, 6])])))],
        )
        out = MarkdownConverter().convert(_cnd([target, lst])).text
        assert "- see it\n\n[t]" in out

    def test_html_markers_of_nested_paragraphs_reach_the_block(self) -> None:
        target = para("target", label="t")
        lst = ListNode(
            type="list", id=uuid4(),
            items=[item(para(rt("see it", refs=[NodeRef(label="t", text_span=[4, 6])])))],
        )
        out = HtmlConverter().convert(_cnd([target, lst])).text
        assert (
            '<ul><li>see it</li></ul>\n'
            '<span class="cnd-markers"><a class="cnd-ref" href="#t">[t]</a></span>'
        ) in out
        assert out.count('href="#t"') == 1

    def _parse(self, node, target):
        out = MarkdownConverter().convert(_cnd([target, node])).text
        body = out.split("\n---\n", 1)[1]
        return MarkdownIt("commonmark").enable("table").parse(body)

    @staticmethod
    def _marker_paragraph(tokens, marker):
        inline = [i for i, t in enumerate(tokens) if t.type == "inline" and t.content == marker]
        assert len(inline) == 1
        assert tokens[inline[0] - 1].type == "paragraph_open"
        return inline[0]

    @staticmethod
    def _inside(tokens, open_type, close_type, marker):
        start = max(i for i, t in enumerate(tokens) if t.type == open_type)
        end = next(i for i in range(start, len(tokens)) if tokens[i].type == close_type)
        return any(t.content == marker for t in tokens[start:end] if t.type == "inline")

    def test_marker_under_a_list_is_its_own_paragraph(self) -> None:
        lst = ListNode(type="list", id=uuid4(),
                       items=[item(para(rt("see", refs=[NodeRef(label="t", text_span=[0, 3])])))])
        tokens = self._parse(lst, para("target", label="t"))
        self._marker_paragraph(tokens, "[t]")
        assert not self._inside(tokens, "list_item_open", "list_item_close", "[t]")

    def test_marker_under_a_table_is_not_a_row(self) -> None:
        link = LinkRef(href="http://x", text_span=[0, 1])
        table = TableNode(type="table", id=uuid4(), kind="content", cells=[
            cell(0, 0, "h", is_header=True), cell(1, 0, None, children=[para(rt("c", links=[link]))]),
        ])
        tokens = self._parse(table, para("target", label="t"))
        self._marker_paragraph(tokens, "[http://x](http://x)")
        assert len([t for t in tokens if t.type in ("td_open", "th_open")]) == 2

    def test_marker_under_a_quote_is_its_own_paragraph(self) -> None:
        quote = QuoteNode(type="quote", id=uuid4(),
                          children=[para(rt("see", refs=[NodeRef(label="t", text_span=[0, 3])]))])
        tokens = self._parse(quote, para("target", label="t"))
        self._marker_paragraph(tokens, "[t]")
        assert not self._inside(tokens, "blockquote_open", "blockquote_close", "[t]")

    def test_spans_of_two_texts_are_never_compared(self) -> None:
        figure = FigureNode(
            type="figure", id=uuid4(), kind="image",
            caption=rt("caption with a late ref", refs=[NodeRef(label="b", text_span=[20, 23])]),
            description=rt("early", refs=[NodeRef(label="a", text_span=[0, 5])]),
        )
        cnd = _cnd([figure, para("a", label="a"), para("b", label="b")])
        labels = [marker.label for marker in resolve_markers(cnd, figure, [])]
        assert labels == ["b", "a"]  # caption first, then description

    def test_unresolved_label_names_the_node_holding_the_edge(self) -> None:
        inner = para(rt("x", refs=[NodeRef(label="nowhere")]))
        lst = ListNode(type="list", id=uuid4(), items=[item(inner)])
        warnings: list[str] = []
        resolve_markers(_cnd([lst]), lst, warnings)
        assert warnings == [f"unresolved refs label 'nowhere' on node {inner.id}"]

    def test_links_come_back_unresolved_without_warning(self) -> None:
        node = para(rt("site", links=[LinkRef(href="https://example.com", text_span=[0, 4])]))
        warnings: list[str] = []
        [marker] = resolve_markers(_cnd([node]), node, warnings)
        assert marker.family == "links" and marker.target is None and warnings == []


class TestPools:
    def _with_footnote(self) -> Cnd:
        note = Footnote(id=uuid4(), label="fn", children=[para("First."), para("Second.")])
        body = para(rt("Text.", footnotes=[FootnoteRef(label="fn", text_span=[4, 5])]))
        return _cnd([body], footnotes=[note])

    def test_markdown_footnote_holds_several_blocks(self) -> None:
        # Pandoc and GFM footnotes: a further paragraph is indented 4 spaces.
        out = MarkdownConverter().convert(self._with_footnote()).text
        assert "[^fn]: First.\n\n    Second." in out

    def test_formatted_reference_keeps_its_marks(self) -> None:
        entry = BibEntry(
            id=uuid4(), label="k",
            formatted=rt("Knuth. The TeXbook.", marks=[Mark(start=7, end=18, kind="emph")]),
        )
        cnd = _cnd([para("x")], bibliography=[entry])
        assert "- **k** — Knuth. *The TeXbook*." in MarkdownConverter().convert(cnd).text

    def test_format_bib_entry_returns_rich_text(self) -> None:
        entry = BibEntry(id=uuid4(), label="k", authors=["A"], year=2020)
        reference, warning = format_bib_entry(entry)
        assert reference.value == "A. (2020)" and warning is not None


class TestDocumentMetadata:
    def _doc(self) -> DocMetadata:
        return DocMetadata(
            title="Guide", status="Approved", version="1.2",
            extra={"client": "ACME", "reference": "PRJ-042"},
        )

    def test_markdown_front_matter(self) -> None:
        head = MarkdownConverter().convert(_cnd([], doc=self._doc())).text.split("---\n")[1]
        assert (
            'status: "Approved"\nversion: "1.2"\nextra:\n'
            '  "client": "ACME"\n  "reference": "PRJ-042"\n'
        ) in head


class TestTextOnly:
    def test_text_only_threads_into_the_default_renderer(self) -> None:
        converter = MarkdownConverter(text_only=True)
        assert converter.renderer.text_only is True
        assert MarkdownConverter().renderer.text_only is False

    def test_text_only_with_an_injected_renderer_is_refused(self) -> None:
        with pytest.raises(ValueError):
            MarkdownConverter(MarkdownRenderer(), text_only=True)

    def test_text_only_document_has_no_html(self, elements_cnd_path) -> None:
        cnd = Cnd.model_validate_json(elements_cnd_path.read_text())
        out = MarkdownConverter(text_only=True).convert(cnd).text
        kinds = {t.type for t in MarkdownIt("commonmark").enable("table").parse(out)}
        assert not kinds & {"html_block", "html_inline"}
        inline = [
            child.type
            for t in MarkdownIt("commonmark").enable("table").parse(out)
            for child in (t.children or [])
        ]
        assert "html_inline" not in inline


def test_explicit_defaults_twin_converts_identically(elements_cnd_path) -> None:
    explicit = elements_cnd_path.with_name("elements_explicit.cnd")
    a = MarkdownConverter().convert(Cnd.model_validate_json(elements_cnd_path.read_text()))
    b = MarkdownConverter().convert(Cnd.model_validate_json(explicit.read_text()))
    assert a.text == b.text


# -- HTML ---------------------------------------------------------------


class TestHtml:
    def test_links_are_not_rendered_as_unresolved(self) -> None:
        node = para(rt("site", links=[LinkRef(href="https://example.com", text_span=[0, 4])]))
        html = HtmlConverter().convert(_cnd([node])).text
        assert 'class="cnd-unresolved"' not in html

    def test_footnote_holds_its_blocks(self) -> None:
        note = Footnote(id=uuid4(), label="fn", children=[para("First."), para("Second.")])
        out = HtmlConverter().convert(_cnd([para("x")], footnotes=[note])).text
        assert '<li id="fn"><p>First.</p><p>Second.</p></li>' in out

    def test_formatted_reference_keeps_its_marks(self) -> None:
        entry = BibEntry(
            id=uuid4(), label="k",
            formatted=rt("Knuth. The TeXbook.", marks=[Mark(start=7, end=18, kind="emph")]),
        )
        out = HtmlConverter().convert(_cnd([para("x")], bibliography=[entry])).text
        assert '<li id="k">Knuth. <em>The TeXbook</em>.</li>' in out

    def test_head_carries_status_version_and_extra(self) -> None:
        doc = DocMetadata(title="Guide", status="Approved", version="1.2", extra={"client": "ACME"})
        text = HtmlConverter().convert(_cnd([], doc=doc)).text
        assert '<meta name="status" content="Approved">' in text
        assert '<meta name="version" content="1.2">' in text
        assert '<meta name="client" content="ACME">' in text

    def test_explicit_defaults_twin_converts_identically(self, elements_cnd_path) -> None:
        explicit = elements_cnd_path.with_name("elements_explicit.cnd")
        a = HtmlConverter().convert(Cnd.model_validate_json(elements_cnd_path.read_text()))
        b = HtmlConverter().convert(Cnd.model_validate_json(explicit.read_text()))
        assert a.text == b.text


# -- headings nested in containers and footnotes --------------------------


def _section_heading() -> HeadingNode:
    """A heading whose section holds one paragraph with a ref marker."""
    child = para(rt("SECTION-TEXT", refs=[NodeRef(label="tgt-c1", text_span=[0, 7])]))
    return HeadingNode(
        type="heading", id=uuid4(), level=3, text=rt("Inner"), heading_path=["Inner"],
        children=[child],
    )


def _holding(kind: str):
    heading = _section_heading()
    if kind == "quote":
        return QuoteNode(type="quote", id=uuid4(), children=[heading])
    if kind == "list item":
        return ListNode(type="list", id=uuid4(), items=[item(heading)])
    if kind == "admonition":
        return AdmonitionNode(type="admonition", id=uuid4(), kind="note", children=[heading])
    if kind == "table cell":
        return TableNode(type="table", id=uuid4(), kind="content", cells=[
            cell(0, 0, "head", is_header=True), cell(1, 0, None, children=[heading]),
        ])
    if kind == "layout cell":
        return LayoutNode(type="layout", id=uuid4(), cells=[cell(0, 0, None, children=[heading])])
    if kind == "figure":
        return FigureNode(type="figure", id=uuid4(), kind="other", children=[heading])
    raise AssertionError(kind)


_CONTAINERS = ["quote", "list item", "admonition", "table cell", "layout cell", "figure"]
_CONVERTERS = {
    "markdown": (lambda: MarkdownConverter(), "[tgt-c1]"),
    "markdown text_only": (lambda: MarkdownConverter(text_only=True), "[tgt-c1]"),
    "html": (lambda: HtmlConverter(), 'href="#tgt-c1"'),
}


def _assert_once_with_its_text(out: str, marker: str) -> None:
    assert out.count("Inner") == 1
    assert out.count("SECTION-TEXT") == 1
    assert out.count(marker) == 1
    assert out.index("SECTION-TEXT") < out.index(marker)


class TestNestedHeadings:
    @pytest.mark.parametrize("converter", list(_CONVERTERS))
    @pytest.mark.parametrize("container", _CONTAINERS)
    def test_a_heading_in_a_container_keeps_its_section(self, container, converter) -> None:
        make, marker = _CONVERTERS[converter]
        target = para("target", label="tgt-c1")
        out = make().convert(_cnd([target, _holding(container)])).text
        _assert_once_with_its_text(out, marker)

    @pytest.mark.parametrize("converter", list(_CONVERTERS))
    def test_a_heading_in_a_footnote_keeps_its_section(self, converter) -> None:
        make, marker = _CONVERTERS[converter]
        note = Footnote(id=uuid4(), label="fn", children=[para("Intro."), _section_heading()])
        body = para(rt("Text.", footnotes=[FootnoteRef(label="fn", text_span=[4, 5])]))
        target = para("target", label="tgt-c1")
        out = make().convert(_cnd([body, target], footnotes=[note])).text
        _assert_once_with_its_text(out, marker)
        notes = out[out.index("Footnotes"):]
        assert notes.index("Intro.") < notes.index("Inner") < notes.index("SECTION-TEXT")

    def test_a_heading_in_a_footnote_keeps_the_markdown_structure(self) -> None:
        note = Footnote(id=uuid4(), label="fn", children=[para("Intro."), _section_heading()])
        body = para(rt("Text.", footnotes=[FootnoteRef(label="fn", text_span=[4, 5])]))
        out = MarkdownConverter().convert(_cnd([body, para("t", label="tgt-c1")], footnotes=[note])).text
        assert "[^fn]: Intro.\n\n    ### Inner\n\n    SECTION-TEXT\n    [tgt-c1]" in out

    def test_nested_sections_expand_in_pre_order(self) -> None:
        deep = HeadingNode(
            type="heading", id=uuid4(), level=4, text=rt("Deep"), heading_path=["Deep"],
            children=[para("DEEP-TEXT")],
        )
        outer = HeadingNode(
            type="heading", id=uuid4(), level=3, text=rt("Outer"), heading_path=["Outer"],
            children=[deep, para("AFTER-DEEP")],
        )
        quote = QuoteNode(type="quote", id=uuid4(), children=[outer])
        out = MarkdownRenderer().render(quote)
        assert out == "> ### Outer\n>\n> #### Deep\n>\n> DEEP-TEXT\n>\n> AFTER-DEEP"


class TestFrontMatterScalars:
    CONTROLS = (
        [chr(c) for c in range(0x20) if chr(c) not in "\n\r\t"]
        + ["\x7f", "\x85", " ", " "]
    )

    @pytest.mark.parametrize("ch", CONTROLS)
    def test_a_control_character_is_escaped(self, ch: str) -> None:
        from cnd.converters.markdown import _yaml_scalar

        out = _yaml_scalar(f"a{ch}b")
        assert out == f'"a\\u{ord(ch):04x}b"'
        assert ch not in out

    def test_front_matter_parses_back(self) -> None:
        yaml = pytest.importorskip("yaml")
        nasty = "t\x00i\x1bt\x7fl\x85e x y \"q\" \\ \n\r\t"
        doc = DocMetadata(title=nasty, extra={"k\x01": "v "})
        text = MarkdownConverter().convert(_cnd([para("x")], doc=doc)).text
        front = text.split("---\n")[1]
        assert " " not in front and "\x85" not in front
        data = yaml.safe_load(front)
        assert data["title"] == nasty
        assert data["extra"] == {"k\x01": "v "}


class TestHtmlMetaExtra:
    @pytest.mark.parametrize("key", [
        "author", "description", "keywords", "date", "status", "version", "viewport",
        "Author", " DESCRIPTION ",
    ])
    def test_a_key_the_converter_emits_is_skipped_with_a_warning(self, key: str) -> None:
        doc = DocMetadata(title="T", description="real", extra={key: "spoof", "team": "core"})
        result = HtmlConverter().convert(_cnd([para("x")], doc=doc))
        assert "spoof" not in result.text
        assert '<meta name="team" content="core">' in result.text
        assert '<meta name="description" content="real">' in result.text
        assert any(repr(key) in w and "extra" in w for w in result.warnings)

    def test_other_keys_do_not_warn(self) -> None:
        doc = DocMetadata(title="T", extra={"team": "core"})
        result = HtmlConverter().convert(_cnd([para("x")], doc=doc))
        assert result.warnings == ()
