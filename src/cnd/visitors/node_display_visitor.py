from collections import Counter
from collections.abc import Sequence

from rich.console import Console, ConsoleRenderable
from rich.padding import Padding
from rich.rule import Rule
from rich.text import Text
from rich.tree import Tree

from typing_extensions import override

from cnd.core.cnd import Cnd
from cnd.core.nodes import (
    CiteRef,
    CndNode,
    CodeNode,
    FigureNode,
    FootnoteRef,
    HeadingNode,
    ImageNode,
    ListNode,
    MathNode,
    NodeRef,
    NodeTraverseContext,
    ParagraphNode,
    QuoteNode,
    TableNode,
    TermsNode,
)
from cnd.core.node_text import render_table_markdown
from cnd.core.render import MarkdownRenderer, NodeRenderer
from cnd.display.theme import (
    NODE_STYLE,
    document_panel,
    format_node_ref,
    format_preview,
    kv_line,
    legend_panel,
    options_panel,
    pool_panel,
    print_header_grid,
    summary_panel,
    typed_panel,
)
from cnd.visitors.base_visitor import BaseVisitor, VisitTarget


def _format_links(links: Sequence[NodeRef | CiteRef | FootnoteRef]) -> str:
    """Format a link family for display, appending text spans when present."""
    parts: list[str] = []
    for link in links:
        text = format_node_ref(link.label)
        if link.text_span is not None:
            span = link.text_span
            text += f"[{span[0]}:{span[1]}]" if len(span) == 2 else str(span)
        parts.append(text)
    return ", ".join(parts)


class NodeDisplayVisitor(BaseVisitor):
    """Render a readable, colorized trace of each node while visiting a cnd.

    Text previews are produced by a ``NodeRenderer`` (composition — the
    default is a plain ``MarkdownRenderer``; pass ``renderer=`` to change
    verbosity or format).

    Example::

        NodeDisplayVisitor().visit(cnd)
        NodeDisplayVisitor(show_refs=False, truncate_text=False).visit(cnd)
    """

    def __init__(
        self,
        *,
        console: Console | None = None,
        renderer: NodeRenderer | None = None,
        max_text_len: int = 80,
        truncate_text: bool = True,
        show_fields: bool = True,
        show_refs: bool = True,
        show_location: bool = True,
        show_summary: bool = True,
        show_tree: bool = True,
        show_legend: bool = True,
        show_pools: bool = True,
    ) -> None:
        self._console = console or Console(highlight=False)
        self._renderer = renderer or MarkdownRenderer()
        self._max_text_len = max_text_len
        self._truncate_text = truncate_text
        self._show_fields = show_fields
        self._show_refs = show_refs
        self._show_location = show_location
        self._show_summary = show_summary
        self._show_tree = show_tree
        self._show_legend = show_legend
        self._show_pools = show_pools
        self._counts: Counter[str] = Counter()
        self._tree: Tree | None = None
        self._tree_stack: list[Tree] = []
        self._max_depth: int = 0
        self._refs_total: int = 0

    def _preview(self, text: str) -> str:
        return format_preview(
            text, max_len=self._max_text_len, truncate_text=self._truncate_text
        )

    @override
    def visit_heading(self, node: HeadingNode, ctx: NodeTraverseContext) -> None:
        self._counts["heading"] += 1
        title = f"H{node.level} {node.text}"
        details = {
            "number": node.number or "-",
            "children": str(len(node.children)),
        }
        self._render_node("heading", node, ctx, title, details)

    @override
    def visit_paragraph(self, node: ParagraphNode, ctx: NodeTraverseContext) -> None:
        self._counts["paragraph"] += 1
        details: dict[str, str] = {}
        if node.lang:
            details["lang"] = node.lang
        self._render_node("paragraph", node, ctx, self._preview(node.text), details)

    @override
    def visit_table(self, node: TableNode, ctx: NodeTraverseContext) -> None:
        self._counts["table"] += 1
        # Preview the actual cell content (inline pipe grid), like text nodes
        # preview their text; the label stays visible on the identity line.
        title = render_table_markdown(node) or node.label or "Table"
        details: dict[str, str] = {
            "cells": str(len(node.cells)),
            "kind": node.kind,
        }
        if node.content_kind:
            details["content_kind"] = node.content_kind
        self._render_node("table", node, ctx, self._preview(title), details)

    @override
    def visit_quote(self, node: QuoteNode, ctx: NodeTraverseContext) -> None:
        self._counts["quote"] += 1
        details: dict[str, str] = {}
        if node.attribution:
            details["attribution"] = self._preview(node.attribution)
        if node.lang:
            details["lang"] = node.lang
        self._render_node("quote", node, ctx, self._preview(node.text), details)

    @override
    def visit_code(self, node: CodeNode, ctx: NodeTraverseContext) -> None:
        self._counts["code"] += 1
        details: dict[str, str] = {}
        if node.lang:
            details["lang"] = node.lang
        self._render_node("code", node, ctx, self._preview(node.text), details)

    @override
    def visit_math(self, node: MathNode, ctx: NodeTraverseContext) -> None:
        self._counts["math"] += 1
        details: dict[str, str] = {}
        if node.number:
            details["number"] = node.number
        self._render_node("math", node, ctx, self._preview(node.text), details)

    @override
    def visit_figure(self, node: FigureNode, ctx: NodeTraverseContext) -> None:
        self._counts["figure"] += 1
        title = node.caption or node.number or node.label or "Figure"
        details: dict[str, str] = {
            "children": str(len(node.children)),
        }
        if node.kind:
            details["kind"] = node.kind
        if node.number:
            details["number"] = node.number
        if node.caption and node.caption != title:
            details["caption"] = self._preview(node.caption)
        self._render_node("figure", node, ctx, self._preview(title), details)

    @override
    def visit_image(self, node: ImageNode, ctx: NodeTraverseContext) -> None:
        self._counts["image"] += 1
        title = node.alt or node.path or node.label or "Image"
        details: dict[str, str] = {}
        if node.path:
            details["path"] = node.path
        if node.alt:
            details["alt"] = self._preview(node.alt)
        self._render_node("image", node, ctx, self._preview(title), details)

    @override
    def visit_list(self, node: ListNode, ctx: NodeTraverseContext) -> None:
        self._counts["list"] += 1
        ordered = "ordered" if node.ordered else "bullet"
        title = f"{ordered} list ({len(node.items)} items)"
        details: dict[str, str] = {
            "ordered": str(node.ordered).lower(),
            "items": str(len(node.items)),
            "tight": str(node.tight).lower(),
        }
        preview = self._preview(self._renderer.render(node))
        self._render_node("list", node, ctx, preview or title, details)

    @override
    def visit_terms(self, node: TermsNode, ctx: NodeTraverseContext) -> None:
        self._counts["terms"] += 1
        title = f"terms ({len(node.items)} items)"
        details: dict[str, str] = {
            "items": str(len(node.items)),
            "tight": str(node.tight).lower(),
        }
        preview = self._preview(self._renderer.render(node))
        self._render_node("terms", node, ctx, preview or title, details)

    @override
    def visit_unknown(self, node: CndNode, ctx: NodeTraverseContext) -> None:
        node_type = str(getattr(node, "type", type(node).__name__))
        self._counts[node_type] += 1
        self._render_node(node_type, node, ctx, node_type, {})

    @override
    def visit(
        self,
        target: VisitTarget,
        *,
        max_depth: int | None = None,
    ) -> None:
        self._counts.clear()
        self._max_depth = 0
        self._refs_total = 0
        self._tree = Tree("[bold]CND[/]", guide_style="dim") if self._show_tree else None
        self._tree_stack = [self._tree] if self._tree else []

        if isinstance(target, Cnd):
            self._print_cnd_header(target)

        self._console.print(Rule("[bold]CND tree[/]", style="bright_black"))

        super().visit(target, max_depth=max_depth)

        if self._show_tree and self._tree is not None:
            self._console.print(self._tree)

        self._console.print(Rule(style="bright_black"))

        if self._show_summary and self._counts:
            self._console.print(self._build_summary())

        if self._show_pools and isinstance(target, Cnd):
            self._print_pools(target)

    def _print_pools(self, cnd: Cnd) -> None:
        def sources(label: str) -> int:
            # incoming() already returns distinct citing nodes.
            return len(cnd.incoming(label))

        if cnd.bibliography:
            rows = [
                (
                    f"@{entry.label}",
                    self._preview(entry.formatted or entry.title or ""),
                    f"id={str(entry.id)[:8]}   cited by {sources(entry.label)}",
                )
                for entry in cnd.bibliography
            ]
            self._console.print(pool_panel("Bibliography", rows))
        if cnd.footnotes:
            rows = [
                (
                    f"@{note.label}",
                    self._preview(note.text),
                    f"id={str(note.id)[:8]}   referenced by {sources(note.label)}",
                )
                for note in cnd.footnotes
            ]
            self._console.print(pool_panel("Footnotes", rows))

    def _print_cnd_header(self, cnd: Cnd) -> None:
        panels = [
            document_panel(cnd),
            options_panel(
                "Render options",
                [
                    ("root nodes", str(len(cnd.nodes))),
                    ("bibliography", str(len(cnd.bibliography))),
                    ("footnotes", str(len(cnd.footnotes))),
                    ("truncate", "on" if self._truncate_text else "off"),
                    ("fields", "on" if self._show_fields else "off"),
                    ("tree mode", "on" if self._show_tree else "off"),
                    ("refs", "on" if self._show_refs else "off"),
                    ("location", "on" if self._show_location else "off"),
                ],
            ),
        ]
        if self._show_legend:
            panels.append(legend_panel(NODE_STYLE))
        print_header_grid(self._console, panels)

    def _render_node(
        self,
        kind: str,
        node: CndNode,
        ctx: NodeTraverseContext,
        title: str,
        details: dict[str, str],
    ) -> None:
        self._max_depth = max(self._max_depth, ctx.depth)
        self._refs_total += len(node.refs) + len(node.cites) + len(node.footnotes)

        body_parts: list[ConsoleRenderable] = []
        if title:
            body_parts.append(Text(title, style="bold white"))
            if self._show_fields:
                body_parts.append(Text(""))
        if self._show_fields:
            body_parts.extend(self._meta_lines(node, ctx, details))

        panel = typed_panel(kind, NODE_STYLE, body_parts)
        if self._show_tree and self._tree is not None:
            self._attach_to_tree(ctx.depth, panel)
            return

        indent = ctx.depth * 4
        self._console.print(Padding(panel, (0, 0, 1, indent)))

    def _attach_to_tree(
        self,
        depth: int,
        branch: ConsoleRenderable,
    ) -> None:
        assert self._tree is not None
        while len(self._tree_stack) > depth + 1:
            self._tree_stack.pop()
        parent = self._tree_stack[-1]
        child = parent.add(branch)
        self._tree_stack.append(child)

    def _meta_lines(
        self,
        node: CndNode,
        ctx: NodeTraverseContext,
        details: dict[str, str],
    ) -> list[Text]:
        lines: list[Text] = []

        parent_id = str(ctx.parent.id) if ctx.parent else "-"
        identity: list[tuple[str, str]] = [
            ("id", str(node.id)),
            ("depth", str(ctx.depth)),
            ("parent", parent_id),
        ]
        if node.label:
            identity.append(("label", node.label))
        lines.append(kv_line(identity))

        if details:
            lines.append(kv_line(list(details.items())))

        if ctx.heading_path:
            path = Text()
            path.append("path", "dim")
            path.append("  ")
            path.append(" > ".join(ctx.heading_path), "italic cyan")
            lines.append(path)

        if self._show_refs and (node.refs or node.cites or node.footnotes):
            refs = Text()
            first = True
            for name, links in (
                ("refs", node.refs),
                ("cites", node.cites),
                ("footnotes", node.footnotes),
            ):
                if not links:
                    continue
                if not first:
                    refs.append("    ")
                refs.append(name, "dim")
                refs.append("  ")
                refs.append(_format_links(links), "yellow")
                first = False
            lines.append(refs)

        if self._show_location:
            location = Text()
            location.append("loc", "dim")
            location.append("  ")
            # An unpaginated CND has no page and no page-derived position;
            # both are omitted rather than shown as a fabricated zero.
            if node.location is not None:
                location.append(f"page={node.location.page}", "bright_black")
                location.append("   ·   ", "dim")
            location.append(f"child={ctx.sibling_index}/{ctx.sibling_count}", "bright_black")
            location.append("   ·   ", "dim")
            if ctx.page_index is not None:
                location.append(
                    f"on-page={ctx.page_index}/{ctx.page_count}", "bright_black"
                )
                location.append("   ·   ", "dim")
            location.append(f"doc={ctx.doc_index}/{ctx.doc_count}", "bright_black")
            lines.append(location)

        return lines

    def _build_summary(self):
        total = sum(self._counts.values())
        return summary_panel(
            "Node summary",
            self._counts,
            NODE_STYLE,
            [
                ("Total nodes", str(total)),
                ("Node types", str(len(self._counts))),
                ("Max depth", str(self._max_depth)),
                ("Cross-refs", str(self._refs_total)),
            ],
        )
