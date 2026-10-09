from pathlib import Path
from uuid import uuid4

import pytest

from cnd.core.cnd import Cnd
from cnd.core.node_text import (
    format_figure_placeholder,
    render_list_markdown,
    render_table_markdown,
    table_node_placeholder,
)
from cnd.core.nodes import (
    CodeNode,
    FigureNode,
    HeadingNode,
    ImageNode,
    ListItem,
    ListNode,
    MathNode,
    NodeLocation,
    ParagraphNode,
    QuoteNode,
    TableCell,
    TableNode,
    TermItem,
    TermsNode,
)
from cnd.core.render import MarkdownRenderer, NodeRenderer

FIXTURES_DIR = Path(__file__).parent.parent / "fixtures"
ALL_FIXTURES = sorted(FIXTURES_DIR.glob("*.cnd"))


def _location() -> NodeLocation:
    return NodeLocation(page=1)


def _base(**kwargs):
    defaults = {
        "id": uuid4(),
        "location": _location(),
    }
    defaults.update(kwargs)
    return defaults


class TestRendererAbc:
    def test_nodes_have_no_to_text(self) -> None:
        node = ParagraphNode(type="paragraph", text="Hello", **_base())
        assert not hasattr(node, "to_text")

    def test_incomplete_subclass_cannot_be_instantiated(self) -> None:
        class Partial(NodeRenderer):
            def render_heading(self, node):  # noqa: ANN001
                return ""

        with pytest.raises(TypeError):
            Partial()  # type: ignore[abstract]

    def test_render_dispatches_by_node_type(self) -> None:
        renderer = MarkdownRenderer()
        node = ParagraphNode(type="paragraph", text="Hello world", **_base())
        assert renderer.render(node) == renderer.render_paragraph(node)


class TestMarkdownRenderer:
    renderer = MarkdownRenderer()

    def test_heading(self) -> None:
        node = HeadingNode(
            type="heading",
            level=2,
            number="1.1",
            text="Interfaces",
            heading_path=["1 X", "1.1 Interfaces"],
            **_base(),
        )
        assert self.renderer.render(node) == "## Interfaces"

    def test_paragraph(self) -> None:
        node = ParagraphNode(type="paragraph", text="Hello world", **_base())
        assert self.renderer.render(node) == "Hello world"

    def test_quote_with_attribution(self) -> None:
        node = QuoteNode(
            type="quote",
            text="Programs must be written for people to read.",
            attribution="Ada Lovelace",
            **_base(),
        )
        assert self.renderer.render(node) == (
            "> Programs must be written for people to read.\n>\n> — Ada Lovelace"
        )

    def test_code(self) -> None:
        node = CodeNode(type="code", text="print('hi')", lang="python", **_base())
        assert self.renderer.render(node) == "```python\nprint('hi')\n```"

    def test_math(self) -> None:
        node = MathNode(type="math", text="E = m c^2", **_base())
        assert self.renderer.render(node) == "E = m c^2"

    def test_list(self) -> None:
        node = ListNode(
            type="list",
            ordered=False,
            items=[ListItem(text="Alpha"), ListItem(text="Beta")],
            **_base(),
        )
        assert self.renderer.render(node) == "- Alpha\n- Beta"

    def test_terms(self) -> None:
        node = TermsNode(
            type="terms",
            items=[
                TermItem(term="Endpoint", description="A stable URL."),
                TermItem(term="Token", description="A bearer secret."),
            ],
            **_base(),
        )
        assert self.renderer.render(node) == (
            "**Endpoint**\n: A stable URL.\n**Token**\n: A bearer secret."
        )

    def test_image_with_path(self) -> None:
        node = ImageNode(type="image", path="figures/a.png", alt="Diagram", **_base())
        assert self.renderer.render(node) == "![Diagram](figures/a.png)"

    def test_image_without_path_is_never_empty(self) -> None:
        node = ImageNode(type="image", alt="Diagram", **_base())
        rendered = self.renderer.render(node)
        assert rendered == f'[[image:{node.id} alt="Diagram"]]'

    def test_image_without_path_or_alt_is_never_empty(self) -> None:
        node = ImageNode(type="image", **_base())
        assert self.renderer.render(node) == f"[[image:{node.id}]]"


class TestTableRendering:
    _CELLS = [
        TableCell(row=0, col=0, text="A", is_header=True),
        TableCell(row=1, col=0, text="B"),
    ]

    def test_placeholder_mode_ignores_content_kind(self) -> None:
        node = TableNode(type="table", content_kind="content", cells=self._CELLS, **_base())
        assert MarkdownRenderer(tables="placeholder").render(node).startswith("[[figure:")

    def test_default_mode_is_placeholder(self) -> None:
        node = TableNode(type="table", content_kind="content", cells=self._CELLS, **_base())
        assert MarkdownRenderer().render(node) == table_node_placeholder(node)

    def test_inline_mode_renders_markdown_regardless_of_content_kind(self) -> None:
        node = TableNode(type="table", content_kind="data", cells=self._CELLS, **_base())
        assert MarkdownRenderer(tables="inline").render(node) == "| A |\n| --- |\n| B |"

    def test_auto_mode_inlines_when_content_kind_is_content(self) -> None:
        node = TableNode(type="table", content_kind="content", cells=self._CELLS, **_base())
        assert MarkdownRenderer(tables="auto").render(node) == "| A |\n| --- |\n| B |"

    def test_auto_mode_placeholders_when_content_kind_is_data_or_unset(self) -> None:
        renderer = MarkdownRenderer(tables="auto")
        data = TableNode(type="table", content_kind="data", cells=self._CELLS, **_base())
        unset = TableNode(type="table", content_kind=None, cells=self._CELLS, **_base())
        assert renderer.render(data).startswith("[[figure:")
        assert renderer.render(unset).startswith("[[figure:")

    def test_inline_mode_falls_back_to_placeholder_when_no_cells(self) -> None:
        node = TableNode(type="table", **_base())
        assert MarkdownRenderer(tables="inline").render(node).startswith("[[figure:")

    def test_placeholder_uses_kind_and_header_row(self) -> None:
        node = TableNode(
            type="table",
            kind="grid",
            cells=[
                TableCell(row=0, col=0, text="Name", is_header=True),
                TableCell(row=0, col=1, text="Value", is_header=True),
            ],
            **_base(),
        )
        rendered = MarkdownRenderer().render(node)
        assert 'kind="grid"' in rendered
        assert 'header="Name | Value"' in rendered


class TestFigureRendering:
    def _figure(self, *, children, **kwargs) -> FigureNode:
        return FigureNode(type="figure", children=children, **_base(), **kwargs)

    def test_placeholder_includes_caption_number_and_kind(self) -> None:
        node = self._figure(
            kind="image",
            caption="Diagram",
            number="1",
            children=[ImageNode(type="image", path="a.png", alt="Alt", **_base())],
        )
        rendered = MarkdownRenderer().render(node)
        assert rendered.startswith(f"[[figure:{node.id} ")
        assert 'kind="image"' in rendered
        assert 'number="1"' in rendered
        assert 'caption="Diagram"' in rendered
        assert 'summary="Alt"' in rendered

    def test_placeholder_kind_falls_back_to_child_type(self) -> None:
        node = self._figure(
            children=[CodeNode(type="code", text="x = 1", lang="python", **_base())],
        )
        rendered = MarkdownRenderer().render(node)
        assert 'kind="code"' in rendered
        assert 'summary="code (python)"' in rendered

    def test_placeholder_for_single_table_child_includes_header_row(self) -> None:
        table = TableNode(
            type="table",
            cells=[TableCell(row=0, col=0, text="Name", is_header=True)],
            **_base(),
        )
        node = self._figure(kind="table", caption="Params", children=[table])
        rendered = MarkdownRenderer().render(node)
        assert 'header="Name"' in rendered

    def test_inline_renders_children_with_caption_line(self) -> None:
        image = ImageNode(type="image", path="a.png", alt="Alt", **_base())
        node = self._figure(
            kind="image", caption="Diagram", number="1",
            counter_label="Figure", children=[image]
        )
        rendered = MarkdownRenderer(figures="inline").render(node)
        assert rendered == "![Alt](a.png)\n\n*Figure 1: Diagram*"

    def test_inline_with_no_children_falls_back_to_placeholder(self) -> None:
        node = self._figure(kind="atom", children=[], raw={"format": "typst", "value": "#figure(..)"})
        assert MarkdownRenderer(figures="inline").render(node).startswith("[[figure:")

    def test_auto_inlines_wrapped_content_table(self) -> None:
        table = TableNode(
            type="table",
            content_kind="content",
            cells=[TableCell(row=0, col=0, text="A", is_header=True)],
            **_base(),
        )
        node = self._figure(kind="table", caption="Params", children=[table])
        renderer = MarkdownRenderer(figures="auto", tables="auto")
        rendered = renderer.render(node)
        assert "| A |" in rendered
        assert "*Params*" in rendered

    def test_auto_placeholders_wrapped_data_table(self) -> None:
        table = TableNode(
            type="table",
            content_kind="data",
            cells=[TableCell(row=0, col=0, text="A", is_header=True)],
            **_base(),
        )
        node = self._figure(kind="table", children=[table])
        assert MarkdownRenderer(figures="auto").render(node).startswith("[[figure:")

    def test_nested_figures_render_inline(self) -> None:
        inner = self._figure(
            kind="image",
            caption="Sub",
            children=[ImageNode(type="image", path="b.png", **_base())],
        )
        outer = self._figure(kind="image", caption="Main", children=[inner])
        rendered = MarkdownRenderer(figures="inline").render(outer)
        assert "![](b.png)" in rendered
        assert "*Sub*" in rendered
        assert "*Main*" in rendered


class TestNodeTextHelpers:
    def test_render_list_markdown_nested(self) -> None:
        items = [ListItem(text="Parent", children=[ListItem(text="Child")])]
        assert render_list_markdown(items, ordered=True) == "1. Parent\n   1. Child"

    def test_nested_bullets_keep_two_space_indent(self) -> None:
        items = [ListItem(text="a", children=[ListItem(text="b", children=[ListItem(text="c")])])]
        assert render_list_markdown(items, ordered=False) == "- a\n  - b\n    - c"

    def test_nested_ordered_indent_follows_the_parent_marker(self) -> None:
        items = [ListItem(text="p", number=10, children=[ListItem(text="c", children=[ListItem(text="d")])])]
        assert render_list_markdown(items, ordered=True) == "10. p\n    1. c\n       1. d"

    def test_format_figure_placeholder(self) -> None:
        figure_id = uuid4()
        placeholder = format_figure_placeholder(
            figure_id=figure_id,
            kind="grid",
            caption="Layout",
            number="Figure 3",
            summary="two images",
        )
        assert str(figure_id) in placeholder
        assert 'kind="grid"' in placeholder
        assert 'summary="two images"' in placeholder

    def test_render_table_markdown_simple_grid(self) -> None:
        node = TableNode(
            type="table",
            cells=[
                TableCell(row=0, col=0, text="Name", is_header=True),
                TableCell(row=0, col=1, text="Value", is_header=True),
                TableCell(row=1, col=0, text="Torque"),
                TableCell(row=1, col=1, text="12 Nm"),
            ],
            **_base(),
        )
        assert render_table_markdown(node) == (
            "| Name | Value |\n"
            "| --- | --- |\n"
            "| Torque | 12 Nm |"
        )

    def test_render_table_markdown_no_cells_returns_empty_string(self) -> None:
        node = TableNode(type="table", **_base())
        assert render_table_markdown(node) == ""

    def test_render_table_markdown_spanned_cell_extends_grid(self) -> None:
        # A cell spanning two columns starting at the last column index any
        # other cell uses — max_col must account for colspan, not just col.
        node = TableNode(
            type="table",
            cells=[
                TableCell(row=0, col=0, text="A", colspan=2),
                TableCell(row=1, col=0, text="B"),
                TableCell(row=1, col=1, text="C"),
            ],
            **_base(),
        )
        rows = render_table_markdown(node).split("\n")
        assert rows[0] == "| A |  |"
        assert rows[-1] == "| B | C |"


class TestRenderFixtures:
    """Every node of every fixture renders to non-empty text with the
    MarkdownRenderer, at every verbosity."""

    @pytest.mark.parametrize("path", ALL_FIXTURES, ids=lambda p: p.stem)
    @pytest.mark.parametrize("mode", ["placeholder", "inline", "auto"])
    def test_all_fixture_nodes_render(self, path: Path, mode: str) -> None:
        cnd = Cnd.model_validate_json(path.read_text())
        renderer = MarkdownRenderer(tables=mode, figures=mode)
        count = 0
        for visit in cnd.iter():
            rendered = renderer.render(visit.node)
            assert isinstance(rendered, str)
            assert rendered.strip(), f"{visit.node.type} {visit.node.id} rendered empty"
            count += 1
        assert count > 0

    def test_fixtures_cover_every_node_type(self) -> None:
        seen: set[str] = set()
        for path in ALL_FIXTURES:
            cnd = Cnd.model_validate_json(path.read_text())
            for visit in cnd.iter():
                seen.add(visit.node.type)
        # Hard minimum: the types the v0.2 migration introduced or reshaped.
        assert {"heading", "paragraph", "table", "figure", "image", "code", "terms"} <= seen

    def test_real_fixture_table_auto_mode_inlines(
        self, comprehensive_cnd_path: Path
    ) -> None:
        cnd = Cnd.model_validate_json(comprehensive_cnd_path.read_text())
        table = next(
            visit.node for visit in cnd.iter() if isinstance(visit.node, TableNode)
        )
        assert table.content_kind == "content"
        rendered = MarkdownRenderer(tables="auto").render(table)

        assert not rendered.startswith("[[figure:")
        assert "Capteur" in rendered
        assert "Pression" in rendered
        assert "0–16 bar" in rendered
        rows = [line for line in rendered.split("\n") if line.startswith("|")]
        # 1 header + 1 separator + 3 data rows (Pression spans rows 1-2,
        # Débit is row 3) — the grid must be sized from row+rowspan, not
        # just the max row any single cell declares.
        assert len(rows) == 5


class TestCodeFence:
    def _code(self, text: str, lang: str | None = "markdown") -> CodeNode:
        return CodeNode(type="code", text=text, lang=lang, **_base())

    def test_plain_code_uses_three_backticks(self) -> None:
        out = MarkdownRenderer().render(self._code("print(1)", "python"))
        assert out == "```python\nprint(1)\n```"

    def test_fence_outgrows_inner_backtick_runs(self) -> None:
        text = "intro\n```typ\n#set page()\n```\nmore\n````\nend"
        out = MarkdownRenderer().render(self._code(text))
        assert out.startswith("`````markdown\n")
        assert out.endswith("\n`````")

    def test_inline_backticks_also_count(self) -> None:
        out = MarkdownRenderer().render(self._code("a ```` b", None))
        assert out.split("\n")[0] == "`````"


class TestListNumbers:
    def _items(self, *pairs: tuple[str, int | None]) -> list[ListItem]:
        return [ListItem(text=t, number=n) for t, n in pairs]

    def test_ordered_items_keep_their_numbers(self) -> None:
        out = render_list_markdown(self._items(("a", 1), ("b", 3), ("c", 7)), ordered=True)
        assert out == "1. a\n3. b\n7. c"

    def test_list_starting_at_five(self) -> None:
        out = render_list_markdown(self._items(("a", 5), ("b", 6)), ordered=True)
        assert out == "5. a\n6. b"

    def test_missing_numbers_fall_back_to_position(self) -> None:
        out = render_list_markdown(self._items(("a", None), ("b", None)), ordered=True)
        assert out == "1. a\n2. b"

    def test_bullets_ignore_numbers(self) -> None:
        out = render_list_markdown(self._items(("a", 4)), ordered=False)
        assert out == "- a"

    def test_escape_callback_applies_to_item_text(self) -> None:
        out = render_list_markdown(self._items(("x", None)), ordered=False, escape=str.upper)
        assert out == "- X"


class TestTableCells:
    def _table(self, *rows: list[str]) -> TableNode:
        cells = [
            TableCell(row=r, col=c, text=t, is_header=(r == 0))
            for r, row in enumerate(rows)
            for c, t in enumerate(row)
        ]
        return TableNode(type="table", cells=cells, **_base())

    def test_pipe_in_cell_is_escaped(self) -> None:
        out = render_table_markdown(self._table(["k", "v"], ['kind: "a" | "b"', "x"]))
        assert out.splitlines()[2] == '| kind: "a" \\| "b" | x |'

    def test_newline_in_cell_becomes_br(self) -> None:
        out = render_table_markdown(self._table(["k"], ["line one\nline two"]))
        assert out.splitlines()[2] == "| line one<br>line two |"

    def test_lone_carriage_return_in_cell_becomes_br(self) -> None:
        out = render_table_markdown(self._table(["k"], ["a\rb"]))
        assert out.splitlines()[2] == "| a<br>b |"

    def test_escape_callback_runs_before_pipe_escaping(self) -> None:
        out = render_table_markdown(self._table(["k"], ["a|b"]), escape=lambda s: s + "!")
        assert out.splitlines()[2] == "| a\\|b! |"


class TestRendererEscapeFlag:
    def test_default_renderer_does_not_escape(self) -> None:
        node = ParagraphNode(type="paragraph", text="1. a *b* <c>", **_base())
        assert MarkdownRenderer().render(node) == "1. a *b* <c>"

    def test_escape_flag_escapes_paragraph_heading_list_terms(self) -> None:
        r = MarkdownRenderer(escape=True)
        assert r.render(ParagraphNode(type="paragraph", text="1. a", **_base())) == "1\\. a"
        heading = HeadingNode(type="heading", level=2, text="Use *this*", heading_path=["Use *this*"], **_base())
        assert r.render(heading) == "## Use \\*this\\*"
        lst = ListNode(type="list", items=[ListItem(text="<x>")], **_base())
        assert r.render(lst) == "- \\<x>"
        terms = TermsNode(type="terms", items=[TermItem(term="a_", description="*b*")], **_base())
        assert r.render(terms) == "**a\\_**\n: \\*b\\*"

    def test_escape_flag_reaches_table_cells(self) -> None:
        cells = [TableCell(row=0, col=0, text="h", is_header=True), TableCell(row=1, col=0, text="*x*")]
        table = TableNode(type="table", cells=cells, **_base())
        out = MarkdownRenderer(tables="inline", escape=True).render(table)
        assert out.splitlines()[2] == "| \\*x\\* |"

    def test_code_is_never_escaped(self) -> None:
        code = CodeNode(type="code", text="*a* <b>", lang=None, **_base())
        assert MarkdownRenderer(escape=True).render(code) == "```\n*a* <b>\n```"


class TestEscapeTrailingMarkup:
    def test_term_ending_in_backslash(self) -> None:
        terms = TermsNode(type="terms", items=[TermItem(term="a\\", description="d")], **_base())
        assert MarkdownRenderer(escape=True).render(terms) == "**a\\\\**\n: d"

    def test_figure_caption_ending_in_backslash(self) -> None:
        code = CodeNode(type="code", text="x", lang=None, **_base())
        fig = FigureNode(
            type="figure", children=[code], caption="C:\\", number="1",
            counter_label="Figure", **_base(),
        )
        out = MarkdownRenderer(figures="inline", escape=True).render(fig)
        assert out.splitlines()[-1] == "*Figure 1: C:\\\\*"

    @pytest.mark.parametrize(
        ("text", "expected"),
        [
            ("C #", "## C \\#"),
            ("#", "## \\#"),
            ("C ##  ", "## C \\##  "),
            ("C#", "## C#"),
            ("Use #tags", "## Use #tags"),
        ],
    )
    def test_heading_closing_hashes(self, text: str, expected: str) -> None:
        node = HeadingNode(type="heading", level=2, text=text, heading_path=[text], **_base())
        assert MarkdownRenderer(escape=True).render(node) == expected

    def test_heading_unescaped_is_unchanged(self) -> None:
        node = HeadingNode(type="heading", level=2, text="C #", heading_path=["C #"], **_base())
        assert MarkdownRenderer().render(node) == "## C #"


class TestQuoteImageFigure:
    def test_quote_lines_are_prefixed(self) -> None:
        q = QuoteNode(type="quote", text="one\n\ntwo", attribution="Someone", **_base())
        assert MarkdownRenderer().render(q) == "> one\n>\n> two\n>\n> — Someone"

    def test_quote_normalises_carriage_returns(self) -> None:
        q = QuoteNode(type="quote", text="a\rb\r\nc", attribution="x\ry", **_base())
        assert MarkdownRenderer().render(q) == "> a\n> b\n> c\n>\n> — x\n> y"

    def test_quote_escapes_when_flagged(self) -> None:
        q = QuoteNode(type="quote", text="1. not a list", **_base())
        assert MarkdownRenderer(escape=True).render(q) == "> 1\\. not a list"

    def test_image_path_with_space_is_bracketed(self) -> None:
        img = ImageNode(type="image", path="logo team.png", alt="Team [logo]", **_base())
        assert MarkdownRenderer().render(img) == "![Team \\[logo\\]](<logo team.png>)"

    def test_plain_image_path_unchanged(self) -> None:
        img = ImageNode(type="image", path="img/a.png", alt="A", **_base())
        assert MarkdownRenderer().render(img) == "![A](img/a.png)"

    def test_childless_figure_inline_renders_caption(self) -> None:
        fig = FigureNode(type="figure", kind="image", caption="Release pipeline", number="1",
                         counter_label="Figure", children=[], **_base())
        assert MarkdownRenderer(figures="inline").render(fig) == "*Figure 1: Release pipeline*"

    def test_childless_uncaptioned_figure_keeps_placeholder(self) -> None:
        fig = FigureNode(type="figure", kind="image", children=[], **_base())
        assert MarkdownRenderer(figures="inline").render(fig).startswith("[[figure:")

    @pytest.mark.parametrize("escape", [False, True])
    def test_multiline_attribution_stays_in_quote(self, escape: bool) -> None:
        q = QuoteNode(type="quote", text="body", attribution="- x\n> y\n\nz", **_base())
        out = MarkdownRenderer(escape=escape).render(q)
        assert all(line.startswith(">") for line in out.split("\n"))
        assert out.split("\n")[-2] == ">"

    def test_quote_empty_body_line_escaped(self) -> None:
        q = QuoteNode(type="quote", text="a\n\nb", **_base())
        assert MarkdownRenderer(escape=True).render(q) == "> a\n>\n> b"


class TestHeadingNumbers:
    def _h(self, **kw) -> HeadingNode:
        return HeadingNode(type="heading", level=2, text="Scope", heading_path=["Scope"], **_base(), **kw)

    def test_numbers_off_by_default(self) -> None:
        assert MarkdownRenderer().render(self._h(number="4.1")) == "## Scope"

    def test_number_prefixes_text(self) -> None:
        assert MarkdownRenderer(heading_numbers=True).render(self._h(number="4.1")) == "## 4.1 Scope"

    def test_counter_label_and_number(self) -> None:
        out = MarkdownRenderer(heading_numbers=True).render(self._h(number="3", counter_label="Chapter"))
        assert out == "## Chapter 3 Scope"

    def test_unnumbered_heading_unchanged(self) -> None:
        assert MarkdownRenderer(heading_numbers=True).render(self._h()) == "## Scope"

    @pytest.mark.parametrize(
        ("text", "expected"),
        [("1. Intro", "## 2 1\\. Intro"), ("Intro #", "## 2 Intro \\#")],
    )
    def test_prefix_is_added_after_escaping(self, text: str, expected: str) -> None:
        node = HeadingNode(type="heading", level=2, text=text, heading_path=[text], **_base(), number="2")
        assert MarkdownRenderer(escape=True, heading_numbers=True).render(node) == expected
