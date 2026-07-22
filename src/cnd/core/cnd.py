from collections.abc import Iterator
from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

from pydantic import BaseModel, Field, PrivateAttr

from cnd.core.nodes import (
    CndNode,
    NodeTraverse,
    StopPredicate,
    iter_nodes,
    position_totals,
)


class DocDate(BaseModel):
    """Partial or full document date from cnd metadata."""

    year: int
    month: int | None = None
    day: int | None = None


class DocMetadata(BaseModel):
    """Bibliographic metadata for the source document."""

    title: str
    authors: list[str]
    date: DocDate | None = None
    keywords: list[str] = Field(default_factory=list)
    description: str | None = None
    lang: str | None = None


class BibEntry(BaseModel):
    """Bibliography pool entry — target of ``cites`` edges.

    ``rendered`` is the reference string as displayed in the compiled
    document (the faithful capture). A curated typed subset of common
    bibliographic fields is lifted alongside it; the full source entry
    (e.g. Hayagriva) is carried losslessly as structured JSON in ``raw``.
    """

    id: UUID
    label: str
    rendered: str
    type: str | None = None
    authors: list[str] = Field(default_factory=list)
    title: str | None = None
    year: int | None = None
    container: str | None = None
    doi: str | None = None
    url: str | None = None
    raw: dict[str, Any] = Field(default_factory=dict)


class Footnote(BaseModel):
    """Footnote pool entry — target of ``footnotes`` edges. Flat text."""

    id: UUID
    label: str
    text: str


class Cnd(BaseModel):
    """Top-level CND — a compiled document as a tree of typed nodes."""

    id: UUID = Field(default_factory=uuid4)
    cnd_version: str
    doc_hash: str
    compiled_at: datetime
    doc: DocMetadata
    nodes: list[CndNode]
    bibliography: list[BibEntry] = Field(default_factory=list)
    footnotes: list[Footnote] = Field(default_factory=list)

    _incoming_index: dict[UUID, list[CndNode]] | None = PrivateAttr(default=None)
    _position_totals: tuple[int, dict[int, int]] | None = PrivateAttr(default=None)

    def iter(
        self,
        *,
        max_depth: int | None = None,
        stop_predicate: StopPredicate | None = None,
    ) -> Iterator[NodeTraverse]:
        """Iterate cnd nodes depth-first with traversal context.

        Derived reading-order positions (doc/sibling/page index and totals)
        ride on each yielded context; the totals pre-pass is computed once
        per cnd and cached, mirroring ``incoming()``.
        """
        if self._position_totals is None:
            self._position_totals = position_totals(self.nodes)
        return iter_nodes(
            self.nodes,
            max_depth=max_depth,
            stop_predicate=stop_predicate,
            _totals=self._position_totals,
        )

    def __iter__(self) -> Iterator[NodeTraverse]:
        return self.iter()

    def incoming(self, node_id: UUID) -> list[CndNode]:
        """Distinct nodes whose forward edges (``refs``, ``cites``,
        ``footnotes``) point at ``node_id``.

        A CND serializes forward edges only (docs/adr/0008); this
        reverse index is derived, built lazily on first call and cached on
        the instance. A node that references the same target more than once
        appears once. ``node_id`` may be a node id or a pool-entry id.
        """
        if self._incoming_index is None:
            index: dict[UUID, list[CndNode]] = {}
            seen: dict[UUID, set[UUID]] = {}
            for visit in self.iter():
                node = visit.node
                for link in (*node.refs, *node.cites, *node.footnotes):
                    targets = seen.setdefault(link.id, set())
                    if node.id in targets:
                        continue
                    targets.add(node.id)
                    index.setdefault(link.id, []).append(node)
            self._incoming_index = index
        return self._incoming_index.get(node_id, [])
