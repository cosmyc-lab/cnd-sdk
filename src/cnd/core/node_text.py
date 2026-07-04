"""Text rendering helpers for CND manifest nodes."""

from uuid import UUID

from cnd.core.nodes import FigureNode, ListItem, ListNode, TableNode


def format_figure_placeholder(
    *,
    figure_id: UUID,
    kind: str,
    caption: str | None = None,
    number: str | None = None,
    summary: str | None = None,
) -> str:
    """Build a parseable figure placeholder for chunk content."""
    attrs: dict[str, str] = {"kind": kind}
    if number:
        attrs["number"] = number
    if caption:
        attrs["caption"] = caption
    if summary:
        attrs["summary"] = summary
    formatted = " ".join(f'{key}="{value}"' for key, value in attrs.items())
    return f"[[figure:{figure_id} {formatted}]]"


def render_list_markdown(items: list[ListItem], *, ordered: bool, depth: int = 0) -> str:
    """Render a bullet or numbered list as markdown-like text."""
    return "\n".join(_render_list_items(items, ordered, depth))


def _render_list_items(items: list[ListItem], ordered: bool, depth: int) -> list[str]:
    lines: list[str] = []
    for index, item in enumerate(items, start=1):
        prefix = f"{index}." if ordered else "-"
        indent = "  " * depth
        lines.append(f"{indent}{prefix} {item.text}")
        if item.children:
            lines.extend(_render_list_items(item.children, ordered, depth + 1))
    return lines


def table_node_placeholder(node: TableNode) -> str:
    """Placeholder string for a table or grid node."""
    return format_figure_placeholder(
        figure_id=node.id,
        kind=node.kind,
        caption=node.caption,
        number=node.fig_number,
    )


def figure_node_placeholder(node: FigureNode) -> str:
    """Placeholder string for a non-table figure node."""
    return format_figure_placeholder(
        figure_id=node.id,
        kind=node.kind or "image",
        caption=node.caption,
        number=node.fig_number,
    )
