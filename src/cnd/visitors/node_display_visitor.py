from collections import Counter

from rich.console import Console, ConsoleRenderable
from rich.padding import Padding
from rich.rule import Rule
from rich.text import Text
from rich.tree import Tree

from typing_extensions import override

from cnd.core.manifest import CndManifest
from cnd.core.nodes import (
    CndNode,
    CodeNode,
    FigureNode,
    HeadingNode,
    ListNode,
    MathNode,
    NodeTraverseContext,
    ParagraphNode,
    QuoteNode,
    TableNode,
)
from cnd.display.theme import (
    NODE_STYLE,
    document_panel,
    format_node_refs,
    format_preview,
    kv_line,
    legend_panel,
    options_panel,
    print_header_grid,
    summary_panel,
    typed_panel,
)
from cnd.visitors.base_visitor import BaseVisitor, VisitTarget


class NodeDisplayVisitor(BaseVisitor):
    """Render a readable, colorized trace of each node while visiting a manifest.

    Example::

        NodeDisplayVisitor().visit(cnd.manifest)
        NodeDisplayVisitor(show_refs=False, truncate_text=False).visit(cnd.manifest)
    """

    def __init__(
        self,
        *,
        console: Console | None = None,
        max_text_len: int = 80,
        truncate_text: bool = True,
        show_fields: bool = True,
        show_refs: bool = True,
        show_location: bool = True,
        show_summary: bool = True,
        show_tree: bool = True,
        show_legend: bool = True,
    ) -> None:
        self._console = console or Console(highlight=False)
        self._max_text_len = max_text_len
        self._truncate_text = truncate_text
        self._show_fields = show_fields
        self._show_refs = show_refs
        self._show_location = show_location
        self._show_summary = show_summary
        self._show_tree = show_tree
        self._show_legend = show_legend
        self._counts: Counter[str] = Counter()
        self._tree: Tree | None = None
        self._tree_stack: list[Tree] = []
        self._max_depth: int = 0
        self._refs_total: int = 0

    @override
    def visit_heading(self, node: HeadingNode, ctx: NodeTraverseContext) -> None:
        self._counts["heading"] += 1
        title = f"H{node.level} {node.text}"
        details = {
            "numbering": node.numbering,
            "children": str(len(node.children)),
        }
        self._render_node("heading", node, ctx, title, details)

    @override
    def visit_paragraph(self, node: ParagraphNode, ctx: NodeTraverseContext) -> None:
        self._counts["paragraph"] += 1
        details: dict[str, str] = {}
        if node.lang:
            details["lang"] = node.lang
        self._render_node(
            "paragraph",
            node,
            ctx,
            format_preview(node.text, max_len=self._max_text_len, truncate_text=self._truncate_text),
            details,
        )

    @override
    def visit_table(self, node: TableNode, ctx: NodeTraverseContext) -> None:
        self._counts["table"] += 1
        title = node.caption or node.fig_number or node.label or "Table"
        details: dict[str, str] = {
            "cells": str(len(node.cells)),
            "kind": node.kind,
        }
        if node.fig_number:
            details["fig_number"] = node.fig_number
        if node.caption and node.caption != title:
            details["caption"] = format_preview(
                node.caption, max_len=self._max_text_len, truncate_text=self._truncate_text
            )
        self._render_node(
            "table",
            node,
            ctx,
            format_preview(title, max_len=self._max_text_len, truncate_text=self._truncate_text),
            details,
        )

    @override
    def visit_quote(self, node: QuoteNode, ctx: NodeTraverseContext) -> None:
        self._counts["quote"] += 1
        details: dict[str, str] = {}
        if node.attribution:
            details["attribution"] = format_preview(
                node.attribution,
                max_len=self._max_text_len,
                truncate_text=self._truncate_text,
            )
        if node.lang:
            details["lang"] = node.lang
        self._render_node(
            "quote",
            node,
            ctx,
            format_preview(node.text, max_len=self._max_text_len, truncate_text=self._truncate_text),
            details,
        )

    @override
    def visit_code(self, node: CodeNode, ctx: NodeTraverseContext) -> None:
        self._counts["code"] += 1
        details: dict[str, str] = {}
        if node.lang:
            details["lang"] = node.lang
        self._render_node(
            "code",
            node,
            ctx,
            format_preview(node.text, max_len=self._max_text_len, truncate_text=self._truncate_text),
            details,
        )

    @override
    def visit_math(self, node: MathNode, ctx: NodeTraverseContext) -> None:
        self._counts["math"] += 1
        details: dict[str, str] = {}
        if node.numbering:
            details["numbering"] = node.numbering
        self._render_node(
            "math",
            node,
            ctx,
            format_preview(node.text, max_len=self._max_text_len, truncate_text=self._truncate_text),
            details,
        )

    @override
    def visit_figure(self, node: FigureNode, ctx: NodeTraverseContext) -> None:
        self._counts["figure"] += 1
        title = node.caption or node.fig_number or node.label or "Figure"
        details: dict[str, str] = {}
        if node.kind:
            details["kind"] = node.kind
        if node.fig_number:
            details["fig_number"] = node.fig_number
        if node.alt:
            details["alt"] = format_preview(
                node.alt, max_len=self._max_text_len, truncate_text=self._truncate_text
            )
        if node.path:
            details["path"] = node.path
        self._render_node(
            "figure",
            node,
            ctx,
            format_preview(title, max_len=self._max_text_len, truncate_text=self._truncate_text),
            details,
        )

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
        preview = format_preview(
            node.to_text(), max_len=self._max_text_len, truncate_text=self._truncate_text
        )
        self._render_node("list", node, ctx, preview or title, details)

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
        self._tree = Tree("[bold]CND Manifest[/]", guide_style="dim") if self._show_tree else None
        self._tree_stack = [self._tree] if self._tree else []

        if isinstance(target, CndManifest):
            self._print_manifest_header(target)

        self._console.print(Rule("[bold]Manifest tree[/]", style="bright_black"))

        super().visit(target, max_depth=max_depth)

        if self._show_tree and self._tree is not None:
            self._console.print(self._tree)

        self._console.print(Rule(style="bright_black"))

        if self._show_summary and self._counts:
            self._console.print(self._build_summary())

    def _print_manifest_header(self, manifest: CndManifest) -> None:
        panels = [
            document_panel(manifest),
            options_panel(
                "Render options",
                [
                    ("root nodes", str(len(manifest.nodes))),
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
        self._refs_total += len(node.refs_to) + len(node.refs_from)

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

        if self._show_refs and (node.refs_to or node.refs_from):
            refs = Text()
            if node.refs_to:
                refs.append("refs_to", "dim")
                refs.append("  ")
                refs.append(format_node_refs(node.refs_to), "yellow")
            if node.refs_from:
                if node.refs_to:
                    refs.append("    ")
                refs.append("refs_from", "dim")
                refs.append("  ")
                refs.append(format_node_refs(node.refs_from), "yellow")
            lines.append(refs)

        if self._show_location:
            loc = node.location
            location = Text()
            location.append("loc", "dim")
            location.append("  ")
            location.append(f"page={loc.page}", "bright_black")
            location.append("   ·   ", "dim")
            location.append(f"span={loc.span}", "bright_black")
            location.append("   ·   ", "dim")
            location.append(f"page_span={loc.page_span}", "bright_black")
            location.append("   ·   ", "dim")
            location.append(f"parent_span={loc.parent_span}", "bright_black")
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
