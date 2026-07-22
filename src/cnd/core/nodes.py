from uuid import UUID
from typing import Annotated, Any, Literal, Union
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field

from pydantic import BaseModel, Field


class NodeLocation(BaseModel):
    """Layout facts the SDK cannot derive from the tree: the page where the
    node begins in the compiled document.

    Positions in reading order (document/sibling/page index and totals) are
    NOT serialized — the node tree is normatively in reading order, so the
    SDK derives them during traversal (see ``NodeTraverseContext``), the
    same way reverse reference edges are derived (docs/adr/0008).
    """

    page: int


class NodeRef(BaseModel):
    """Forward cross-reference edge to another node.

    Canonical shape is ``{id, label}`` (docs/adr/0002); ``text_span`` is an
    additive optional field marking where the reference marker sits in the
    containing node's rendered text, as a ``[start, end)`` pair of Unicode
    code-point offsets (docs/adr/0013).
    """

    id: UUID
    label: str | None = None
    text_span: list[int] | None = None


class CiteRef(BaseModel):
    """Forward citation edge; ``id`` resolves in the CND ``bibliography`` pool."""

    id: UUID
    label: str | None = None
    text_span: list[int] | None = None
    form: Literal["normal", "prose", "full", "author", "year", "none"] | None = None
    supplement: str | None = None


class FootnoteRef(BaseModel):
    """Forward footnote edge; ``id`` resolves in the CND ``footnotes`` pool."""

    id: UUID
    label: str | None = None
    text_span: list[int] | None = None


class NodeBase(BaseModel):
    """Shared fields for every cnd node."""

    id: UUID
    label: str | None = None
    refs: list[NodeRef] = Field(default_factory=list)
    cites: list[CiteRef] = Field(default_factory=list)
    footnotes: list[FootnoteRef] = Field(default_factory=list)
    state_metadata: dict[str, Any] = Field(default_factory=dict)
    location: NodeLocation


class HeadingNode(NodeBase):
    """Section heading with nested section content in ``children``."""

    type: Literal["heading"]
    level: int
    numbering: str
    text: str
    heading_path: list[str]
    children: list["CndNode"] = Field(default_factory=list)


class ParagraphNode(NodeBase):
    """Plain text paragraph."""

    type: Literal["paragraph"]
    text: str
    lang: str | None = None


class TableCell(BaseModel):
    """Single cell inside a table node."""

    row: int
    col: int
    rowspan: int = 1
    colspan: int = 1
    is_header: bool = False
    text: str


class TableNode(NodeBase):
    """Structured table with typed cells.

    ``kind`` distinguishes a semantic ``table`` from a layout ``grid``: both
    share the same cell model, but a grid carries no tabular semantics.

    A table has no caption of its own — a captioned/numbered table is a
    ``TableNode`` wrapped in a ``FigureNode``, which carries the caption.
    """

    type: Literal["table"]
    kind: Literal["table", "grid"] = "table"
    # Optional producer-supplied hint used by mode="auto" rendering (see
    # cnd.core.render.MarkdownRenderer): "content" for a table whose cells
    # read fine inlined as text (a short comparison table, a parameter
    # list), "data" for one that doesn't (a numeric measurement grid).
    # Unset (the common case today) is treated as "data".
    content_kind: Literal["data", "content"] | None = None
    cells: list[TableCell] = Field(default_factory=list)
    raw_typst: str | None = None


class QuoteNode(NodeBase):
    """Block quotation with optional attribution (author or source)."""

    type: Literal["quote"]
    text: str
    attribution: str | None = None
    block: bool = True
    lang: str | None = None


class CodeNode(NodeBase):
    """Raw code block, preserved verbatim with its language tag."""

    type: Literal["code"]
    text: str
    lang: str | None = None
    block: bool = True


class MathNode(NodeBase):
    """Block-level equation."""

    type: Literal["math"]
    text: str
    raw_typst: str | None = None
    numbering: str | None = None
    block: bool = True


class ImageNode(NodeBase):
    """Leaf image content. A bare image outside any figure is an ``ImageNode``
    with no wrapper; a captioned image is an ``ImageNode`` inside a
    ``FigureNode``."""

    type: Literal["image"]
    path: str | None = None
    alt: str | None = None


class FigureNode(NodeBase):
    """Captioned/numbered float wrapper — never a content carrier.

    The wrapped content (image, table, code, …) lives in ``children`` and
    keeps its own node type and ``location``. ``kind`` is the counter/label
    selector of the figure ("image", "table", or an author-custom kind like
    "atom") — an open string, never a content discriminator. Nested figures
    (subfigures) are allowed. An unconvertible body yields ``children=[]``
    with ``raw_typst`` filled.
    """

    type: Literal["figure"]
    kind: str | None = None
    caption: str | None = None
    fig_number: str | None = None
    children: list["CndNode"] = Field(default_factory=list)
    raw_typst: str | None = None


class ListItem(BaseModel):
    """Single item of a bullet or numbered list."""

    text: str
    number: int | None = None
    children: list["ListItem"] = Field(default_factory=list)


class ListNode(NodeBase):
    """Bullet (`ordered=False`) or numbered (`ordered=True`) list."""

    type: Literal["list"]
    ordered: bool = False
    tight: bool = True
    items: list[ListItem] = Field(default_factory=list)


class TermItem(BaseModel):
    """Single term/description pair of a definition list."""

    term: str
    description: str


class TermsNode(NodeBase):
    """Definition list (Typst ``/ term: description`` items)."""

    type: Literal["terms"]
    tight: bool = True
    items: list[TermItem] = Field(default_factory=list)


CndNode = Annotated[
    Union[
        HeadingNode,
        ParagraphNode,
        TableNode,
        QuoteNode,
        CodeNode,
        MathNode,
        FigureNode,
        ImageNode,
        ListNode,
        TermsNode,
    ],
    Field(discriminator="type"),
]

ListItem.model_rebuild()

HeadingNode.model_rebuild()  # For recursive reference to children
FigureNode.model_rebuild()  # For recursive reference to children


@dataclass(frozen=True)
class NodeTraverseContext:
    """Traversal state passed to visitor hooks for the current node.

    The position attributes are derived by the traversal engine from the
    normative reading order of the tree (all 1-based, ``index``/``count``
    pairs suitable for an "x/y" display):

    - ``doc_index``/``doc_count`` — position among all nodes of the walk.
    - ``sibling_index``/``sibling_count`` — position among the parent's
      children.
    - ``page_index``/``page_count`` — position among the nodes that begin
      on the same page (``location.page``).

    They are document facts, not walk artifacts: pruning a branch with
    ``max_depth``/``stop_predicate`` does not shift the positions of the
    nodes that are still visited.
    """

    depth: int
    heading_path: list[str]
    parent: CndNode | None = None
    doc_index: int = 0
    doc_count: int = 0
    sibling_index: int = 0
    sibling_count: int = 0
    page_index: int = 0
    page_count: int = 0


@dataclass(frozen=True)
class NodeTraverse:
    """A node paired with its traversal context."""

    node: CndNode
    ctx: NodeTraverseContext


StopPredicate = Callable[[CndNode, NodeTraverseContext], bool]


def _children_of(node: CndNode) -> list["CndNode"]:
    """The child list of a children-bearing node (heading, figure)."""
    if isinstance(node, (HeadingNode, FigureNode)):
        return node.children
    return []


def position_totals(nodes: list[CndNode]) -> tuple[int, dict[int, int]]:
    """One cheap pre-pass over the tree: total node count and per-page
    node counts (keyed on ``location.page``). Feeds the ``*_count``
    attributes of ``NodeTraverseContext``."""
    doc_count = 0
    page_counts: dict[int, int] = {}
    stack = list(reversed(nodes))
    while stack:
        node = stack.pop()
        doc_count += 1
        page = node.location.page
        page_counts[page] = page_counts.get(page, 0) + 1
        stack.extend(reversed(_children_of(node)))
    return doc_count, page_counts


@dataclass
class _WalkCounters:
    """Mutable reading-order counters shared across the recursive walk."""

    doc_index: int = 0
    page_indices: dict[int, int] = field(default_factory=dict)

    def advance(self, node: CndNode) -> tuple[int, int]:
        """Count ``node`` and return its (doc_index, page_index)."""
        self.doc_index += 1
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
) -> Iterator[NodeTraverse]:
    """Walk a node tree depth-first, yielding each node with its context.

    The tree is normatively in document reading order, so the walk order is
    reading order and the derived position attributes on the context are
    document positions. ``_totals`` lets a caller (``Cnd.iter``)
    reuse a cached ``position_totals`` result.
    """
    totals = _totals if _totals is not None else position_totals(nodes)
    root_ctx = NodeTraverseContext(depth=0, heading_path=[], parent=None)
    yield from _iter_nodes(nodes, root_ctx, max_depth, stop_predicate, totals, _WalkCounters())


def _iter_nodes(
    nodes: list[CndNode],
    ctx: NodeTraverseContext,
    max_depth: int | None,
    stop_predicate: StopPredicate | None,
    totals: tuple[int, dict[int, int]],
    counters: _WalkCounters,
) -> Iterator[NodeTraverse]:
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
            page_count=page_counts[node.location.page],
        )
        yield NodeTraverse(node=node, ctx=visit_ctx)

        children = _children_of(node)
        if not children:
            continue
        if (max_depth is not None and ctx.depth >= max_depth) or (
            stop_predicate is not None and stop_predicate(node, visit_ctx)
        ):
            counters.skip_subtree(children)
            continue

        child_ctx = NodeTraverseContext(
            depth=ctx.depth + 1,
            heading_path=(
                node.heading_path if isinstance(node, HeadingNode) else ctx.heading_path
            ),
            parent=node,
        )
        yield from _iter_nodes(
            children, child_ctx, max_depth, stop_predicate, totals, counters
        )
