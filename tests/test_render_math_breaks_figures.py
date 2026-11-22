"""Math sources, paragraph breaks inside marks, heading lines and figure
content in the Markdown and HTML renderers."""

from uuid import uuid4

from markdown_it import MarkdownIt

from factories import para, rt

from cnd.converters.html import HtmlNodeRenderer
from cnd.core.inline import render_inline
from cnd.core.nodes import CodeNode, FigureNode, HeadingNode, MathNode
from cnd.core.render import MarkdownRenderer
from cnd.core.text import Mark, RawSource

MD = MarkdownRenderer()
HTML = HtmlNodeRenderer()


def _id() -> dict:
    return {"id": uuid4()}


def _math_text(value: str, source: RawSource | None):
    return rt(value, marks=[Mark(start=0, end=len(value), kind="math", raw=source)])


def _heading(text, level: int = 1) -> HeadingNode:
    return HeadingNode(type="heading", level=level, text=text, heading_path=[], **_id())


def _tokens(markdown: str, *types: str) -> list:
    found = []
    for token in MarkdownIt("commonmark").parse(markdown):
        for t in [token, *(token.children or [])]:
            if t.type in types:
                found.append(t)
    return found


class TestInlineMathSource:
    def test_latex_source_goes_between_dollars(self) -> None:
        text = _math_text("x²", RawSource(format="latex", value="x^{2}"))
        assert render_inline(text, "markdown") == "$x^{2}$"

    def test_latex_format_is_case_insensitive(self) -> None:
        text = _math_text("x²", RawSource(format="LaTeX", value="x^{2}"))
        assert render_inline(text, "markdown") == "$x^{2}$"

    def test_typst_source_is_not_written_as_latex(self) -> None:
        text = _math_text("x²", RawSource(format="typst", value="x^2 + sum_(i=1)^n i"))
        assert render_inline(text, "markdown") == "x²"

    def test_without_raw_the_linear_value_is_written(self) -> None:
        assert render_inline(_math_text("a+b", None), "markdown") == "a+b"

    def test_dollar_inside_latex_is_neutralised(self) -> None:
        text = _math_text("x", RawSource(format="latex", value="a $ b \\$ c \\\\$ d"))
        assert render_inline(text, "markdown") == "$a \\$ b \\$ c \\\\\\$ d$"

    def test_dollar_in_the_linear_value_is_escaped(self) -> None:
        out = render_inline(_math_text("cost $5", None), "markdown", escape=True)
        assert out == "cost \\$5"

    def test_html_follows_the_same_rule(self) -> None:
        typst = _math_text("x²", RawSource(format="typst", value="x^2"))
        latex = _math_text("x²", RawSource(format="latex", value="x^{2}"))
        assert render_inline(typst, "html") == '<code class="math">x²</code>'
        assert render_inline(latex, "html") == '<code class="math">x^{2}</code>'


class TestDollarsInProse:
    def test_two_dollars_in_prose_are_not_math(self) -> None:
        out = MarkdownRenderer(escape=True).render(para("It costs $5 and then $10."))
        assert out == "It costs \\$5 and then \\$10."
        assert "math" not in "".join(t.type for t in MarkdownIt("commonmark").parse(out))
        inline = _tokens(out, "inline")[0]
        assert inline.content == "It costs \\$5 and then \\$10."
        assert "".join(c.content for c in inline.children) == "It costs $5 and then $10."


class TestBlockMathHtml:
    def _node(self, raw: RawSource | None) -> MathNode:
        return MathNode(type="math", text="x²", raw=raw, **_id())

    def test_latex_raw_is_the_source(self) -> None:
        out = HTML.render(self._node(RawSource(format="latex", value="x^{2}")))
        assert '<code class="cnd-math">x^{2}</code>' in out

    def test_other_raw_keeps_the_linear_text(self) -> None:
        out = HTML.render(self._node(RawSource(format="typst", value="x^2")))
        assert '<code class="cnd-math">x²</code>' in out

    def test_no_raw_keeps_the_text(self) -> None:
        assert '<code class="cnd-math">x²</code>' in HTML.render(self._node(None))


class TestMarksAcrossParagraphBreaks:
    def test_strong_is_split_per_paragraph(self) -> None:
        text = rt("alpha\n\nbeta", marks=[Mark(start=0, end=11, kind="strong")])
        out = MD.render_text(text)
        assert out == "**alpha**\n\n**beta**"
        paragraphs = _tokens(out, "paragraph_open")
        assert len(paragraphs) == 2
        assert len(_tokens(out, "strong_open")) == 2
        assert "**" not in "".join(t.content for t in _tokens(out, "text"))

    def test_emph_across_several_breaks_and_a_whitespace_only_line(self) -> None:
        text = rt("a\n\nb\n  \n\nc", marks=[Mark(start=0, end=10, kind="emph")])
        out = MD.render_text(text)
        assert len(_tokens(out, "em_open")) == 3
        assert len(_tokens(out, "paragraph_open")) == 3

    def test_single_line_break_keeps_one_mark(self) -> None:
        text = rt("alpha\nbeta", marks=[Mark(start=0, end=10, kind="strong")])
        assert MD.render_text(text) == "**alpha\nbeta**"

    def test_html_only_mark_is_split_too(self) -> None:
        text = rt("alpha\n\nbeta", marks=[Mark(start=0, end=11, kind="underline")])
        assert MD.render_text(text) == "<u>alpha</u>\n\n<u>beta</u>"

    def test_html_keeps_one_element(self) -> None:
        text = rt("alpha\n\nbeta", marks=[Mark(start=0, end=11, kind="strong")])
        assert render_inline(text, "html") == "<strong>alpha\n\nbeta</strong>"


class TestHeadings:
    def test_newline_in_a_heading_is_folded(self) -> None:
        out = MD.render(_heading(rt("one\ntwo\r\nthree")))
        assert "\n" not in out and "\r" not in out
        heading = _tokens(out, "heading_open")
        assert len(heading) == 1
        assert _tokens(out, "inline")[0].content == "one two  three"
        assert len(_tokens(out, "paragraph_open")) == 0

    def test_marks_keep_their_place_after_folding(self) -> None:
        text = rt("one\ntwo", marks=[Mark(start=4, end=7, kind="strong")])
        assert MD.render(_heading(text, 2)) == "## one **two**"

    def test_level_above_six_is_clamped(self) -> None:
        out = MD.render(_heading(rt("Deep"), 7))
        assert out == "###### Deep"
        assert len(_tokens(out, "heading_open")) == 1

    def test_level_six_is_unchanged(self) -> None:
        assert MD.render(_heading(rt("Deep"), 6)) == "###### Deep"


class TestFigureContent:
    def _listing(self) -> FigureNode:
        return FigureNode(
            type="figure",
            kind="listing",
            children=[
                CodeNode(type="code", text="x = 1", lang="python", **_id()),
                para("Sets the counter."),
            ],
            **_id(),
        )

    def test_placeholder_keeps_the_code_and_the_paragraph(self) -> None:
        out = MD.render(self._listing())
        assert "x = 1" in out
        assert "Sets the counter." in out
        assert out.count("\n") == 0

    def test_code_without_text_keeps_its_label(self) -> None:
        node = FigureNode(
            type="figure",
            children=[CodeNode(type="code", text="", lang="json", **_id())],
            **_id(),
        )
        assert 'summary="code (json)"' in MD.render(node)

    def test_html_figure_keeps_everything(self) -> None:
        out = HTML.render(self._listing())
        assert "x = 1" in out and "Sets the counter." in out
