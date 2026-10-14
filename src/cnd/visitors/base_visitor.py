from cnd.core.cnd import Cnd
from cnd.core.nodes import (
    AdmonitionNode,
    CndNode,
    CodeNode,
    FigureNode,
    HeadingNode,
    ImageNode,
    LayoutNode,
    ListNode,
    MathNode,
    NodeTraverseContext,
    ParagraphNode,
    QuoteNode,
    TableNode,
    TermsNode,
    iter_nodes,
)

VisitTarget = Cnd | list[CndNode]


class BaseVisitor:
    """Visit a CND node tree with overridable per-type hooks.

    Override ``visit_*`` for node logic and ``should_stop_descent`` to prune
    branches. All hooks are no-ops by default; there is one per node type,
    ``visit_<type>``.

    The walk is the body walk (spec §8) by default: it enters every
    container — list and term items, table and layout cells, quotes,
    admonitions, figures — so a paragraph inside a cell reaches
    ``visit_paragraph`` with the table as its ``ctx.parent``. Footnote
    content is not part of the body; ``visit(cnd, full=True)`` runs the full
    walk instead (``Cnd.iter_all``): the body, then each footnote's content,
    with spec §8 paths (``("footnotes", 0, "children", 0)``) and ``slot``
    ``"footnotes"``. Do not walk ``cnd.footnotes[i].children`` by hand: its
    paths would start at ``("nodes", 0)`` and name a body node.

    During traversal, ``current_node`` and ``current_ctx`` hold the node and
    context being visited.
    """

    current_node: CndNode | None
    current_ctx: NodeTraverseContext | None

    def visit(
        self,
        target: VisitTarget,
        *,
        max_depth: int | None = None,
        full: bool = False,
    ) -> None:
        """Traverse ``target`` and dispatch to per-type hooks.

        ``full=True`` runs the full walk of a ``Cnd`` (the body, then each
        footnote's content); it needs a ``Cnd``, since a bare node list has
        no footnotes.
        """
        self.current_node = None
        self.current_ctx = None
        if full:
            if not isinstance(target, Cnd):
                raise ValueError("full=True walks a Cnd's footnotes; pass a Cnd")
            steps = target.iter_all(
                max_depth=max_depth, stop_predicate=self.should_stop_descent
            )
        else:
            nodes = target.nodes if isinstance(target, Cnd) else target
            steps = iter_nodes(
                nodes,
                max_depth=max_depth,
                stop_predicate=self.should_stop_descent,
            )
        for step in steps:
            self._dispatch(step.node, step.ctx)

    def should_stop_descent(
        self,
        node: CndNode,
        ctx: NodeTraverseContext,
    ) -> bool:
        """Return ``True`` to skip visiting the children of ``node``."""
        return False

    def _dispatch(self, node: CndNode, ctx: NodeTraverseContext) -> None:
        self.current_node = node
        self.current_ctx = ctx
        if isinstance(node, HeadingNode):
            self.visit_heading(node, ctx)
        elif isinstance(node, ParagraphNode):
            self.visit_paragraph(node, ctx)
        elif isinstance(node, TableNode):
            self.visit_table(node, ctx)
        elif isinstance(node, QuoteNode):
            self.visit_quote(node, ctx)
        elif isinstance(node, CodeNode):
            self.visit_code(node, ctx)
        elif isinstance(node, MathNode):
            self.visit_math(node, ctx)
        elif isinstance(node, FigureNode):
            self.visit_figure(node, ctx)
        elif isinstance(node, ImageNode):
            self.visit_image(node, ctx)
        elif isinstance(node, ListNode):
            self.visit_list(node, ctx)
        elif isinstance(node, TermsNode):
            self.visit_terms(node, ctx)
        elif isinstance(node, AdmonitionNode):
            self.visit_admonition(node, ctx)
        elif isinstance(node, LayoutNode):
            self.visit_layout(node, ctx)
        else:
            self.visit_unknown(node, ctx)

    def visit_heading(self, node: HeadingNode, ctx: NodeTraverseContext) -> None:
        pass

    def visit_paragraph(self, node: ParagraphNode, ctx: NodeTraverseContext) -> None:
        pass

    def visit_table(self, node: TableNode, ctx: NodeTraverseContext) -> None:
        pass

    def visit_quote(self, node: QuoteNode, ctx: NodeTraverseContext) -> None:
        pass

    def visit_code(self, node: CodeNode, ctx: NodeTraverseContext) -> None:
        pass

    def visit_math(self, node: MathNode, ctx: NodeTraverseContext) -> None:
        pass

    def visit_figure(self, node: FigureNode, ctx: NodeTraverseContext) -> None:
        pass

    def visit_image(self, node: ImageNode, ctx: NodeTraverseContext) -> None:
        pass

    def visit_list(self, node: ListNode, ctx: NodeTraverseContext) -> None:
        pass

    def visit_terms(self, node: TermsNode, ctx: NodeTraverseContext) -> None:
        pass

    def visit_admonition(self, node: AdmonitionNode, ctx: NodeTraverseContext) -> None:
        pass

    def visit_layout(self, node: LayoutNode, ctx: NodeTraverseContext) -> None:
        pass

    def visit_unknown(self, node: CndNode, ctx: NodeTraverseContext) -> None:
        raise NotImplementedError(f"Unknown node type: {type(node).__name__}")
