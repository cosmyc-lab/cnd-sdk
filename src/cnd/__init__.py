"""CND — the Context Native Document standard.

Core parsing (``CndManifest`` and node types) has no optional dependencies.
Display helpers (``cnd.display``, ``cnd.visitors.node_display_visitor``)
require the ``display`` extra: ``pip install cnd-sdk[display]``.
"""

from cnd.core import (
    CndManifest,
    CndNode,
    CodeNode,
    DocDate,
    DocMetadata,
    FigureNode,
    HeadingNode,
    ListItem,
    ListNode,
    MathNode,
    NodeBase,
    NodeLocation,
    NodeRef,
    NodeTraverse,
    NodeTraverseContext,
    ParagraphNode,
    QuoteNode,
    StopPredicate,
    TableCell,
    TableNode,
    iter_nodes,
)
from cnd.visitors import BaseVisitor, VisitTarget

__all__ = [
    "BaseVisitor",
    "CndManifest",
    "CndNode",
    "CodeNode",
    "DocDate",
    "DocMetadata",
    "FigureNode",
    "HeadingNode",
    "ListItem",
    "ListNode",
    "MathNode",
    "NodeBase",
    "NodeLocation",
    "NodeRef",
    "NodeTraverse",
    "NodeTraverseContext",
    "ParagraphNode",
    "QuoteNode",
    "StopPredicate",
    "TableCell",
    "TableNode",
    "VisitTarget",
    "iter_nodes",
]
