from uuid import UUID
from typing import Annotated, Any, Literal, Union
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field

from pydantic import BaseModel, Field

from cnd.core.text import (  # noqa: F401  (re-exported for existing imports)
    CiteRef,
    Edge,
    FootnoteRef,
    LinkRef,
    NodeRef,
    Numbering,
    RawSource,
    RichText,
)


class NodeLocation(BaseModel):
    """Layout facts the SDK cannot derive from the tree: the page where the
    node begins in the built document.

    Nullable, because a page only exists for a paginated source. Pagination
    is all-or-nothing across a CND — either every node carries a location or
    none does — so ``location`` never encodes "unknown page" (docs/adr/0012,
    docs/proposals/0008). Whether a CND is paginated is itself derived, not
    serialized: see ``Cnd.paginated``.

    Positions in reading order (document/sibling/page index and totals) are
    NOT serialized — the node tree is normatively in reading order, so the
    SDK derives them during traversal (see ``NodeTraverseContext``), the
    same way reverse reference edges are derived (docs/adr/0008).
    """

    page: int


KNOWN_ADMONITION_KINDS = frozenset({"note", "tip", "important", "warning", "caution"})
"""Known ``admonition.kind`` values (open vocabulary; fallback: a generic
callout headed by the title, or by the kind)."""

KNOWN_TABLE_KINDS = frozenset({"data", "content"})
"""Known ``table.kind`` values (open vocabulary; ``None`` = unstated)."""


class NodeBase(BaseModel):
    """Shared fields for every node. The link families live in the node's
    texts (``RichText``), not here (docs/proposals/0013)."""

    id: UUID
    label: str | None = None
    state_metadata: dict[str, Any] = Field(default_factory=dict)
    location: NodeLocation | None = None


class HeadingNode(NodeBase):
    """Section heading; the section's content is in ``children``."""

    type: Literal["heading"]
    level: int
    numbering: Numbering | None = None
    text: RichText
    heading_path: list[str]
    children: list["CndNode"] = Field(default_factory=list)


class ParagraphNode(NodeBase):
    """A paragraph: the leaf that carries prose."""

    type: Literal["paragraph"]
    text: RichText


class QuoteNode(NodeBase):
    """Block quotation. An inline quotation stays text in its paragraph."""

    type: Literal["quote"]
    attribution: RichText | None = None
    children: list["CndNode"] = Field(default_factory=list)


class CodeNode(NodeBase):
    """Code block, verbatim. Inline code is a ``code`` mark. ``title`` is
    the label an author gives a listing, typically a file name."""

    type: Literal["code"]
    text: str
    lang: str | None = None
    title: str | None = None


class MathNode(NodeBase):
    """Block equation. Inline math is a ``math`` mark."""

    type: Literal["math"]
    text: str
    raw: RawSource | None = None
    numbering: Numbering | None = None


class ImageNode(NodeBase):
    """Leaf image content."""

    type: Literal["image"]
    path: str | None = None
    alt: str | None = None


class FigureNode(NodeBase):
    """Captioned/numbered wrapper; content keeps its own node type in
    ``children``. ``kind`` is the figure's category (open vocabulary),
    useful above all for author-defined categories ``children`` cannot
    reveal. ``description`` is the text equivalent of the visual. An
    unconvertible body (a drawing) yields ``children=[]`` with ``raw``."""

    type: Literal["figure"]
    kind: str | None = None
    caption: RichText | None = None
    description: RichText | None = None
    numbering: Numbering | None = None
    children: list["CndNode"] = Field(default_factory=list)
    raw: RawSource | None = None


class AdmonitionNode(NodeBase):
    """A callout ("Note", "Warning"). ``kind`` is an open vocabulary; the
    known values are ``KNOWN_ADMONITION_KINDS``."""

    type: Literal["admonition"]
    kind: str
    title: RichText | None = None
    children: list["CndNode"] = Field(default_factory=list)


class ListItem(BaseModel):
    """One list entry. Its content is block nodes; a nested list is a
    ``list`` node with its own ``ordered``. ``checked`` is ``None`` for an
    item that is not a task-list checkbox."""

    number: int | None = None
    checked: bool | None = None
    children: list["CndNode"] = Field(default_factory=list)


class ListNode(NodeBase):
    """Bullet (``ordered=False``) or numbered (``ordered=True``) list."""

    type: Literal["list"]
    ordered: bool = False
    items: list[ListItem] = Field(default_factory=list)


class TermItem(BaseModel):
    """One term and its definition (block nodes in ``children``)."""

    term: RichText
    children: list["CndNode"] = Field(default_factory=list)


class TermsNode(NodeBase):
    """Definition list."""

    type: Literal["terms"]
    items: list[TermItem] = Field(default_factory=list)


class Cell(BaseModel):
    """One cell of a ``table`` or a ``layout``; content is block nodes."""

    row: int
    col: int
    rowspan: int = 1
    colspan: int = 1
    is_header: bool = False
    children: list["CndNode"] = Field(default_factory=list)


class TableNode(NodeBase):
    """A table whose rows and columns carry meaning. ``kind`` states what
    it is: ``"data"`` (a dataset of records), ``"content"`` (cells to
    read), ``None`` (unstated). Open vocabulary; never guessed by a
    producer. A captioned table is wrapped in a ``FigureNode``."""

    type: Literal["table"]
    kind: str | None = None
    cells: list[Cell] = Field(default_factory=list)


class LayoutNode(NodeBase):
    """A grid used for arrangement only; position carries no relation."""

    type: Literal["layout"]
    cells: list[Cell] = Field(default_factory=list)


CndNode = Annotated[
    Union[
        HeadingNode,
        ParagraphNode,
        QuoteNode,
        CodeNode,
        MathNode,
        ImageNode,
        FigureNode,
        AdmonitionNode,
        ListNode,
        TermsNode,
        TableNode,
        LayoutNode,
    ],
    Field(discriminator="type"),
]

for _model in (HeadingNode, QuoteNode, FigureNode, AdmonitionNode, ListItem, TermItem, Cell):
    _model.model_rebuild()


def texts_of(node: "CndNode") -> list[RichText]:
    """The node's own texts, in document order; never a nested node's."""
    if isinstance(node, (HeadingNode, ParagraphNode)):
        return [node.text]
    if isinstance(node, QuoteNode):
        return [node.attribution] if node.attribution is not None else []
    if isinstance(node, FigureNode):
        return [t for t in (node.caption, node.description) if t is not None]
    if isinstance(node, AdmonitionNode):
        return [node.title] if node.title is not None else []
    if isinstance(node, TermsNode):
        return [item.term for item in node.items]
    return []


def edges_of(node: "CndNode") -> list[Edge]:
    """Every forward edge of the node's own texts, flattened."""
    return [edge for text in texts_of(node) for edge in text.edges()]




@dataclass(frozen=True)
class NodeTraverseContext:
    """Traversal state passed to visitor hooks for the current node.

    The position attributes are derived by the traversal engine from the
    normative reading order of the tree (all 1-based, ``index``/``count``
    pairs suitable for an "x/y" display):

    - ``doc_index``/``doc_count`` — position among all nodes of the walk.
    - ``sibling_index``/``sibling_count`` — position among the siblings
      of the same slot list.
    - ``page_index``/``page_count`` — position among the nodes that begin
      on the same page (``location.page``). Both are ``None`` on an
      unpaginated CND, where no page exists to be positioned within — the
      page-derived positions are undefined, not zero
      (docs/proposals/0008).

    They are document facts, not walk artifacts: pruning a branch with
    ``max_depth``/``stop_predicate`` does not shift the positions of the
    nodes that are still visited.

    - ``slot``/``slot_index`` — where the node's list sits in its parent:
      ``"children"`` (index ``None``), ``"items"`` or ``"cells"`` with the
      entry index, ``"footnotes"`` with the pool index, ``None`` at the top
      level.
    - ``path`` — the node's full position, e.g.
      ``("nodes", 0, "children", 4, "cells", 2, "children", 0)``. It feeds
      the document hash (§10).
    """

    depth: int
    heading_path: list[str]
    parent: CndNode | None = None
    doc_index: int = 0
    doc_count: int = 0
    sibling_index: int = 0
    sibling_count: int = 0
    page_index: int | None = None
    page_count: int | None = None
    slot: str | None = None
    slot_index: int | None = None
    path: tuple[str | int, ...] = ()


@dataclass(frozen=True)
class NodeTraverse:
    """A node paired with its traversal context."""

    node: CndNode
    ctx: NodeTraverseContext


StopPredicate = Callable[[CndNode, NodeTraverseContext], bool]


@dataclass(frozen=True)
class ChildSlot:
    """One list of nested nodes inside a container, and where it sits:
    ``field`` is ``"children"``, ``"items"`` or ``"cells"``; ``index`` is
    the item or cell index (``None`` for ``"children"``)."""

    field: str
    index: int | None
    nodes: list["CndNode"]


def child_slots(node: "CndNode") -> list[ChildSlot]:
    """Every nested-node list of ``node``, in document order (principle 2:
    nested nodes always live in ``children``)."""
    if isinstance(node, (HeadingNode, FigureNode, QuoteNode, AdmonitionNode)):
        return [ChildSlot("children", None, node.children)]
    if isinstance(node, (ListNode, TermsNode)):
        return [ChildSlot("items", i, item.children) for i, item in enumerate(node.items)]
    if isinstance(node, (TableNode, LayoutNode)):
        return [ChildSlot("cells", i, cell.children) for i, cell in enumerate(node.cells)]
    return []


def _children_of(node: "CndNode") -> list["CndNode"]:
    """All nested nodes of ``node``, every slot flattened in order."""
    return [child for slot in child_slots(node) for child in slot.nodes]


def position_totals(nodes: list[CndNode]) -> tuple[int, dict[int, int]]:
    """One cheap pre-pass over the tree: total node count and per-page
    node counts (keyed on ``location.page``). Feeds the ``*_count``
    attributes of ``NodeTraverseContext``.

    On an unpaginated CND no node carries a location, so ``page_counts``
    comes back empty and the page-derived positions stay undefined.
    """
    doc_count = 0
    page_counts: dict[int, int] = {}
    stack = list(reversed(nodes))
    while stack:
        node = stack.pop()
        doc_count += 1
        if node.location is not None:
            page = node.location.page
            page_counts[page] = page_counts.get(page, 0) + 1
        stack.extend(reversed(_children_of(node)))
    return doc_count, page_counts


@dataclass
class _WalkCounters:
    """Mutable reading-order counters shared across the recursive walk."""

    doc_index: int = 0
    page_indices: dict[int, int] = field(default_factory=dict)

    def advance(self, node: CndNode) -> tuple[int, int | None]:
        """Count ``node`` and return its (doc_index, page_index); the page
        index is ``None`` for a node with no location."""
        self.doc_index += 1
        if node.location is None:
            return self.doc_index, None
        page = node.location.page
        self.page_indices[page] = self.page_indices.get(page, 0) + 1
        return self.doc_index, self.page_indices[page]

    def skip_subtree(self, nodes: list[CndNode]) -> None:
        """Advance past a pruned subtree without yielding it, so positions
        stay document-true for the nodes visited after it."""
        stack = list(nodes)
        while stack:
            node = stack.pop()
            self.advance(node)
            stack.extend(_children_of(node))


def iter_nodes(
    nodes: list[CndNode],
    *,
    max_depth: int | None = None,
    stop_predicate: StopPredicate | None = None,
    _totals: tuple[int, dict[int, int]] | None = None,
    _base_path: tuple[str | int, ...] = ("nodes",),
    _slot: str | None = None,
    _slot_index: int | None = None,
) -> Iterator[NodeTraverse]:
    """Walk a node tree depth-first in reading order, entering every
    container, yielding each node with its context.

    The tree is normatively in document reading order, so the walk order is
    reading order and the derived position attributes on the context are
    document positions. ``_totals`` lets a caller (``Cnd.iter``)
    reuse a cached ``position_totals`` result.
    """
    totals = _totals if _totals is not None else position_totals(nodes)
    root_ctx = NodeTraverseContext(
        depth=0, heading_path=[], parent=None, slot=_slot, slot_index=_slot_index
    )
    yield from _iter_nodes(
        nodes, root_ctx, max_depth, stop_predicate, totals, _WalkCounters(), _base_path
    )


def _iter_nodes(nodes, ctx, max_depth, stop_predicate, totals, counters, base_path):
    doc_count, page_counts = totals
    for sibling_index, node in enumerate(nodes, start=1):
        doc_index, page_index = counters.advance(node)
        visit_ctx = NodeTraverseContext(
            depth=ctx.depth,
            heading_path=ctx.heading_path,
            parent=ctx.parent,
            doc_index=doc_index,
            doc_count=doc_count,
            sibling_index=sibling_index,
            sibling_count=len(nodes),
            page_index=page_index,
            page_count=(
                page_counts[node.location.page] if node.location is not None else None
            ),
            slot=ctx.slot,
            slot_index=ctx.slot_index,
            path=(*base_path, sibling_index - 1),
        )
        yield NodeTraverse(node=node, ctx=visit_ctx)

        slots = [slot for slot in child_slots(node) if slot.nodes]
        if not slots:
            continue
        if (max_depth is not None and ctx.depth >= max_depth) or (
            stop_predicate is not None and stop_predicate(node, visit_ctx)
        ):
            counters.skip_subtree(_children_of(node))
            continue

        heading_path = (
            node.heading_path if isinstance(node, HeadingNode) else ctx.heading_path
        )
        for slot in slots:
            child_ctx = NodeTraverseContext(
                depth=ctx.depth + 1,
                heading_path=heading_path,
                parent=node,
                slot=slot.field,
                slot_index=slot.index,
            )
            prefix = (
                (*visit_ctx.path, slot.field)
                if slot.index is None
                else (*visit_ctx.path, slot.field, slot.index, "children")
            )
            yield from _iter_nodes(
                slot.nodes, child_ctx, max_depth, stop_predicate, totals, counters, prefix
            )
