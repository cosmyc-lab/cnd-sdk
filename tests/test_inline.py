"""The inline layer: rich text to Markdown, HTML and plain text
(docs/proposals/0013, "Marks" and "Rendering")."""

import pytest
from markdown_it import MarkdownIt

from factories import rt

from cnd.core.inline import concat_texts, render_inline, with_whole_mark
from cnd.core.text import LinkRef, Mark, NodeRef, RawSource


def m(start: int, end: int, kind: str, **kw) -> Mark:
    return Mark(start=start, end=end, kind=kind, **kw)


def md(text, **kw) -> str:
    return render_inline(text, "markdown", **kw)


def html(text) -> str:
    return render_inline(text, "html")


def parsed(markdown: str) -> str:
    """The HTML a CommonMark + GFM parser makes of ``markdown``."""
    parser = MarkdownIt("commonmark").enable("strikethrough")
    return parser.render(markdown).strip()


class TestMarkdownMarks:
    @pytest.mark.parametrize(
        ("kind", "expected"),
        [
            ("strong", "a **bc** d"),
            ("emph", "a *bc* d"),
            ("code", "a `bc` d"),
            ("strike", "a ~~bc~~ d"),
            ("sup", "a <sup>bc</sup> d"),
            ("sub", "a <sub>bc</sub> d"),
            ("underline", "a <u>bc</u> d"),
            ("highlight", "a <mark>bc</mark> d"),
            ("math", "a $bc$ d"),
            ("smallcaps", "a bc d"),
        ],
    )
    def test_every_kind(self, kind: str, expected: str) -> None:
        assert md(rt("a bc d", marks=[m(2, 4, kind)])) == expected

    @pytest.mark.parametrize("kind", ["sup", "sub", "underline", "highlight"])
    def test_text_only_drops_the_html_marks(self, kind: str) -> None:
        assert md(rt("a bc d", marks=[m(2, 4, kind)]), text_only=True) == "a bc d"

    def test_text_only_keeps_the_markdown_marks(self) -> None:
        text = rt("a bc d", marks=[m(0, 1, "strong"), m(2, 4, "code")])
        assert md(text, text_only=True) == "**a** `bc` d"

    def test_math_renders_its_source(self) -> None:
        raw = RawSource(format="typst", value="E = m c^2")
        text = rt("so E = mc2 holds", marks=[m(3, 10, "math", raw=raw)])
        assert md(text) == "so $E = m c^2$ holds"
        assert render_inline(text, "plain") == "so E = mc2 holds"

    def test_escape_touches_plain_segments_only(self) -> None:
        text = rt("a_b *c* x_1", marks=[m(4, 7, "code")])
        assert md(text, escape=True) == "a_b `*c*` x_1"
        text = rt("*x* y", marks=[m(4, 5, "strong")])
        assert md(text, escape=True) == "\\*x\\* **y**"

    def test_no_escape_by_default(self) -> None:
        assert md(rt("1. *a*")) == "1. *a*"


class TestNesting:
    def test_nested_marks(self) -> None:
        text = rt("abcdef", marks=[m(0, 6, "strong"), m(2, 4, "emph")])
        assert md(text) == "**ab*cd*ef**"
        assert parsed(md(text)) == "<p><strong>ab<em>cd</em>ef</strong></p>"

    def test_crossing_marks_split_and_still_parse(self) -> None:
        text = rt("abcdefgh", marks=[m(0, 5, "strong"), m(3, 8, "emph")])
        out = md(text)
        # The strong piece closes after the emph's "*": a "**" there could
        # not close, so it falls back to its tag.
        assert out == "<strong>abc*de*</strong>*fgh*"
        assert parsed(out) == "<p><strong>abc<em>de</em></strong><em>fgh</em></p>"

    def test_crossing_marks_in_html(self) -> None:
        text = rt("abcdefgh", marks=[m(0, 5, "strong"), m(3, 8, "emph")])
        assert html(text) == "<strong>abc<em>de</em></strong><em>fgh</em>"

    def test_a_star_opener_never_touches_a_star_closer(self) -> None:
        text = rt("abcd", marks=[m(0, 2, "strong"), m(2, 4, "emph")])
        out = md(text)
        assert out == "**ab**<em>cd</em>"
        assert parsed(out) == "<p><strong>ab</strong><em>cd</em></p>"

    def test_outer_whitespace_moves_outside_the_delimiters(self) -> None:
        text = rt("a bold b", marks=[m(1, 7, "strong")])
        out = md(text)
        assert out == "a **bold** b"
        assert parsed(out) == "<p>a <strong>bold</strong> b</p>"

    def test_whitespace_only_mark_renders_nothing(self) -> None:
        assert md(rt("a   b", marks=[m(1, 4, "strong")])) == "a   b"

    def test_punctuation_flanked_closer_falls_back_to_html(self) -> None:
        text = rt('"x"y', marks=[m(0, 3, "strong")])
        out = md(text)
        assert out == '<strong>"x"</strong>y'
        assert parsed(out) == "<p><strong>&quot;x&quot;</strong>y</p>"

    def test_punctuation_flanked_fallback_is_dropped_when_text_only(self) -> None:
        text = rt('"x"y', marks=[m(0, 3, "strong")])
        assert md(text, text_only=True) == '"x"y'

    def test_code_inside_strong(self) -> None:
        text = rt("run it", marks=[m(0, 6, "strong"), m(0, 3, "code")])
        out = md(text)
        assert out == "**`run` it**"
        assert parsed(out) == "<p><strong><code>run</code> it</strong></p>"


class TestAtoms:
    def test_code_span_outgrows_backtick_runs(self) -> None:
        text = rt("x a``b y", marks=[m(2, 6, "code")])
        assert md(text) == "x ```a``b``` y"

    def test_code_span_pads_an_edge_backtick(self) -> None:
        text = rt("`a", marks=[m(0, 2, "code")])
        out = md(text)
        assert out == "`` `a ``"
        assert parsed(out) == "<p><code>`a</code></p>"

    def test_newline_in_a_code_span_becomes_a_space(self) -> None:
        text = rt("a\n# b", marks=[m(0, 5, "code")])
        out = md(text)
        assert out == "`a # b`"
        assert "<h1>" not in parsed(out)

    def test_html_code_and_math(self) -> None:
        raw = RawSource(format="typst", value="x < y")
        text = rt("a<b and x<y", marks=[m(0, 3, "code"), m(8, 11, "math", raw=raw)])
        assert html(text) == '<code>a&lt;b</code> and <code class="math">x &lt; y</code>'


class TestDialects:
    def test_html_maps_every_known_kind(self) -> None:
        kinds = ["strong", "emph", "strike", "sup", "sub", "underline", "highlight"]
        tags = ["strong", "em", "s", "sup", "sub", "u", "mark"]
        for kind, tag in zip(kinds, tags):
            assert html(rt("ab", marks=[m(0, 2, kind)])) == f"<{tag}>ab</{tag}>"

    def test_html_escapes_text(self) -> None:
        assert html(rt('a < b & "c"')) == "a &lt; b &amp; &quot;c&quot;"

    def test_html_unknown_kind_is_plain(self) -> None:
        assert html(rt("ab", marks=[m(0, 2, "smallcaps")])) == "ab"

    def test_plain_drops_every_mark(self) -> None:
        text = rt("abcd", marks=[m(0, 2, "strong"), m(2, 4, "sup")])
        assert render_inline(text, "plain") == "abcd"

    def test_out_of_bounds_mark_never_raises(self) -> None:
        text = rt("ab", marks=[m(1, 9, "strong"), m(5, 7, "emph")])
        assert md(text) == "a**b**"


class TestEdges:
    """Edge spans take part only when the caller wraps them."""

    @staticmethod
    def _anchor(edge) -> tuple[str, str]:
        return f'<a href="{edge.href}">', "</a>"

    def test_without_edge_wrap_edges_change_nothing(self) -> None:
        marks = [m(0, 4, "strong")]
        linked = rt("abcdef", marks=marks, links=[LinkRef(href="u", text_span=[2, 6])])
        assert md(linked) == md(rt("abcdef", marks=marks)) == "**abcd**ef"
        assert html(linked) == "<strong>abcd</strong>ef"

    def test_a_wrapped_edge_crossing_a_mark_nests(self) -> None:
        text = rt("abcdef", marks=[m(0, 4, "strong")], links=[LinkRef(href="u", text_span=[2, 6])])
        out = render_inline(text, "html", edge_wrap=self._anchor)
        assert out == '<strong>ab<a href="u">cd</a></strong><a href="u">ef</a>'

    def test_a_wrapped_edge_inside_a_mark_in_markdown(self) -> None:
        text = rt("see the docs", marks=[m(4, 12, "emph")], links=[LinkRef(href="u", text_span=[8, 12])])
        out = render_inline(text, "markdown", edge_wrap=lambda e: ("[", f"]({e.href})"))
        assert out == "see *the [docs](u)*"
        assert parsed(out) == '<p>see <em>the <a href="u">docs</a></em></p>'

    def test_edge_wrap_returning_none_skips_the_edge(self) -> None:
        text = rt("abc", refs=[NodeRef(label="x", text_span=[0, 3])])
        assert render_inline(text, "html", edge_wrap=lambda e: None) == "abc"


class TestComposition:
    def test_concat_shifts_marks(self) -> None:
        text = concat_texts("Figure 1: ", rt("big deal", marks=[m(0, 3, "strong")]))
        assert text.value == "Figure 1: big deal"
        assert [(mk.start, mk.end) for mk in text.marks] == [(10, 13)]

    def test_concat_skips_none(self) -> None:
        assert concat_texts("a", None, rt("b")).value == "ab"

    def test_whole_mark_absorbs_same_kind_marks(self) -> None:
        text = with_whole_mark(rt("abc", marks=[m(0, 1, "emph"), m(1, 2, "strong")]), "emph")
        assert sorted((mk.kind, mk.start, mk.end) for mk in text.marks) == [
            ("emph", 0, 3),
            ("strong", 1, 2),
        ]
        assert md(text) == "*a**b**c*"


class TestFlankingOnTheRenderedEdge:
    """A delimiter touches the rendered inner text: when a nested mark
    opens or closes at the edge, its own delimiter is the neighbour."""

    @pytest.mark.parametrize(
        ("value", "marks", "expected"),
        [
            # emph and strike over the same word after a letter
            ("xab", [m(1, 3, "emph"), m(1, 3, "strike")], "<p>x<em><s>ab</s></em></p>"),
            # a nested mark opening at the edge
            ("xabc", [m(1, 4, "emph"), m(1, 2, "strike")], "<p>x<em><s>a</s>bc</em></p>"),
            # a nested mark closing at the edge
            ("abcx", [m(0, 3, "emph"), m(2, 3, "strike")], "<p><em>ab<s>c</s></em>x</p>"),
            # strong around strike, both edges
            ("xaby", [m(1, 3, "strong"), m(1, 3, "strike")], "<p>x<s><strong>ab</strong></s>y</p>"),
            # a code span opening at the edge
            ("xab", [m(1, 3, "emph"), m(1, 2, "code")], "<p>x<em><code>a</code>b</em></p>"),
        ],
    )
    def test_nested_mark_at_the_edge_round_trips(self, value, marks, expected) -> None:
        assert parsed(md(rt(value, marks=marks), escape=True)) == expected

    def test_the_reported_case(self) -> None:
        out = md(rt("xab", marks=[m(1, 3, "emph"), m(1, 3, "strike")]))
        assert out == "x<em>~~ab~~</em>"

    def test_text_only_drops_the_mark_it_cannot_delimit(self) -> None:
        out = md(rt("xab", marks=[m(1, 3, "emph"), m(1, 3, "strike")]), text_only=True)
        assert out == "x~~ab~~"
        assert "*" not in out

    def test_spaces_around_still_take_delimiters(self) -> None:
        out = md(rt("x ab y", marks=[m(2, 4, "emph"), m(2, 4, "strike")]))
        assert out == "x *~~ab~~* y"
        assert parsed(out) == "<p>x <em><s>ab</s></em> y</p>"
