"""The converters on 0.5 documents: blocks rendered once, markers read
from every text of a block, pools holding blocks, document metadata
(docs/proposals/0013)."""

from datetime import datetime, timezone
from uuid import uuid4

import pytest
from markdown_it import MarkdownIt

from factories import cell, item, para, rt

from cnd.converters import MarkdownConverter, iter_body, resolve_markers
from cnd.converters.markdown import format_bib_entry
from cnd.core.cnd import BibEntry, Cnd, DocMetadata, Footnote
from cnd.core.nodes import (
    FigureNode,
    HeadingNode,
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
    @pytest.mark.parametrize("converter_cls", [MarkdownConverter])
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
