from uuid import uuid4

from cnd.core.node_text import format_figure_placeholder, render_list_markdown
from cnd.core.nodes import (
    CodeNode,
    FigureNode,
    ListItem,
    ListNode,
    MathNode,
    NodeLocation,
    ParagraphNode,
    QuoteNode,
    TableCell,
    TableNode,
)


def _location(span: int = 0) -> NodeLocation:
    return NodeLocation(
        page=1,
        span=span,
        page_span=span,
        parent_span=0,
        span_count=1,
    )


def _base(**kwargs):
    defaults = {
        "id": uuid4(),
        "location": _location(),
    }
    defaults.update(kwargs)
    return defaults


class TestNodeToText:
    def test_paragraph_to_text(self) -> None:
        node = ParagraphNode(type="paragraph", text="Hello world", **_base())
        assert node.to_text() == "Hello world"

    def test_quote_to_text_with_attribution(self) -> None:
        node = QuoteNode(
            type="quote",
            text="Programs must be written for people to read.",
            attribution="Ada Lovelace",
            **_base(),
        )
        assert node.to_text() == (
            "Programs must be written for people to read.\n— Ada Lovelace"
        )

    def test_code_to_text(self) -> None:
        node = CodeNode(
            type="code",
            text="print('hi')",
            lang="python",
            **_base(),
        )
        assert node.to_text() == "```python\nprint('hi')\n```"

    def test_math_to_text(self) -> None:
        node = MathNode(type="math", text="E = m c^2", **_base())
        assert node.to_text() == "E = m c^2"

    def test_list_to_text(self) -> None:
        node = ListNode(
            type="list",
            ordered=False,
            items=[
                ListItem(text="Alpha"),
                ListItem(text="Beta"),
            ],
            **_base(),
        )
        assert node.to_text() == "- Alpha\n- Beta"

    def test_table_placeholder_uses_kind(self) -> None:
        node = TableNode(
            type="table",
            kind="grid",
            caption="A grid",
            fig_number="Figure 2",
            cells=[TableCell(row=0, col=0, text="A")],
            **_base(),
        )
        text = node.to_text()
        assert 'kind="grid"' in text
        assert 'caption="A grid"' in text

    def test_figure_placeholder(self) -> None:
        node = FigureNode(
            type="figure",
            kind="image",
            caption="Diagram",
            fig_number="Figure 1",
            **_base(),
        )
        text = node.to_text()
        assert 'kind="image"' in text
        assert 'caption="Diagram"' in text


class TestNodeTextHelpers:
    def test_render_list_markdown_nested(self) -> None:
        items = [
            ListItem(
                text="Parent",
                children=[ListItem(text="Child")],
            )
        ]
        assert render_list_markdown(items, ordered=True) == "1. Parent\n  1. Child"

    def test_format_figure_placeholder(self) -> None:
        figure_id = uuid4()
        placeholder = format_figure_placeholder(
            figure_id=figure_id,
            kind="grid",
            caption="Layout",
            number="Figure 3",
        )
        assert str(figure_id) in placeholder
        assert 'kind="grid"' in placeholder
