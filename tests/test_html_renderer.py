"""HtmlNodeRenderer on the 0.5 elements (docs/proposals/0013, "Rendering")."""

from uuid import uuid4

from factories import cell, item, para, rt

from cnd.converters.html import HtmlNodeRenderer
from cnd.core.nodes import (
    AdmonitionNode,
    CodeNode,
    FigureNode,
    HeadingNode,
    ImageNode,
    LayoutNode,
    ListNode,
    MathNode,
    QuoteNode,
    TableNode,
    TermItem,
    TermsNode,
)
from cnd.core.render import NodeRenderer
from cnd.core.text import Mark, Numbering, RawSource

H = HtmlNodeRenderer()


def _id() -> dict:
    return {"id": uuid4()}


def test_every_node_type_has_a_method() -> None:
    abstract = NodeRenderer.__abstractmethods__
    assert {"render_admonition", "render_layout", "render_text"} <= abstract
    HtmlNodeRenderer()  # instantiable: implements them all


def test_paragraph_marks_and_math() -> None:
    raw = RawSource(format="typst", value="x^2")
    text = rt("Bold x2 here", marks=[
        Mark(start=0, end=4, kind="strong"),
        Mark(start=5, end=7, kind="math", raw=raw),
    ])
    assert H.render(para(text)) == '<p><strong>Bold</strong> <code class="math">x^2</code> here</p>'


def test_paragraph_lang_comes_from_its_text() -> None:
    assert H.render(para(rt("Hallo", lang="de"))) == '<p lang="de">Hallo</p>'


def test_heading_numbering() -> None:
    node = HeadingNode(
        type="heading", level=2, text=rt("Scope"), heading_path=["Scope"],
        numbering=Numbering(value="3", name="Chapter"), **_id(),
    )
    assert H.render(node) == "<h2>Chapter 3 Scope</h2>"


def test_tight_list_with_checkbox_and_nested_list() -> None:
    nested = ListNode(type="list", ordered=False, items=[item("b")], **_id())
    node = ListNode(type="list", ordered=True, items=[item("a", nested, checked=True)], **_id())
    assert H.render(node) == (
        '<ol><li><input type="checkbox" disabled checked> a<ul><li>b</li></ul></li></ol>'
    )


def test_loose_item_keeps_paragraphs() -> None:
    node = ListNode(type="list", items=[item("a", "b")], **_id())
    assert H.render(node) == "<ul><li><p>a</p><p>b</p></li></ul>"


def test_terms_definition_holds_blocks() -> None:
    node = TermsNode(
        type="terms",
        items=[TermItem(term=rt("T", marks=[Mark(start=0, end=1, kind="emph")]), children=[para("d")])],
        **_id(),
    )
    assert H.render(node) == "<dl><dt><em>T</em></dt><dd>d</dd></dl>"


def test_table_cells_hold_blocks() -> None:
    node = TableNode(
        type="table",
        kind="content",
        cells=[cell(0, 0, "H", is_header=True), cell(1, 0, children=[para("a"), para("b")])],
        **_id(),
    )
    assert H.render(node) == (
        '<table data-kind="content"><tr><th>H</th></tr>'
        "<tr><td><p>a</p><p>b</p></td></tr></table>"
    )


def test_layout_is_a_css_grid() -> None:
    image = ImageNode(type="image", path="a.png", alt="A", **_id())
    node = LayoutNode(type="layout", cells=[cell(0, 1, "right"), cell(0, 0, children=[image])], **_id())
    assert H.render(node) == (
        '<div class="cnd-layout" style="grid-template-columns: repeat(2, 1fr)">'
        '<div style="grid-row: 1 / span 1; grid-column: 1 / span 1"><img src="a.png" alt="A"></div>'
        '<div style="grid-row: 1 / span 1; grid-column: 2 / span 1"><p>right</p></div></div>'
    )


def test_quote_children_and_attribution() -> None:
    node = QuoteNode(type="quote", children=[para("a"), para("b")], attribution=rt("Ada"), **_id())
    assert H.render(node) == "<blockquote><p>a</p><p>b</p><footer>Ada</footer></blockquote>"


def test_admonition_is_an_aside_with_a_kind_class() -> None:
    known = AdmonitionNode(type="admonition", kind="warning", title=rt("Careful"),
                           children=[para("x")], **_id())
    assert H.render(known) == (
        '<aside class="cnd-admonition cnd-admonition-warning">'
        '<p class="cnd-admonition-title">Careful</p><p>x</p></aside>'
    )
    unknown = AdmonitionNode(type="admonition", kind="my example", children=[], **_id())
    assert H.render(unknown) == (
        '<aside class="cnd-admonition cnd-admonition-my-example">'
        '<p class="cnd-admonition-title">my example</p></aside>'
    )


def test_code_title_wraps_the_block() -> None:
    node = CodeNode(type="code", text="x", lang="py", title="main.py", label="lst", **_id())
    assert H.render(node) == (
        '<div id="lst" class="cnd-code"><p class="cnd-code-title">main.py</p>'
        '<pre><code class="language-py">x</code></pre></div>'
    )


def test_block_math_with_numbering() -> None:
    node = MathNode(type="math", text="a+b", numbering=Numbering(value="(1)"), **_id())
    assert H.render(node) == (
        '<div class="cnd-math-block"><code class="cnd-math">a+b</code>'
        '<span class="cnd-number">(1)</span></div>'
    )


def test_figure_caption_then_description() -> None:
    image = ImageNode(type="image", path="a.png", alt="A", **_id())
    node = FigureNode(
        type="figure", kind="chart", caption=rt("Rates"), description=rt("Bars rise."),
        numbering=Numbering(value="2", name="Figure"), children=[image], **_id(),
    )
    assert H.render(node) == (
        '<figure data-kind="chart"><img src="a.png" alt="A">'
        '<figcaption>Figure 2: Rates<p class="cnd-description">Bars rise.</p></figcaption></figure>'
    )
