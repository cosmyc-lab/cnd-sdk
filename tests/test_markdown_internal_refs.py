"""Markdown output keeps internal references navigable (docs/adr/0032): a
``refs`` edge becomes a link to an anchor written on the node it names."""

import re
from datetime import datetime, timezone
from uuid import uuid4

import pytest
from markdown_it import MarkdownIt

from factories import cell, item, para, rt

from cnd.converters import MarkdownConverter
from cnd.core.cnd import Cnd, DocMetadata, Footnote
from cnd.core.nodes import (
    FigureNode,
    HeadingNode,
    ImageNode,
    LayoutNode,
    ListNode,
    QuoteNode,
    TableNode,
)
from cnd.core.render import MarkdownRenderer, markdown_anchor
from cnd.core.text import CiteRef, FootnoteRef, LinkRef, NodeRef, Numbering


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


def _links(md: str) -> list[tuple[str, str]]:
    """``(text, href)`` of every link a CommonMark reader finds."""
    found: list[tuple[str, str]] = []
    for token in MarkdownIt("commonmark").parse(_body(md)):
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


def _anchor_ids(md: str) -> list[str]:
    return re.findall(r'<a id="([^"]*)"></a>', md)


def _assert_every_link_lands(md: str) -> None:
    """Every in-file link names exactly one anchor."""
    ids = _anchor_ids(md)
    for _, href in _links(md):
        if href.startswith("#"):
            assert ids.count(href[1:]) == 1, href


def _heading(label: str, text: str, *children, level: int = 2, value: str | None = None):
    return HeadingNode(
        type="heading", id=uuid4(), level=level, label=label, text=rt(text),
        heading_path=[text], children=list(children),
        numbering=Numbering(value=value) if value else None,
    )


def _figure(label: str) -> FigureNode:
    image = ImageNode(type="image", id=uuid4(), path="arch.png", alt="Architecture")
    return FigureNode(type="figure", id=uuid4(), label=label, caption=rt("The parts"),
                      children=[image])


def _ref(value: str, label: str, span: list[int] | None = None):
    return para(rt(value, refs=[NodeRef(label=label, text_span=span)]))


def _document() -> Cnd:
    """A heading and a figure referenced from the text, one reference
    without a span, one to a label that does not exist, and an
    unreferenced labelled paragraph."""
    return _cnd([
        _heading("intro", "Intro", para("Plain words.", label="plain")),
        _heading(
            "method", "Method",
            _ref("see Section 2", "method", [4, 13]),
            _ref("as drawn", "fig:arch"),
            _ref("lost", "ghost"),
            _figure("fig:arch"),
            value="2",
        ),
    ])


def _convert(cnd: Cnd, **options) -> str:
    return MarkdownConverter(**options).convert(cnd).text


# -- the option on -------------------------------------------------------------


def test_ref_with_span_links_to_the_heading_anchor() -> None:
    md = _convert(_document(), ref_links=True)
    body = _body(md)
    assert "see [Section 2](#method)" in body
    assert '## <a id="method"></a>2 Method' in body.splitlines()
    assert ("Section 2", "#method") in _links(md)
    _assert_every_link_lands(md)


def test_ref_without_span_links_on_the_marker_line() -> None:
    md = _convert(_document(), ref_links=True)
    assert "as drawn\n[fig:arch](#fig:arch)" in _body(md)
    assert ("fig:arch", "#fig:arch") in _links(md)


def test_unresolved_ref_keeps_todays_marker() -> None:
    result = MarkdownConverter(ref_links=True).convert(_document())
    assert "lost\n[ghost]" in _body(result.text)
    assert "ghost" not in _anchor_ids(result.text)
    assert not any(href == "#ghost" for _, href in _links(result.text))
    assert any("'ghost'" in warning for warning in result.warnings)


def test_anchor_on_non_heading_target() -> None:
    md = _convert(_document(), ref_links=True)
    assert _anchor_ids(md).count("fig:arch") == 1
    # On a line of its own: a table, a list or a fence must start its line.
    assert '<a id="fig:arch"></a>\n\n![Architecture](arch.png)' in _body(md)
    assert ("fig:arch", "#fig:arch") in _links(md)


def test_label_needing_escape_matches_in_anchor_and_link() -> None:
    label = "résumé final/2%"
    anchor = markdown_anchor(label)
    assert anchor == "r%C3%A9sum%C3%A9%20final%2F2%25"
    cnd = _cnd([
        _heading(label, "Summary"),
        _ref("read the summary", label, [9, 16]),
        _ref("again", label),
    ])
    md = _convert(cnd, ref_links=True)
    body = _body(md)
    assert f'## <a id="{anchor}"></a>Summary' in body
    assert f"read the [summary](#{anchor})" in body
    assert f"[résumé final/2%](#{anchor})" in body
    assert _anchor_ids(md) == [anchor]
    assert [href for _, href in _links(md)] == [f"#{anchor}", f"#{anchor}"]


def test_markdown_anchor_keeps_fragment_characters_as_they_are() -> None:
    assert markdown_anchor("Fig.3_a:b-c") == "Fig.3_a:b-c"
    assert markdown_anchor("a b") == "a%20b"
    assert markdown_anchor('x"<y>#') == "x%22%3Cy%3E%23"


def test_unreferenced_labels_get_no_anchor() -> None:
    md = _convert(_document(), ref_links=True)
    ids = _anchor_ids(md)
    assert "intro" not in ids
    assert "plain" not in ids
    assert sorted(ids) == ["fig:arch", "method"]


def test_a_nested_target_is_anchored_at_the_block_that_renders_it() -> None:
    target = para("the nested point", label="point")
    lst = ListNode(type="list", id=uuid4(), items=[item(target)])
    md = _convert(_cnd([_ref("see the point", "point", [8, 13]), lst]), ref_links=True)
    assert "see the [point](#point)" in _body(md)
    assert _anchor_ids(md) == ["point"]
    assert '<a id="point"></a>\n\n- the nested point' in _body(md)
    _assert_every_link_lands(md)


def test_a_target_under_a_heading_nested_in_a_container_is_anchored() -> None:
    """A container renders a nested heading's whole section itself, so a
    target in that section is anchored at the container's block."""
    deep = para("the deep point", label="deep")
    quote = QuoteNode(type="quote", id=uuid4(),
                      children=[_heading("inner", "Inner", deep, level=3)])
    md = _convert(_cnd([_ref("see deep", "deep", [4, 8]), quote]), ref_links=True)
    assert "see [deep](#deep)" in _body(md)
    assert _anchor_ids(md) == ["deep"]
    _assert_every_link_lands(md)


def test_a_quote_target_and_a_layout_target_are_anchored() -> None:
    quote = QuoteNode(type="quote", id=uuid4(), label="q", children=[para("quoted")])
    layout = LayoutNode(type="layout", id=uuid4(),
                        cells=[cell(0, 0, None, children=[para("in a cell", label="c")])])
    md = _convert(_cnd([quote, layout, _ref("see q and c", "q", [4, 5]),
                        _ref("and c", "c", [4, 5])]), ref_links=True)
    assert '<a id="q"></a>\n\n> quoted' in _body(md)
    assert sorted(_anchor_ids(md)) == ["c", "q"]
    _assert_every_link_lands(md)


def test_a_ref_in_heading_text_links_on_the_heading_line() -> None:
    heading = HeadingNode(type="heading", id=uuid4(), level=2, heading_path=["See Method"],
                          text=rt("See Method", refs=[NodeRef(label="method", text_span=[4, 10])]))
    md = _convert(_cnd([heading, _heading("method", "Method")]), ref_links=True)
    assert "## See [Method](#method)" in _body(md).splitlines()
    _assert_every_link_lands(md)


def test_a_target_inside_a_footnote_is_anchored_there() -> None:
    note = Footnote(id=uuid4(), label="fn", children=[para("note text", label="in-note")])
    nodes = [
        para(rt("body", footnotes=[FootnoteRef(label="fn")])),
        _ref("see the note", "in-note", [8, 12]),
    ]
    md = _convert(_cnd(nodes, [note]), ref_links=True)
    assert '[^fn]: <a id="in-note"></a>note text' in md
    assert ("note", "#in-note") in _links(md)


def test_a_paragraph_target_takes_its_anchor_inline() -> None:
    md = _convert(_cnd([para("Claim.", label="claim"), _ref("by claim", "claim", [3, 8])]),
                  ref_links=True)
    assert _body(md).startswith('<a id="claim"></a>Claim.')


def test_footnotes_citations_and_links_are_unchanged() -> None:
    text = rt(
        "words and more",
        cites=[CiteRef(label="knuth")],
        footnotes=[FootnoteRef(label="fn")],
        links=[LinkRef(href="https://e.com/", text_span=[0, 5])],
    )
    cnd = _cnd([para(text)], [Footnote(id=uuid4(), label="fn", children=[para("n")])])
    assert _convert(cnd, ref_links=True) == _convert(cnd)


def test_a_ref_and_a_link_over_the_same_words_write_one_link() -> None:
    """Links never nest: on an equal span the edge listed first (refs come
    before links) wins, and the other goes to the marker line."""
    text = rt("see Method", refs=[NodeRef(label="method", text_span=[4, 10])],
              links=[LinkRef(href="https://e.com/", text_span=[4, 10])])
    md = _convert(_cnd([_heading("method", "Method"), para(text)]), ref_links=True)
    body = _body(md)
    assert "see [Method](#method)\n[https://e.com/](https://e.com/)" in body
    _assert_every_link_lands(md)


def test_a_ref_inside_code_goes_to_the_marker_line() -> None:
    from cnd.core.text import Mark

    text = rt("call run()", marks=[Mark(kind="code", start=5, end=10)],
              refs=[NodeRef(label="method", text_span=[5, 8])])
    md = _convert(_cnd([_heading("method", "Method"), para(text)]), ref_links=True)
    assert "call `run()`\n[method](#method)" in _body(md)


def test_each_ref_written_exactly_once() -> None:
    md = _convert(_document(), ref_links=True)
    assert [href for _, href in _links(md)].count("#method") == 1
    assert [href for _, href in _links(md)].count("#fig:arch") == 1


# -- off by default ------------------------------------------------------------


def test_off_by_default_output_unchanged() -> None:
    """What 0.10.0 wrote for the same document, byte for byte."""
    assert _convert(_document()) == (
        '---\ntitle: "T"\ncnd_version: "0.5.0"\n'
        'built_at: "2026-11-05T00:00:00+00:00"\n---\n\n'
        "## Intro\n\nPlain words.\n\n## 2 Method\n\n"
        "see Section 2\n[method]\n\nas drawn\n[fig:arch]\n\nlost\n[ghost]\n\n"
        "![Architecture](arch.png)\n\n*The parts*\n"
    )


# -- explicit renderers and guards ---------------------------------------------


class _Subclass(MarkdownRenderer):
    pass


def test_explicit_renderer_with_ref_links_gets_targets_and_anchors() -> None:
    renderer = _Subclass(tables="inline", figures="inline", escape=True,
                         heading_numbers=True, links=True, ref_links=True)
    md = MarkdownConverter(renderer).convert(_document()).text
    assert md == _convert(_document(), ref_links=True)
    # The converter hands the targets for its conversion only.
    assert renderer.ref_targets == frozenset()
    assert renderer.render_text(rt("see Method", refs=[NodeRef(label="method",
                                                               text_span=[4, 10])])) == "see Method"


def test_an_explicit_renderer_without_ref_links_keeps_todays_output() -> None:
    renderer = MarkdownConverter.default_renderer()
    assert MarkdownConverter(renderer).convert(_document()).text == _convert(_document())


def test_a_renderer_alone_links_the_targets_it_is_given() -> None:
    renderer = MarkdownRenderer(escape=True, ref_links=True, ref_targets=frozenset({"m"}))
    text = rt("see M and N", refs=[NodeRef(label="m", text_span=[4, 5]),
                                   NodeRef(label="n", text_span=[10, 11])])
    assert renderer.render_text(text) == "see [M](#m) and N"


def test_the_default_renderer_takes_ref_links() -> None:
    renderer = MarkdownConverter.default_renderer(ref_links=True)
    assert isinstance(renderer, MarkdownRenderer) and renderer.ref_links


def test_ref_links_needs_escape() -> None:
    with pytest.raises(ValueError, match="escape"):
        MarkdownRenderer(ref_links=True)


def test_ref_links_writes_html_so_text_only_refuses_it() -> None:
    with pytest.raises(ValueError, match="text_only"):
        MarkdownRenderer(escape=True, text_only=True, ref_links=True)
    with pytest.raises(ValueError, match="text_only"):
        MarkdownConverter(text_only=True, ref_links=True)


def test_ref_links_belongs_to_an_injected_renderer() -> None:
    with pytest.raises(ValueError, match="ref_links"):
        MarkdownConverter(MarkdownConverter.default_renderer(), ref_links=True)


def test_one_converter_in_several_threads() -> None:
    from concurrent.futures import ThreadPoolExecutor

    converter = MarkdownConverter(ref_links=True)

    def convert(n: int) -> str:
        label = f"t{n}"
        cnd = _cnd([_heading(label, "H"), _ref("see H", label, [4, 5])])
        return _body(converter.convert(cnd).text)

    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(convert, range(64)))
    for n, body in enumerate(results):
        assert body == f'## <a id="t{n}"></a>H\n\nsee [H](#t{n})'


def test_a_table_target_keeps_its_table() -> None:
    from factories import cell

    table = TableNode(type="table", id=uuid4(), kind="content", label="tab",
                      cells=[cell(0, 0, "a"), cell(0, 1, "b"), cell(1, 0, "1"), cell(1, 1, "2")])
    md = _convert(_cnd([table, _ref("in the table", "tab", [7, 12])]), ref_links=True)
    tokens = MarkdownIt("commonmark").enable("table").parse(_body(md))
    assert any(token.type == "table_open" for token in tokens)
    _assert_every_link_lands(md)
