"""MarkdownRenderer on the 0.5 elements (docs/proposals/0013, "Rendering")."""

from uuid import uuid4

import pytest
from markdown_it import MarkdownIt

from factories import cell, item, para, rt

from cnd.core.nodes import (
    AdmonitionNode,
    CodeNode,
    FigureNode,
    ImageNode,
    LayoutNode,
    ListNode,
    QuoteNode,
    TableNode,
    TermItem,
    TermsNode,
)
from cnd.core.render import MarkdownRenderer
from cnd.core.text import Mark, Numbering

R = MarkdownRenderer()


def _id() -> dict:
    return {"id": uuid4()}


def _list(*items, ordered: bool = False) -> ListNode:
    return ListNode(type="list", ordered=ordered, items=list(items), **_id())


def _image(path: str = "a.png", alt: str = "A") -> ImageNode:
    return ImageNode(type="image", path=path, alt=alt, **_id())


def _parse(markdown: str) -> list:
    return MarkdownIt("commonmark").enable("table").parse(markdown)


class TestParagraphMarks:
    def test_paragraph_renders_its_marks(self) -> None:
        text = rt("x 103 y", marks=[Mark(start=4, end=5, kind="sup")])
        assert R.render(para(text)) == "x 10<sup>3</sup> y"

    def test_text_only_renders_no_html(self) -> None:
        text = rt("x 103 y", marks=[Mark(start=4, end=5, kind="sup")])
        assert MarkdownRenderer(text_only=True).render(para(text)) == "x 103 y"

    def test_escape_skips_code_marks(self) -> None:
        text = rt("use *a* or *b*", marks=[Mark(start=4, end=7, kind="code")])
        assert MarkdownRenderer(escape=True).render(para(text)) == "use `*a*` or \\*b\\*"


class TestLists:
    def test_checked_items(self) -> None:
        node = _list(item("done", checked=True), item("todo", checked=False), item("plain"))
        assert R.render(node) == "- [x] done\n- [ ] todo\n- plain"

    def test_ordered_checked_item(self) -> None:
        assert R.render(_list(item("a", checked=True), ordered=True)) == "1. [x] a"

    def test_nested_list_keeps_its_own_kind_and_stays_tight(self) -> None:
        node = _list(item("Step", _list(item("detail"))), ordered=True)
        assert R.render(node) == "1. Step\n   - detail"

    def test_an_item_with_several_blocks_makes_the_list_loose(self) -> None:
        node = _list(item("one", "more"), item("two"))
        out = R.render(node)
        assert out == "- one\n\n  more\n\n- two"
        tokens = _parse(out)
        assert [t.type for t in tokens].count("paragraph_open") == 3
        assert [t.hidden for t in tokens if t.type == "paragraph_open"] == [False] * 3

    def test_an_item_holding_a_code_block_indents_the_fence(self) -> None:
        code = CodeNode(type="code", text="x = 1", lang="py", **_id())
        out = R.render(_list(item("Run:", code)))
        assert out == "- Run:\n\n  ```py\n  x = 1\n  ```"
        assert [t.type for t in _parse(out)].count("fence") == 1

    def test_empty_item(self) -> None:
        assert R.render(_list(item(), item("b"))) == "-\n- b"


class TestTermsQuoteAdmonitionCode:
    def test_definition_with_several_blocks(self) -> None:
        node = TermsNode(
            type="terms",
            items=[TermItem(term=rt("Mark"), children=[para("One."), para("Two.")])],
            **_id(),
        )
        assert R.render(node) == "**Mark**\n: One.\n\n  Two."

    def test_term_marks_nest_inside_the_bold(self) -> None:
        term = rt("Mark", marks=[Mark(start=0, end=4, kind="emph")])
        node = TermsNode(type="terms", items=[TermItem(term=term, children=[para("d")])], **_id())
        assert R.render(node) == "***Mark***\n: d"

    def test_quote_with_two_paragraphs_and_attribution(self) -> None:
        node = QuoteNode(
            type="quote", children=[para("One."), para("Two.")], attribution=rt("Ada"), **_id()
        )
        assert R.render(node) == "> One.\n>\n> Two.\n>\n> — Ada"

    def test_known_admonition_is_a_gfm_alert(self) -> None:
        node = AdmonitionNode(
            type="admonition", kind="warning", title=rt("Careful"),
            children=[para("Never edit in place.")], **_id(),
        )
        assert R.render(node) == "> [!WARNING]\n> **Careful**\n>\n> Never edit in place."

    def test_known_admonition_without_title(self) -> None:
        node = AdmonitionNode(type="admonition", kind="note", children=[para("x")], **_id())
        assert R.render(node) == "> [!NOTE]\n>\n> x"

    def test_unknown_admonition_is_a_quote_headed_by_its_title(self) -> None:
        node = AdmonitionNode(
            type="admonition", kind="example", title=rt("Try it"), children=[para("x")], **_id()
        )
        assert R.render(node) == "> **Try it**\n>\n> x"

    def test_unknown_admonition_without_title_is_headed_by_its_kind(self) -> None:
        node = AdmonitionNode(type="admonition", kind="example", children=[para("x")], **_id())
        assert R.render(node) == "> **example**\n>\n> x"

    def test_code_title_is_a_line_before_the_fence(self) -> None:
        node = CodeNode(type="code", text="print(1)", lang="python", title="main.py", **_id())
        out = R.render(node)
        assert out == "main.py\n```python\nprint(1)\n```"
        assert [t.type for t in _parse(out)][:4] == [
            "paragraph_open", "inline", "paragraph_close", "fence",
        ]

    def test_code_ending_in_a_newline_adds_no_blank_line(self) -> None:
        node = CodeNode(type="code", text="a = 1\n", lang="python", **_id())
        out = R.render(node)
        assert out == "```python\na = 1\n```"
        fence = [t for t in _parse(out) if t.type == "fence"][0]
        assert fence.content == "a = 1\n"

    def test_code_strips_only_one_trailing_newline(self) -> None:
        node = CodeNode(type="code", text="a\n\n", **_id())
        assert R.render(node) == "```\na\n\n```"

    def test_code_title_is_escaped_with_the_text(self) -> None:
        node = CodeNode(type="code", text="x", title="__init__.py", **_id())
        out = MarkdownRenderer(escape=True).render(node)
        assert out.splitlines()[0] == "\\_\\_init\\_\\_.py"


class TestTablesAndLayouts:
    def _table(self, *cells, kind: str | None = None) -> TableNode:
        return TableNode(type="table", kind=kind, cells=list(cells), **_id())

    def test_inline_cells_make_a_gfm_table_with_marks(self) -> None:
        bold = para(rt("Pro", marks=[Mark(start=0, end=3, kind="strong")]))
        node = self._table(
            cell(0, 0, "Plan", is_header=True),
            cell(0, 1, "Logo", is_header=True),
            cell(1, 0, children=[bold]),
            cell(1, 1, children=[_image("pro.png", "Pro logo")]),
        )
        out = MarkdownRenderer(tables="inline").render(node)
        assert out == "| Plan | Logo |\n| --- | --- |\n| **Pro** | ![Pro logo](pro.png) |"

    def test_empty_cells_stay_in_the_gfm_table(self) -> None:
        node = self._table(cell(0, 0, "A", is_header=True), cell(0, 1), cell(1, 0, "x"))
        out = MarkdownRenderer(tables="inline").render(node)
        assert out.startswith("| A |  |")

    def test_block_cells_make_an_html_table_without_blank_lines(self) -> None:
        node = self._table(
            cell(0, 0, "Step", is_header=True),
            cell(1, 0, children=[para("One."), para("Two.")]),
        )
        out = MarkdownRenderer(tables="inline").render(node)
        assert out == (
            "<table><tr><th>Step</th></tr><tr><td><p>One.</p><p>Two.</p></td></tr></table>"
        )
        assert "\n" not in out

    def test_html_table_keeps_a_code_block_on_one_line(self) -> None:
        code = CodeNode(type="code", text="a\n\nb", **_id())
        node = self._table(cell(0, 0, children=[para("x"), code]))
        out = MarkdownRenderer(tables="inline").render(node)
        assert "\n" not in out and "a&#10;&#10;b" in out
        assert [t.type for t in _parse(out)] == ["html_block"]

    def test_block_cells_under_text_only_become_rows(self) -> None:
        node = self._table(
            cell(0, 0, "Step", is_header=True),
            cell(0, 1, "Note", is_header=True),
            cell(1, 0, "Build"),
            cell(1, 1, children=[para("Slow."), para("Cached.")]),
            cell(2, 0, "Ship"),
            cell(2, 1, "Fast."),
        )
        out = MarkdownRenderer(tables="inline", text_only=True).render(node)
        assert out == (
            "- Step: Build\n\n  Note: Slow.\n\n  Cached.\n\n"
            "- Step: Ship\n  Note: Fast."
        )
        assert "<" not in out

    def test_auto_mode_reads_table_kind(self) -> None:
        cells = [cell(0, 0, "A", is_header=True)]
        renderer = MarkdownRenderer(tables="auto")
        assert renderer.render(self._table(*cells, kind="content")) == "| A |\n| --- |"
        for kind in ("data", None, "matrix"):
            assert renderer.render(self._table(*cells, kind=kind)).startswith("[[figure:")

    def test_layout_is_flattened_row_by_row_in_every_mode(self) -> None:
        node = LayoutNode(
            type="layout",
            cells=[
                cell(1, 0, "third"),
                cell(0, 1, children=[_image("b.png", "B")]),
                cell(0, 0, "first"),
            ],
            **_id(),
        )
        for renderer in (MarkdownRenderer(), MarkdownRenderer(tables="inline")):
            assert renderer.render(node) == "first\n\n![B](b.png)\n\nthird"


class TestFigures:
    def _figure(self, **kwargs) -> FigureNode:
        return FigureNode(type="figure", **_id(), **kwargs)

    def test_description_follows_the_caption(self) -> None:
        node = self._figure(
            kind="chart",
            caption=rt("Rates"),
            description=rt("Bars: A 38 %, B 27 %."),
            numbering=Numbering(value="2", name="Figure"),
            children=[_image("rates.png", "Rates")],
        )
        out = MarkdownRenderer(figures="inline").render(node)
        assert out == "![Rates](rates.png)\n\n*Figure 2: Rates*\n\nBars: A 38 %, B 27 %."

    def test_placeholder_carries_plain_caption_and_description(self) -> None:
        node = self._figure(
            kind="chart",
            caption=rt("Big rates", marks=[Mark(start=0, end=3, kind="strong")]),
            description=rt("Bars rise."),
            children=[_image()],
        )
        out = MarkdownRenderer().render(node)
        assert 'caption="Big rates" description="Bars rise."' in out
        assert "**" not in out

    def test_placeholder_carries_the_wrapped_table_kind(self) -> None:
        table = TableNode(type="table", kind="data", cells=[cell(0, 0, "A", is_header=True)], **_id())
        out = MarkdownRenderer().render(self._figure(kind="table", children=[table]))
        assert 'table_kind="data" header="A"' in out

    def test_caption_marks_render_inside_the_emphasis(self) -> None:
        node = self._figure(
            caption=rt("the H2O case", marks=[Mark(start=5, end=6, kind="sub")]),
            numbering=Numbering(value="1", name="Figure"),
            children=[_image()],
        )
        out = MarkdownRenderer(figures="inline").render(node)
        assert out.endswith("*Figure 1: the H<sub>2</sub>O case*")


@pytest.mark.parametrize("text_only", [False, True])
def test_every_element_of_the_elements_fixture_renders(elements_cnd_path, text_only) -> None:
    from cnd.core.cnd import Cnd

    cnd = Cnd.model_validate_json(elements_cnd_path.read_text())
    renderer = MarkdownRenderer(tables="inline", figures="inline", text_only=text_only)
    for visit in cnd.iter_all():
        assert renderer.render(visit.node).strip()
