from functools import total_ordering
from uuid import UUID
from typing import Annotated, Any, Literal, Union
from collections.abc import Callable, Iterator
from dataclasses import dataclass

from pydantic import BaseModel, Field


@total_ordering
class NodeLocation(BaseModel):
    """Physical position of a node in the compiled document."""

    page: int
    span: int
    page_span: int
    parent_span: int
    span_count: int

    def __lt__(self, other: object) -> bool:
        if not isinstance(other, NodeLocation):
            return NotImplemented
        return self.span < other.span


class NodeRef(BaseModel):
    """Resolved cross-reference edge: stable node id plus optional Typst label."""

    id: UUID
    label: str | None = None


class NodeBase(BaseModel):
    """Shared fields for every manifest node."""

    id: UUID
    label: str | None = None
    refs_to: list[NodeRef] = Field(default_factory=list)
    refs_from: list[NodeRef] = Field(default_factory=list)
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

    def to_text(self) -> str:
        return self.text


class ParagraphNode(NodeBase):
    """Plain text paragraph."""

    type: Literal["paragraph"]
    text: str
    lang: str | None = None

    def to_text(self) -> str:
        return self.text


class TableCell(BaseModel):
    """Single cell inside a table node."""

    row: int
    col: int
    rowspan: int = 1
    colspan: int = 1
    is_header: bool = False
    text: str


class TableNode(NodeBase):
    """Structured table with typed cells and optional caption.

    ``kind`` distinguishes a semantic ``table`` from a layout ``grid``: both
    share the same cell model, but a grid carries no tabular semantics.
    """

    type: Literal["table"]
    kind: Literal["table", "grid"] = "table"
    caption: str | None = None
    fig_number: str | None = None
    cells: list[TableCell] = Field(default_factory=list)
    raw_typst: str | None = None

    def to_text(self) -> str:
        from cnd.core.node_text import table_node_placeholder

        return table_node_placeholder(self)


class QuoteNode(NodeBase):
    """Block quotation with optional attribution (author or source)."""

    type: Literal["quote"]
    text: str
    attribution: str | None = None
    block: bool = True
    lang: str | None = None

    def to_text(self) -> str:
        if self.attribution:
            return f"{self.text}\n— {self.attribution}"
        return self.text


class CodeNode(NodeBase):
    """Raw code block, preserved verbatim with its language tag."""

    type: Literal["code"]
    text: str
    lang: str | None = None
    block: bool = True

    def to_text(self) -> str:
        fence = f"```{self.lang or ''}".rstrip()
        return f"{fence}\n{self.text}\n```"


class MathNode(NodeBase):
    """Block-level equation."""

    type: Literal["math"]
    text: str
    raw_typst: str | None = None
    numbering: str | None = None
    block: bool = True

    def to_text(self) -> str:
        return self.text


class FigureNode(NodeBase):
    """Non-table figure (image and other figurable content)."""

    type: Literal["figure"]
    caption: str | None = None
    fig_number: str | None = None
    kind: str | None = None
    alt: str | None = None
    path: str | None = None
    raw_typst: str | None = None

    def to_text(self) -> str:
        from cnd.core.node_text import figure_node_placeholder

        return figure_node_placeholder(self)


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

    def to_text(self) -> str:
        from cnd.core.node_text import render_list_markdown

        return render_list_markdown(self.items, ordered=self.ordered)


CndNode = Annotated[
    Union[
        HeadingNode,
        ParagraphNode,
        TableNode,
        QuoteNode,
        CodeNode,
        MathNode,
        FigureNode,
        ListNode,
    ],
    Field(discriminator="type"),
]

ListItem.model_rebuild()

HeadingNode.model_rebuild()  # For recursive reference to children


@dataclass(frozen=True)
class NodeTraverseContext:
    """Traversal state passed to visitor hooks for the current node."""

    depth: int
    heading_path: list[str]
    parent: CndNode | None = None


@dataclass(frozen=True)
class NodeTraverse:
    """A node paired with its traversal context."""

    node: CndNode
    ctx: NodeTraverseContext


StopPredicate = Callable[[CndNode, NodeTraverseContext], bool]


def iter_nodes(
    nodes: list[CndNode],
    *,
    max_depth: int | None = None,
    stop_predicate: StopPredicate | None = None,
) -> Iterator[NodeTraverse]:
    """Walk a node tree depth-first, yielding each node with its context."""
    root_ctx = NodeTraverseContext(depth=0, heading_path=[], parent=None)
    yield from _iter_nodes(nodes, root_ctx, max_depth, stop_predicate)


def _iter_nodes(
    nodes: list[CndNode],
    ctx: NodeTraverseContext,
    max_depth: int | None,
    stop_predicate: StopPredicate | None,
) -> Iterator[NodeTraverse]:
    for node in nodes:
        visit_ctx = NodeTraverseContext(
            depth=ctx.depth,
            heading_path=ctx.heading_path,
            parent=ctx.parent,
        )
        yield NodeTraverse(node=node, ctx=visit_ctx)

        if not isinstance(node, HeadingNode) or not node.children:
            continue
        if max_depth is not None and ctx.depth >= max_depth:
            continue
        if stop_predicate is not None and stop_predicate(node, visit_ctx):
            continue

        child_ctx = NodeTraverseContext(
            depth=ctx.depth + 1,
            heading_path=node.heading_path,
            parent=node,
        )
        yield from _iter_nodes(node.children, child_ctx, max_depth, stop_predicate)