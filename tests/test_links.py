"""Hyperlinks: the shared URL check, ``links`` edges in the HTML converter
and the Markdown link marker."""

from datetime import datetime, timezone
from html.parser import HTMLParser

import pytest
from markdown_it import MarkdownIt

from factories import para, rt

from cnd.converters import HtmlConverter, MarkdownConverter
from cnd.converters.html import HtmlNodeRenderer
from cnd.core.cnd import Cnd, DocMetadata
from cnd.core.nodes import TableNode
from cnd.core.render import MarkdownRenderer
from cnd.core.text import LinkRef, Mark
from cnd.core.urls import is_safe_url

from factories import cell


def _cnd(nodes) -> Cnd:
    return Cnd(
        cnd_version="0.5.0",
        built_at=datetime(2026, 10, 13, tzinfo=timezone.utc),
        doc=DocMetadata(title="T"),
        nodes=nodes,
    )


class _Anchors(HTMLParser):
    """Every ``<a>`` element: its attributes and its text."""

    def __init__(self) -> None:
        super().__init__()
        self.anchors: list[tuple[dict, str]] = []
        self._open: list[tuple[dict, list[str]]] = []

    def handle_starttag(self, tag, attrs) -> None:
        if tag == "a":
            self._open.append((dict(attrs), []))

    def handle_endtag(self, tag) -> None:
        if tag == "a" and self._open:
            attrs, text = self._open.pop()
            self.anchors.append((attrs, "".join(text)))

    def handle_data(self, data) -> None:
        for _, text in self._open:
            text.append(data)


def _anchors(html: str) -> list[tuple[dict, str]]:
    parser = _Anchors()
    parser.feed(html)
    return parser.anchors


# -- the URL check ---------------------------------------------------------


class TestIsSafeUrl:
    @pytest.mark.parametrize("url", [
        "http://example.com",
        "https://example.com/a?b#c",
        "HTTPS://EXAMPLE.COM",
        "mailto:someone@example.com",
        "MailTo:someone@example.com",
        "  https://example.com",
        "page.html",
        "../up/page.html",
        "/abs/path",
        "#section",
        "?q=1",
        "dir/name:with-colon",
        "",
    ])
    def test_safe(self, url: str) -> None:
        assert is_safe_url(url)

    @pytest.mark.parametrize("url", [
        "javascript:alert(1)",
        "JavaScript:alert(1)",
        " javascript:alert(1)",
        "\x01\x02javascript:alert(1)",
        "\njavascript:alert(1)",
        "java\tscript:alert(1)",
        "java\nscript:alert(1)",
        "jav\rascript:alert(1)",
        "vbscript:msgbox(1)",
        "data:text/html,<script>alert(1)</script>",
        "data:image/png;base64,AAAA",
        "file:///etc/passwd",
        "ftp://example.com",
        "\u00a0javascript:alert(1)",
        "\u2003javascript:alert(1)",
        "\u2028javascript:alert(1)",
        "\u3000javascript:alert(1)",
        "\u0085javascript:alert(1)",
        "\ufeffjavascript:alert(1)",
        "\x1c\u00a0 javascript:alert(1)",
    ])
    def test_unsafe(self, url: str) -> None:
        assert not is_safe_url(url)


# -- HTML: a link with a span wraps its text --------------------------------


class TestHtmlInlineLinks:
    def test_linked_text_becomes_an_anchor(self) -> None:
        text = rt("see the spec here", links=[LinkRef(href="https://example.com/s", text_span=[8, 12])])
        out = HtmlNodeRenderer().render(para(text))
        assert out == '<p>see the <a class="cnd-link" href="https://example.com/s">spec</a> here</p>'

    def test_href_is_escaped_as_an_attribute(self) -> None:
        text = rt("x", links=[LinkRef(href='https://e.com/?a=1&b="2"', text_span=[0, 1])])
        anchors = _anchors(HtmlNodeRenderer().render(para(text)))
        assert anchors == [({"class": "cnd-link", "href": 'https://e.com/?a=1&b="2"'}, "x")]

    def test_crossing_mark_and_link_nest(self) -> None:
        text = rt(
            "abcdef",
            marks=[Mark(start=0, end=4, kind="strong")],
            links=[LinkRef(href="https://e.com", text_span=[2, 6])],
        )
        out = HtmlNodeRenderer().render_text(text)
        assert out == (
            '<strong>ab<a class="cnd-link" href="https://e.com">cd</a></strong>'
            '<a class="cnd-link" href="https://e.com">ef</a>'
        )

    def test_unsafe_link_leaves_the_text_plain(self) -> None:
        text = rt("click me", links=[LinkRef(href="javascript:alert(1)", text_span=[0, 5])])
        out = HtmlNodeRenderer().render(para(text))
        assert out == "<p>click me</p>"
        assert "javascript" not in out

    def test_other_families_are_not_wrapped(self) -> None:
        from cnd.core.text import NodeRef

        text = rt("see t", refs=[NodeRef(label="t", text_span=[4, 5])])
        assert HtmlNodeRenderer().render_text(text) == "see t"

    def test_links_switch_off_leaves_text_plain(self) -> None:
        text = rt("site", links=[LinkRef(href="https://e.com", text_span=[0, 4])])
        assert HtmlNodeRenderer(links=False).render_text(text) == "site"


# -- HTML converter: marker line --------------------------------------------


class TestHtmlConverterLinks:
    def test_spanned_link_is_inline_not_in_the_marker_line(self) -> None:
        node = para(rt("site", links=[LinkRef(href="https://e.com", text_span=[0, 4])]))
        html = HtmlConverter().convert(_cnd([node])).text
        assert '<p><a class="cnd-link" href="https://e.com">site</a></p>' in html
        assert '<span class="cnd-markers">' not in html

    def test_spanless_link_goes_to_the_marker_line(self) -> None:
        node = para(rt("site", links=[LinkRef(href="https://e.com/x")]))
        html = HtmlConverter().convert(_cnd([node])).text
        assert (
            '<span class="cnd-markers"><a class="cnd-link" href="https://e.com/x">'
            "https://e.com/x</a></span>"
        ) in html

    def test_unsafe_spanless_link_is_plain_text(self) -> None:
        node = para(rt("site", links=[LinkRef(href="javascript:alert('<x>')")]))
        html = HtmlConverter().convert(_cnd([node])).text
        assert '<span class="cnd-markers">javascript:alert(&#x27;&lt;x&gt;&#x27;)</span>' in html
        assert not [a for a in _anchors(html) if "javascript" in a[0].get("href", "")]


# -- Markdown: the link marker ------------------------------------------------


def _md_links(text: str) -> list[str]:
    tokens = MarkdownIt("commonmark").parse(text)
    hrefs = []
    for token in tokens:
        for child in token.children or []:
            if child.type == "link_open":
                hrefs.append(child.attrs["href"])
    return hrefs


class TestMarkdownLinkMarker:
    def test_safe_link_marker_is_a_link(self) -> None:
        node = para(rt("site", links=[LinkRef(href="https://e.com/x", text_span=[0, 4])]))
        md = MarkdownConverter().convert(_cnd([node])).text
        assert "[https://e.com/x](https://e.com/x)" in md
        assert _md_links(md) == ["https://e.com/x"]

    def test_unsafe_link_marker_is_plain_text(self) -> None:
        node = para(rt("site", links=[LinkRef(href="javascript:alert(1)")]))
        md = MarkdownConverter().convert(_cnd([node])).text
        assert "javascript:alert(1)" in md
        assert _md_links(md) == []

    def test_unsafe_link_marker_cannot_open_inline_html(self) -> None:
        node = para(rt("site", links=[LinkRef(href="data:text/html,<script>alert(1)</script>")]))
        md = MarkdownConverter().convert(_cnd([node])).text
        html = MarkdownIt("commonmark").render(md)
        assert "<script>" not in html

    @pytest.mark.parametrize("href", [
        "javascript&colon;alert(1)",
        "javascript\\:alert(1)",
        "a&amp;b",
        "path\\with\\backslash",
    ])
    def test_destination_parses_back_to_the_checked_href(self, href: str) -> None:
        assert is_safe_url(href)
        node = para(rt("site", links=[LinkRef(href=href)]))
        md = MarkdownConverter().convert(_cnd([node])).text
        parsed = _md_links(md)
        assert len(parsed) == 1
        # markdown-it percent-encodes; decode before comparing.
        from urllib.parse import unquote

        assert unquote(parsed[0]) == href

    def test_html_table_in_markdown_does_not_wrap_links(self) -> None:
        link = LinkRef(href="https://e.com", text_span=[0, 1])
        table = TableNode(type="table", id=para().id, kind="content", cells=[
            cell(0, 0, "h", is_header=True),
            cell(1, 0, None, children=[para(rt("c", links=[link])), para("more")]),
        ])
        out = MarkdownRenderer(tables="inline").render(table)
        assert "cnd-link" not in out


class _Nesting(HTMLParser):
    """The deepest ``<a>`` nesting seen."""

    def __init__(self) -> None:
        super().__init__()
        self.depth = self.deepest = 0

    def handle_starttag(self, tag, attrs) -> None:
        if tag == "a":
            self.depth += 1
            self.deepest = max(self.deepest, self.depth)

    def handle_endtag(self, tag) -> None:
        if tag == "a":
            self.depth -= 1


def _deepest_anchor(html: str) -> int:
    parser = _Nesting()
    parser.feed(html)
    return parser.deepest


class TestNestedLinks:
    @pytest.mark.parametrize(("outer", "inner"), [
        ([0, 10], [3, 6]),   # inside
        ([0, 6], [3, 10]),   # crossing
        ([3, 10], [0, 6]),   # crossing, listed second but starts first
        ([0, 10], [0, 10]),  # equal
        ([0, 10], [0, 4]),   # inside, same start
    ])
    def test_never_nested_anchors(self, outer, inner) -> None:
        links = [LinkRef(href="https://o.example", text_span=outer),
                 LinkRef(href="https://i.example", text_span=inner)]
        text = rt("0123456789", marks=[Mark(start=2, end=8, kind="strong")], links=links)
        html = HtmlConverter().convert(_cnd([para(text)])).text
        assert _deepest_anchor(html) == 1
        hrefs = [a[0]["href"] for a in _anchors(html)]
        # Both links survive: one inline, the other in the marker line.
        assert "https://o.example" in hrefs and "https://i.example" in hrefs

    def test_the_dropped_inner_link_goes_to_the_marker_line(self) -> None:
        links = [LinkRef(href="https://o.example", text_span=[0, 10]),
                 LinkRef(href="https://i.example", text_span=[3, 6])]
        html = HtmlConverter().convert(_cnd([para(rt("0123456789", links=links))])).text
        assert '<p><a class="cnd-link" href="https://o.example">0123456789</a></p>' in html
        assert (
            '<span class="cnd-markers"><a class="cnd-link" href="https://i.example">'
            "https://i.example</a></span>"
        ) in html


class TestNoLinkIsLost:
    """A spanned link that does not render inline goes to the marker line."""

    @staticmethod
    def _markers(text) -> str:
        html = HtmlConverter().convert(_cnd([para(text)])).text
        start = html.find('<span class="cnd-markers">')
        return html[start:html.find("</span>", start) + 7] if start >= 0 else ""

    @pytest.mark.parametrize("span", [[2, 2], [9, 12], [3, 1], [1]])
    def test_empty_clamped_or_malformed_span(self, span) -> None:
        text = rt("abcd", links=[LinkRef(href="https://e.com", text_span=span)])
        assert 'href="https://e.com">https://e.com</a>' in self._markers(text)

    @pytest.mark.parametrize("kind", ["code", "math"])
    def test_span_inside_an_atom(self, kind) -> None:
        text = rt("abcdef", marks=[Mark(start=1, end=5, kind=kind)],
                  links=[LinkRef(href="https://e.com", text_span=[2, 4])])
        assert 'href="https://e.com">https://e.com</a>' in self._markers(text)

    def test_unsafe_spanned_href_is_plain_text_in_the_marker_line(self) -> None:
        text = rt("click", links=[LinkRef(href="javascript:alert(1)", text_span=[0, 5])])
        markers = self._markers(text)
        assert markers == '<span class="cnd-markers">javascript:alert(1)</span>'

    def test_a_wrapped_link_is_not_repeated(self) -> None:
        text = rt("abcd", links=[LinkRef(href="https://e.com", text_span=[0, 4])])
        assert self._markers(text) == ""

    def test_nested_texts_of_a_container(self) -> None:
        from cnd.core.nodes import ListNode
        from factories import item

        inner = rt("0123456789", links=[LinkRef(href="https://o.example", text_span=[0, 10]),
                                        LinkRef(href="https://i.example", text_span=[3, 6])])
        lst = ListNode(type="list", id=para().id, items=[item(para(inner))])
        html = HtmlConverter().convert(_cnd([lst])).text
        assert _deepest_anchor(html) == 1
        assert {a[0]["href"] for a in _anchors(html)} == {"https://o.example", "https://i.example"}

    def test_an_injected_renderer_without_inline_links_gets_every_link(self) -> None:
        from cnd.core.render import MarkdownRenderer

        text = rt("abcd", links=[LinkRef(href="https://e.com", text_span=[0, 4])])
        html = HtmlConverter(MarkdownRenderer()).convert(_cnd([para(text)])).text
        assert 'href="https://e.com">https://e.com</a>' in html

    def test_links_false_renderer_gets_every_link_in_the_marker_line(self) -> None:
        text = rt("abcd", links=[LinkRef(href="https://e.com", text_span=[0, 4])])
        html = HtmlConverter(HtmlNodeRenderer(links=False)).convert(_cnd([para(text)])).text
        assert '<p>abcd</p>' in html
        assert 'href="https://e.com">https://e.com</a>' in html


class TestLinkMarkerStaysOnItsLine:
    """No line ending in an href may leave the Markdown link marker."""

    PAYLOADS = [
        "a\n\n[x](ms-msdt:e)",
        "a\n# [x](intent:e)",
        "a\r\r[x](javascript:alert(1))",
        "a\n> [x](x:y)",
        "a\n\n![t](https://t/p.gif)",
        "a\r\n- [x](x:y)",
    ]

    @staticmethod
    def _tokens(md: str) -> list:
        body = md.split("---\n", 2)[-1]  # past the front matter
        tokens = MarkdownIt("commonmark").parse(body)
        flat = list(tokens)
        for token in tokens:
            flat.extend(token.children or [])
        return flat

    @pytest.mark.parametrize("href", PAYLOADS)
    @pytest.mark.parametrize("span", [None, [0, 4]])
    def test_one_link_and_no_new_structure(self, href: str, span) -> None:
        node = para(rt("link here", links=[LinkRef(href=href, text_span=span)]))
        md = MarkdownConverter().convert(_cnd([node])).text
        types = [t.type for t in self._tokens(md)]
        assert types.count("link_open") == (1 if is_safe_url(href) else 0)
        assert "image" not in types
        assert "heading_open" not in types
        assert "blockquote_open" not in types and "bullet_list_open" not in types

    @pytest.mark.parametrize("href", [
        "javascript:a\n\n![t](https://t/p.gif)",
        "javascript:a\n# h",
        "javascript:a\r> q",
    ])
    def test_unsafe_plain_text_stays_on_its_line(self, href: str) -> None:
        node = para(rt("link here", links=[LinkRef(href=href)]))
        md = MarkdownConverter().convert(_cnd([node])).text
        types = [t.type for t in self._tokens(md)]
        assert "link_open" not in types and "image" not in types
        assert "heading_open" not in types and "blockquote_open" not in types


def test_one_link_object_in_two_texts_is_judged_per_text() -> None:
    """A producer may share one LinkRef between texts: inline in one,
    inside a code atom in the other, which must still reach the marker
    line."""
    from cnd.core.nodes import ListNode
    from factories import item

    link = LinkRef(href="https://shared.example/", text_span=[0, 4])
    first = rt("link one", links=[link])
    second = rt("code two", marks=[Mark(start=0, end=8, kind="code")], links=[link])
    lst = ListNode(type="list", id=para().id, items=[item(para(first)), item(para(second))])
    assert lst.items[0].children[0].text.links[0] is lst.items[1].children[0].text.links[0]
    html = HtmlConverter().convert(_cnd([lst])).text
    assert '<a class="cnd-link" href="https://shared.example/">link</a> one' in html
    assert (
        '<span class="cnd-markers"><a class="cnd-link" href="https://shared.example/">'
        "https://shared.example/</a></span>"
    ) in html
