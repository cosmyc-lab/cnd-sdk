"""Markdown links written where their words are (docs/adr/0031), and the
link schemes a caller may allow on top of the URL rule."""

from datetime import datetime, timezone
from uuid import uuid4

import pytest
from markdown_it import MarkdownIt

from factories import cell, item, para, rt

from cnd.converters import HtmlConverter, MarkdownConverter
from cnd.converters.html import HtmlNodeRenderer
from cnd.core.cnd import Cnd, DocMetadata, Footnote
from cnd.core.nodes import (
    AdmonitionNode,
    FigureNode,
    ListNode,
    TableNode,
    TermItem,
    TermsNode,
)
from cnd.core.render import MarkdownRenderer
from cnd.core.text import FootnoteRef, LinkRef, Mark, Numbering, RichText
from cnd.core.urls import allowed_link_schemes, is_safe_url


def _cnd(nodes, footnotes=()) -> Cnd:
    return Cnd(
        cnd_version="0.5.0",
        built_at=datetime(2026, 11, 5, tzinfo=timezone.utc),
        doc=DocMetadata(title="T"),
        nodes=nodes,
        footnotes=list(footnotes),
    )


def _body(md: str) -> str:
    return md.split("---\n", 2)[-1].strip()


def _links(md: str, *rules: str) -> list[tuple[str, str]]:
    """``(text, href)`` of every link a CommonMark reader finds."""
    parser = MarkdownIt("commonmark")
    for rule in rules:
        parser.enable(rule)
    found: list[tuple[str, str]] = []
    for token in parser.parse(_body(md)):
        children = token.children or []
        for i, child in enumerate(children):
            if child.type == "link_open":
                words = []
                for later in children[i + 1:]:
                    if later.type == "link_close":
                        break
                    words.append(later.content)
                found.append(("".join(words), child.attrs["href"]))
    return found


def _convert(nodes, footnotes=(), **renderer) -> str:
    converter = (
        MarkdownConverter(MarkdownConverter.default_renderer(**renderer))
        if renderer
        else MarkdownConverter()
    )
    return converter.convert(_cnd(nodes, footnotes)).text


# -- the default conversion ----------------------------------------------------


class TestInlineByDefault:
    def test_a_spanned_link_is_written_where_its_words_are(self) -> None:
        text = rt("Read the overview next.",
                  links=[LinkRef(href="https://e.com/spec", text_span=[5, 17])])
        md = _convert([para(text)])
        assert _body(md) == "Read [the overview](https://e.com/spec) next."
        assert _links(md) == [("the overview", "https://e.com/spec")]

    def test_each_link_keeps_its_own_words(self) -> None:
        text = rt("one and two", links=[LinkRef(href="https://a.example/", text_span=[0, 3]),
                                        LinkRef(href="https://b.example/", text_span=[8, 11])])
        md = _convert([para(text)])
        assert _links(md) == [("one", "https://a.example/"), ("two", "https://b.example/")]
        assert "\n" not in _body(md)  # no marker line left

    def test_a_link_without_a_span_keeps_its_marker(self) -> None:
        text = rt("see below", links=[LinkRef(href="https://e.com/x")])
        assert _body(_convert([para(text)])) == "see below\n[https://e.com/x](https://e.com/x)"

    def test_brackets_in_the_linked_words_do_not_end_the_link(self) -> None:
        text = rt("a]b [c", links=[LinkRef(href="https://e.com/", text_span=[0, 6])])
        assert _links(_convert([para(text)])) == [("a]b [c", "https://e.com/")]

    def test_marks_inside_and_around_a_link(self) -> None:
        text = rt("very bold link", marks=[Mark(start=0, end=14, kind="strong")],
                  links=[LinkRef(href="https://e.com/", text_span=[10, 14])])
        md = _convert([para(text)])
        assert _links(md) == [("link", "https://e.com/")]
        assert "**" in _body(md)

    def test_an_unsafe_spanned_href_stays_plain_text(self) -> None:
        text = rt("click", links=[LinkRef(href="javascript:alert(1)", text_span=[0, 5])])
        md = _convert([para(text)])
        assert _body(md) == "click\njavascript:alert(1)"
        assert _links(md) == []

    def test_text_only_writes_markdown_links_too(self) -> None:
        text = rt("the site", links=[LinkRef(href="https://e.com/", text_span=[4, 8])])
        md = MarkdownConverter(text_only=True).convert(_cnd([para(text)])).text
        assert _body(md) == "the [site](https://e.com/)"

    def test_one_converter_reused_for_two_documents(self) -> None:
        converter = MarkdownConverter()
        link = LinkRef(href="https://e.com/", text_span=[0, 4])
        first = converter.convert(_cnd([para(rt("link one", links=[link]))])).text
        plain = converter.convert(_cnd([para(rt("link one", links=[LinkRef(href="https://e.com/")]))])).text
        assert _body(first) == "[link](https://e.com/) one"
        assert _body(plain) == "link one\n[https://e.com/](https://e.com/)"


# -- no link is lost ---------------------------------------------------------


class TestNoLinkIsLost:
    """A link the renderer does not write inline goes to the marker line."""

    def test_overlapping_links_outer_inline_inner_on_the_marker_line(self) -> None:
        links = [LinkRef(href="https://o.example/", text_span=[0, 10]),
                 LinkRef(href="https://i.example/", text_span=[3, 6])]
        md = _convert([para(rt("0123456789", links=links))])
        assert _body(md) == (
            "[0123456789](https://o.example/)\n[https://i.example/](https://i.example/)"
        )

    @pytest.mark.parametrize("kind", ["code", "math"])
    def test_a_link_inside_an_atom(self, kind) -> None:
        text = rt("abcdef", marks=[Mark(start=1, end=5, kind=kind)],
                  links=[LinkRef(href="https://e.com/", text_span=[2, 4])])
        assert _body(_convert([para(text)])).endswith("\n[https://e.com/](https://e.com/)")

    def test_a_list_item(self) -> None:
        link = LinkRef(href="https://e.com/", text_span=[0, 4])
        lst = ListNode(type="list", id=uuid4(), items=[item(para(rt("item one", links=[link])))])
        assert _body(_convert([lst])) == "- [item](https://e.com/) one"

    def test_a_gfm_table_cell(self) -> None:
        link = LinkRef(href="https://e.com/a|b", text_span=[0, 4])
        table = TableNode(type="table", id=uuid4(), kind="content", cells=[
            cell(0, 0, "h", is_header=True),
            cell(1, 0, None, children=[para(rt("cell", links=[link]))]),
        ])
        md = _convert([table])
        assert _links(md, "table") == [("cell", "https://e.com/a%7Cb")]

    def test_a_table_cell_holding_blocks_keeps_its_link_on_the_marker_line(self) -> None:
        link = LinkRef(href="https://e.com/", text_span=[0, 1])
        table = TableNode(type="table", id=uuid4(), kind="content", cells=[
            cell(0, 0, "h", is_header=True),
            cell(1, 0, None, children=[para(rt("c", links=[link])), para("more")]),
        ])
        md = _convert([table])
        assert "cnd-link" not in md
        assert _body(md).endswith("[https://e.com/](https://e.com/)")

    def test_a_figure_caption_link_is_written_once(self) -> None:
        caption = rt("from the site", links=[LinkRef(href="https://e.com/", text_span=[9, 13])])
        figure = FigureNode(type="figure", id=uuid4(), caption=caption,
                            children=[para("body")])
        md = _convert([figure])
        assert [href for _, href in _links(md)] == ["https://e.com/"]

    def test_a_placeholder_caption_link_goes_to_the_marker_line(self) -> None:
        caption = rt("the site", links=[LinkRef(href="https://e.com/", text_span=[4, 8])])
        figure = FigureNode(type="figure", id=uuid4(), caption=caption,
                            children=[para("body")])
        renderer = MarkdownRenderer(figures="placeholder", escape=True, links=True)
        md = MarkdownConverter(renderer).convert(_cnd([figure])).text
        assert _links(md) == [("https://e.com/", "https://e.com/")]

    def test_a_term_link_is_written_once(self) -> None:
        term = rt("the term", links=[LinkRef(href="https://e.com/", text_span=[4, 8])])
        terms = TermsNode(type="terms", id=uuid4(),
                          items=[TermItem(term=term, children=[para("def")])])
        md = _convert([terms])
        assert _links(md) == [("term", "https://e.com/")]

    def test_an_admonition_title_link_is_written_once(self) -> None:
        title = rt("Check the site", links=[LinkRef(href="https://e.com/", text_span=[10, 14])])
        node = AdmonitionNode(type="admonition", id=uuid4(), kind="warning", title=title,
                              children=[para("body")])
        md = _convert([node])
        assert _links(md) == [("site", "https://e.com/")]

    def test_a_footnote_link(self) -> None:
        note = Footnote(id=uuid4(), label="n1", children=[
            para(rt("in the overview", links=[LinkRef(href="https://e.com/", text_span=[7, 15])])),
        ])
        body = para(rt("Text.", footnotes=[FootnoteRef(label="n1")]))
        md = _convert([body], footnotes=[note])
        assert "[^n1]: in the [overview](https://e.com/)" in md


# -- the renderer's defaults ------------------------------------------------


class TestRendererDefaults:
    def test_links_are_off_by_default(self) -> None:
        text = rt("the site", links=[LinkRef(href="https://e.com/", text_span=[4, 8])])
        assert MarkdownRenderer().render(para(text)) == "the site"
        assert MarkdownRenderer(escape=True).render(para(text)) == "the site"

    def test_links_need_escape(self) -> None:
        with pytest.raises(ValueError, match="escape"):
            MarkdownRenderer(links=True)


# -- allowed schemes -----------------------------------------------------------


class TestAllowedSchemes:
    HREF = "x-notes://doc/1#overview"

    def test_an_allowed_scheme_is_written_inline(self) -> None:
        text = rt("Read the overview next.", links=[LinkRef(href=self.HREF, text_span=[5, 17])])
        md = _convert([para(text)], link_schemes={"x-notes"})
        assert _body(md) == f"Read [the overview]({self.HREF}) next."

    def test_an_allowed_scheme_without_a_span_is_a_marker_link(self) -> None:
        text = rt("see below", links=[LinkRef(href=self.HREF)])
        md = _convert([para(text)], link_schemes={"X-Notes"})
        assert _body(md) == f"see below\n[{self.HREF}]({self.HREF})"

    def test_the_scheme_is_matched_in_any_case(self) -> None:
        href = "X-NOTES://doc/1"
        text = rt("doc", links=[LinkRef(href=href, text_span=[0, 3])])
        assert _body(_convert([para(text)], link_schemes={"x-notes"})) == f"[doc]({href})"

    def test_a_scheme_not_allowed_stays_plain(self) -> None:
        text = rt("Read the overview next.", links=[LinkRef(href=self.HREF, text_span=[5, 17])])
        assert _body(_convert([para(text)])) == f"Read the overview next.\n{self.HREF}"

    @pytest.mark.parametrize("scheme", ["javascript", "JavaScript", "vbscript", "data"])
    def test_code_running_schemes_are_refused(self, scheme) -> None:
        with pytest.raises(ValueError, match="never"):
            allowed_link_schemes([scheme])
        with pytest.raises(ValueError):
            MarkdownRenderer(escape=True, links=True, link_schemes=[scheme])
        with pytest.raises(ValueError):
            HtmlNodeRenderer(link_schemes=[scheme])

    @pytest.mark.parametrize("scheme", ["", "x notes", "1abc", "x:", "x-notes:"])
    def test_a_malformed_scheme_is_refused(self, scheme) -> None:
        with pytest.raises(ValueError):
            allowed_link_schemes([scheme])

    def test_is_safe_url_extra_schemes(self) -> None:
        assert not is_safe_url(self.HREF)
        assert is_safe_url(self.HREF, frozenset({"x-notes"}))
        assert is_safe_url("  x-notes:y", frozenset({"x-notes"}))
        assert not is_safe_url("javascript:alert(1)", frozenset({"javascript"}))

    def test_html_links_an_allowed_scheme(self) -> None:
        inline = rt("the overview", links=[LinkRef(href=self.HREF, text_span=[4, 12])])
        bare = rt("below", links=[LinkRef(href=self.HREF)])
        html = HtmlConverter(HtmlNodeRenderer(link_schemes={"x-notes"})).convert(
            _cnd([para(inline), para(bare)])
        ).text
        assert f'the <a class="cnd-link" href="{self.HREF}">overview</a>' in html
        assert f'<a class="cnd-link" href="{self.HREF}">{self.HREF}</a>' in html

    def test_html_without_the_scheme_keeps_plain_text(self) -> None:
        inline = rt("the overview", links=[LinkRef(href=self.HREF, text_span=[4, 12])])
        html = HtmlConverter().convert(_cnd([para(inline)])).text
        assert "<p>the overview</p>" in html
        assert f'<span class="cnd-markers">{self.HREF}</span>' in html


# -- every link exactly once, wherever it sits ---------------------------------


def _link(place: str, words: str, value: str) -> LinkRef:
    """A link over ``words`` (their first occurrence in ``value``), with
    an href unique to ``place``."""
    start = value.index(words)
    return LinkRef(href=f"https://e.example/{place}", text_span=[start, start + len(words)])


def _linked(place: str, value: str, words: str, **kwargs) -> "RichText":
    return rt(value, links=[_link(place, words, value)], **kwargs)


def _every_placement():
    """A document with a link in every place a text can sit, plus the
    cases the renderer must leave to the marker line."""
    from cnd.core.nodes import HeadingNode, LayoutNode, QuoteNode

    heading = HeadingNode(
        type="heading", id=uuid4(), level=1, heading_path=["Heading"],
        text=_linked("heading", "Heading link", "link"),
        children=[para(_linked("under-heading", "under the heading", "heading"))],
    )
    nested = ListNode(type="list", id=uuid4(),
                      items=[item(para(_linked("nested-item", "nested item", "item")))])
    lst = ListNode(type="list", id=uuid4(), items=[
        item(para(_linked("item", "first item", "item")), nested),
    ])
    gfm = TableNode(type="table", id=uuid4(), kind="content", cells=[
        cell(0, 0, "h", is_header=True),
        cell(1, 0, None, children=[para(_linked("gfm-cell", "gfm cell", "cell"))]),
    ])
    blocks = TableNode(type="table", id=uuid4(), kind="content", cells=[
        cell(0, 0, "h", is_header=True),
        cell(1, 0, None, children=[para(_linked("block-cell", "block cell", "cell")), para("more")]),
    ])
    figure = FigureNode(
        type="figure", id=uuid4(),
        caption=_linked("caption", "the caption", "caption"),
        description=_linked("description", "the description", "description"),
        children=[para(_linked("figure-body", "figure body", "body"))],
    )
    numbered = FigureNode(
        type="figure", id=uuid4(), numbering=Numbering(name="Figure", value="2"),
        caption=_linked("numbered-caption", "a numbered caption", "caption"),
        children=[para("numbered body")],
    )
    terms = TermsNode(type="terms", id=uuid4(), items=[TermItem(
        term=_linked("term", "the term", "term"),
        children=[para(_linked("definition", "the definition", "definition"))],
    )])
    admonition = AdmonitionNode(
        type="admonition", id=uuid4(), kind="note",
        title=_linked("admonition-title", "a title", "title"),
        children=[para(_linked("admonition-body", "admonition body", "body"))],
    )
    quote = QuoteNode(
        type="quote", id=uuid4(),
        attribution=_linked("attribution", "an author", "author"),
        children=[para(_linked("quote-body", "quoted words", "words"))],
    )
    layout = LayoutNode(type="layout", id=uuid4(), cells=[
        cell(0, 0, None, children=[para(_linked("layout-cell", "layout cell", "cell"))]),
    ])
    # Strictly inside the atom: a link over the whole code span may wrap it.
    atom = para(rt("run cmd now", marks=[Mark(start=4, end=7, kind="code")],
                   links=[LinkRef(href="https://e.example/in-code", text_span=[5, 6])]))
    overlap = para(rt("0123456789", links=[
        LinkRef(href="https://e.example/outer", text_span=[0, 10]),
        LinkRef(href="https://e.example/inner", text_span=[3, 6]),
    ]))
    spanless = para(rt("no span", links=[LinkRef(href="https://e.example/spanless")]))
    refused = para(rt("refused words", links=[
        LinkRef(href="x-notes://e.example/refused", text_span=[0, 7]),
    ]))
    body = para(rt("Text.", footnotes=[FootnoteRef(label="n1")]))
    note = Footnote(id=uuid4(), label="n1",
                    children=[para(_linked("footnote", "in the note", "note"))])
    nodes = [heading, lst, gfm, blocks, figure, numbered, terms, admonition, quote, layout,
             atom, overlap, spanless, refused, body]
    return nodes, [note]


def _safe_hrefs(nodes, footnotes) -> list[str]:
    from cnd.core.nodes import iter_nodes, texts_of

    hrefs = []
    roots = list(nodes) + [child for note in footnotes for child in note.children]
    for visit in iter_nodes(roots):
        for text in texts_of(visit.node):
            hrefs.extend(link.href for link in text.links if is_safe_url(link.href))
    return hrefs


def _all_hrefs(md: str) -> list[str]:
    parser = MarkdownIt("commonmark").enable("table")
    found = []
    for token in parser.parse(md.split("---\n", 2)[-1]):
        for child in token.children or []:
            if child.type == "link_open":
                found.append(child.attrs["href"])
    return found


class TestEveryLinkExactlyOnce:
    """Inline or on the marker line, never both, never neither."""

    @pytest.mark.parametrize("make", [
        lambda: MarkdownConverter(),
        lambda: MarkdownConverter(text_only=True),
        lambda: MarkdownConverter(MarkdownRenderer(
            tables="placeholder", figures="placeholder", escape=True, links=True)),
        lambda: MarkdownConverter(MarkdownRenderer(
            tables="inline", figures="inline", escape=True)),
    ], ids=["default", "text_only", "placeholders", "links_off"])
    def test_each_safe_link_once_and_the_refused_one_as_text(self, make) -> None:
        nodes, footnotes = _every_placement()
        expected = _safe_hrefs(nodes, footnotes)
        assert len(expected) == len(set(expected)) == 22
        md = make().convert(_cnd(nodes, footnotes)).text
        found = _all_hrefs(md)
        assert sorted(found) == sorted(expected)
        assert md.count("x-notes://e.example/refused") == 1

    def test_where_the_default_conversion_writes_them(self) -> None:
        nodes, footnotes = _every_placement()
        md = MarkdownConverter().convert(_cnd(nodes, footnotes)).text
        inline = {
            "heading": "link", "under-heading": "heading", "item": "item",
            "nested-item": "item", "gfm-cell": "cell", "caption": "caption",
            "description": "description",
            "figure-body": "body", "term": "term", "definition": "definition",
            "admonition-title": "title", "admonition-body": "body",
            "attribution": "author", "quote-body": "words", "layout-cell": "cell",
            "footnote": "note", "outer": "0123456789",
        }
        assert "run `cmd` now\n" in md
        for place, words in inline.items():
            assert f"[{words}](https://e.example/{place})" in md, place
        # Written on a marker line, where the renderer could not place them.
        for place in ("block-cell", "numbered-caption", "in-code", "inner", "spanless"):
            href = f"https://e.example/{place}"
            assert f"[{href}]({href})" in md, place


def test_a_link_over_a_whole_code_span_wraps_it() -> None:
    text = rt("run cmd now", marks=[Mark(start=4, end=7, kind="code")],
              links=[LinkRef(href="https://e.com/", text_span=[4, 7])])
    md = _convert([para(text)])
    assert _body(md) == "run [`cmd`](https://e.com/) now"


# -- review findings -------------------------------------------------------------


class TestABangBeforeALink:
    """``![`` would make the link an image: its href an image source."""

    def test_a_bang_in_the_text(self) -> None:
        text = rt("Wow!here", links=[LinkRef(href="https://e.com/", text_span=[4, 8])])
        md = _convert([para(text)])
        assert _body(md) == "Wow\\![here](https://e.com/)"
        assert _links(md) == [("here", "https://e.com/")]

    def test_a_bang_left_by_a_dropped_mark(self) -> None:
        text = rt("wow!here", marks=[Mark(start=0, end=4, kind="underline")],
                  links=[LinkRef(href="https://e.com/", text_span=[4, 8])])
        md = MarkdownConverter(text_only=True).convert(_cnd([para(text)])).text
        assert _links(md) == [("here", "https://e.com/")]
        assert "image" not in [t.type for t in MarkdownIt("commonmark").parse(_body(md))[1].children]

    def test_a_literal_backslash_before_the_bang(self) -> None:
        text = rt("a\\!here", links=[LinkRef(href="https://e.com/", text_span=[3, 7])])
        md = _convert([para(text)])
        assert _links(md) == [("here", "https://e.com/")]

    def test_a_bang_already_escaped_stays_as_it_is(self) -> None:
        # "!" then a mark that opens with the link: still one escape.
        text = rt("go!now", marks=[Mark(start=3, end=6, kind="strong")],
                  links=[LinkRef(href="https://e.com/", text_span=[3, 6])])
        md = _convert([para(text)])
        assert _links(md) == [("now", "https://e.com/")]


class TestWordsAMarkdownLinkCannotHold:
    def test_a_blank_line_in_the_words_goes_to_the_marker_line(self) -> None:
        text = rt("a\n\nb", links=[LinkRef(href="https://e.com/", text_span=[0, 4])])
        md = _convert([para(text)])
        assert _links(md) == [("https://e.com/", "https://e.com/")]

    def test_a_line_break_in_a_heading_goes_to_the_marker_line(self) -> None:
        from cnd.core.nodes import HeadingNode

        heading = HeadingNode(type="heading", id=uuid4(), level=2, heading_path=["a b"],
                              text=rt("a\nb", links=[LinkRef(href="https://e.com/h", text_span=[0, 3])]))
        md = _convert([heading])
        assert [href for _, href in _links(md)] == ["https://e.com/h"]

    def test_a_single_line_break_in_a_paragraph_stays_a_link(self) -> None:
        text = rt("a\nb", links=[LinkRef(href="https://e.com/", text_span=[0, 3])])
        assert [href for _, href in _links(_convert([para(text)]))] == ["https://e.com/"]

    def test_two_cells_at_one_position_lose_no_link(self) -> None:
        hidden = LinkRef(href="https://e.com/hidden", text_span=[0, 6])
        kept = LinkRef(href="https://e.com/kept", text_span=[0, 4])
        table = TableNode(type="table", id=uuid4(), kind="content", cells=[
            cell(0, 0, "h", is_header=True),
            cell(1, 0, None, children=[para(rt("hidden", links=[hidden]))]),
            cell(1, 0, None, children=[para(rt("kept", links=[kept]))]),
        ])
        md = _convert([table])
        assert sorted(href for _, href in _links(md, "table")) == [
            "https://e.com/hidden", "https://e.com/kept",
        ]


class TestSchemeArguments:
    def test_the_converter_refuses_one_string(self) -> None:
        with pytest.raises(TypeError):
            MarkdownConverter(link_schemes="git")

    def test_is_safe_url_refuses_one_string(self) -> None:
        with pytest.raises(TypeError):
            is_safe_url("file:///etc/passwd", "profile")

    def test_a_subclass_with_the_old_default_renderer_signature(self) -> None:
        class Old(MarkdownConverter):
            @classmethod
            def default_renderer(cls, *, text_only: bool = False):
                return MarkdownRenderer(tables="inline", figures="inline", escape=True)

        md = Old().convert(_cnd([para("x")])).text
        assert _body(md) == "x"


class TestRenderersShareNothing:
    def test_one_converter_in_several_threads(self) -> None:
        from concurrent.futures import ThreadPoolExecutor

        converter = MarkdownConverter()

        def convert(n: int) -> str:
            text = rt(f"link {n}", links=[LinkRef(href=f"https://e.com/{n}", text_span=[0, 4])])
            return _body(converter.convert(_cnd([para(text)] * 20)).text)

        with ThreadPoolExecutor(max_workers=8) as pool:
            results = list(pool.map(convert, range(64)))
        for n, body in enumerate(results):
            assert body == "\n\n".join([f"[link](https://e.com/{n}) {n}"] * 20)

    def test_an_html_renderer_in_the_markdown_converter(self) -> None:
        text = rt("the site", links=[LinkRef(href="https://e.com/", text_span=[4, 8])])
        md = MarkdownConverter(HtmlNodeRenderer()).convert(_cnd([para(text)])).text
        assert md.count("https://e.com/") == 1

    def test_a_markdown_renderer_in_the_html_converter(self) -> None:
        text = rt("the site", links=[LinkRef(href="https://e.com/", text_span=[4, 8])])
        renderer = MarkdownRenderer(escape=True, links=True)
        html = HtmlConverter(renderer).convert(_cnd([para(text)])).text
        assert html.count("https://e.com/") == 1


def test_a_nested_conversion_does_not_note_into_the_outer_record() -> None:
    """A renderer that converts another document inside its own block: the
    inner bibliography, rendered outside the inner blocks, must not note
    its links into the outer block's record."""
    from cnd.core.cnd import BibEntry

    shared = LinkRef(href="https://e.com/shared", text_span=[7, 8])
    inner = _cnd([para("inner")])
    inner.bibliography = [BibEntry(id=uuid4(), label="b", formatted=rt("0123456789", links=[shared]))]

    class Nesting(MarkdownRenderer):
        def render_paragraph(self, node):
            if node.text.value.startswith("abc"):
                MarkdownConverter().convert(inner)
                HtmlConverter().convert(inner)
            return super().render_paragraph(node)

    outer = _cnd([para(rt("abcdefghij", marks=[Mark(start=6, end=9, kind="code")], links=[shared]))])
    md = MarkdownConverter(Nesting(escape=True, links=True)).convert(outer).text
    # The outer link sits inside a code span: it must reach the marker line.
    assert _body(md).endswith("[https://e.com/shared](https://e.com/shared)")
