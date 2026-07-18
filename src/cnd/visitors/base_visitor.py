from cnd.core.manifest import CndManifest
from cnd.core.nodes import (
    CndNode,
    CodeNode,
    FigureNode,
    HeadingNode,
    ImageNode,
    ListNode,
    MathNode,
    NodeTraverseContext,
    ParagraphNode,
    QuoteNode,
    TableNode,
    TermsNode,
    iter_nodes,
)

VisitTarget = CndManifest | list[CndNode]


class BaseVisitor:
    """Visit a manifest node tree with overridable per-type hooks.

    Override ``visit_*`` for node logic and ``should_stop_descent`` to prune
    branches. All hooks are no-ops by default.

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
    ) -> None:
        """Traverse ``target`` and dispatch to per-type hooks."""
        self.current_node = None
        self.current_ctx = None
        nodes = target.nodes if isinstance(target, CndManifest) else target
        for step in iter_nodes(
            nodes,
            max_depth=max_depth,
            stop_predicate=self.should_stop_descent,
        ):
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

    def visit_unknown(self, node: CndNode, ctx: NodeTraverseContext) -> None:
        raise NotImplementedError(f"Unknown node type: {type(node).__name__}")
