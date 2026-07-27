from collections.abc import Iterator
from datetime import datetime
from typing import Any, Union
from uuid import UUID, uuid4

from pydantic import BaseModel, Field, PrivateAttr

from cnd.core.nodes import (
    CndNode,
    NodeTraverse,
    StopPredicate,
    iter_nodes,
    position_totals,
)


CND_VERSION = "0.3.0"
"""The format version this SDK builds and targets (spec/cnd-spec.md).

Stamped into ``Cnd.cnd_version`` by the builder (docs/adr/0019). One
constant so the builder, and any future writer, cannot drift from the
version the models implement.
"""


class DocDate(BaseModel):
    """Partial or full document date from cnd metadata."""

    year: int
    month: int | None = None
    day: int | None = None


class DocMetadata(BaseModel):
    """Bibliographic metadata for the work the CND represents.

    This identifies the *work* — title, authors, date. The input artifact it
    was built from is ``Cnd.source``, deliberately separate: the same work
    can be built from a Typst source and later re-imported from another
    format (docs/proposals/0008).
    """

    title: str
    authors: list[str] = Field(default_factory=list)
    date: DocDate | None = None
    keywords: list[str] = Field(default_factory=list)
    description: str | None = None
    lang: str | None = None


class SourceInfo(BaseModel):
    """The input artifact the CND was built from.

    ``hash`` is self-describing (``"sha256:…"``). Its comparability is
    narrow and normative: two hashes are comparable only between CNDs from
    the **same producer over the same source**, where equal means unchanged
    and different means changed. Comparing across producers is meaningless.

    ``uri`` is an identifier in the producer's own space and is **never
    promised resolvable** — a consumer must not dereference it.
    """

    type: str
    hash: str
    uri: str | None = None


class BibEntry(BaseModel):
    """Bibliography pool entry — target of ``cites`` edges.

    ``formatted`` is the reference string as displayed in the built
    document (the faithful capture). It is nullable because requiring it
    presupposes a style engine ran, which a hand author or a markdown
    producer has no reason to have. A curated typed subset of common
    bibliographic fields is lifted alongside it; the full source entry
    (e.g. Hayagriva) is carried losslessly as structured JSON in ``fields``.

    An entry must carry ``formatted``, structured fields, or both — never an
    empty, unconsumable entry. That floor is a validator rule, not a shape
    the type system can express.
    """

    id: UUID
    label: str
    formatted: str | None = None
    type: str | None = None
    authors: list[str] = Field(default_factory=list)
    title: str | None = None
    year: int | None = None
    container: str | None = None
    doi: str | None = None
    url: str | None = None
    fields: dict[str, Any] = Field(default_factory=dict)


class Footnote(BaseModel):
    """Footnote pool entry — target of ``footnotes`` edges. Flat text."""

    id: UUID
    label: str
    text: str


LinkTarget = Union[CndNode, BibEntry, Footnote]
"""What a link family can resolve to: a node, or an out-of-tree pool entry."""


class Cnd(BaseModel):
    """Top-level CND — a compiled document as a tree of typed nodes."""

    id: UUID = Field(default_factory=uuid4)
    cnd_version: str
    built_at: datetime
    source: SourceInfo | None = None
    doc: DocMetadata
    nodes: list[CndNode]
    bibliography: list[BibEntry] = Field(default_factory=list)
    footnotes: list[Footnote] = Field(default_factory=list)

    _incoming_index: dict[str, list[CndNode]] | None = PrivateAttr(default=None)
    _label_index: dict[str, LinkTarget] | None = PrivateAttr(default=None)
    _position_totals: tuple[int, dict[int, int]] | None = PrivateAttr(default=None)

    @property
    def paginated(self) -> bool:
        """Whether this CND carries page locations.

        Derived, never serialized: a boolean a consumer can compute is not a
        field (docs/adr/0012, docs/proposals/0008). Pagination is
        all-or-nothing — a partially located CND is a validation error — so
        the first node settles it for the whole document.
        """
        for visit in self.iter():
            return visit.node.location is not None
        return False

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

    def resolve(self, label: str) -> LinkTarget | None:
        """The node or pool entry carrying ``label``, or ``None``.

        Labels are globally unique within a CND (docs/adr/0017), which is
        what lets one index serve all three link families; the family an
        edge sits in still fixes its resolution domain, so a caller that
        needs domain enforcement checks the returned type.
        """
        if self._label_index is None:
            index: dict[str, LinkTarget] = {}
            for visit in self.iter():
                if visit.node.label is not None:
                    index.setdefault(visit.node.label, visit.node)
            for entry in (*self.bibliography, *self.footnotes):
                index.setdefault(entry.label, entry)
            self._label_index = index
        return self._label_index.get(label)

    def incoming(self, label: str) -> list[CndNode]:
        """Distinct nodes whose forward edges (``refs``, ``cites``,
        ``footnotes``) point at ``label``.

        A CND serializes forward edges only (docs/adr/0008); this
        reverse index is derived, built lazily on first call and cached on
        the instance. A node that references the same target more than once
        appears once. ``label`` may name a node or a pool entry.
        """
        if self._incoming_index is None:
            index: dict[str, list[CndNode]] = {}
            seen: dict[str, set[UUID]] = {}
            for visit in self.iter():
                node = visit.node
                for link in (*node.refs, *node.cites, *node.footnotes):
                    sources = seen.setdefault(link.label, set())
                    if node.id in sources:
                        continue
                    sources.add(node.id)
                    index.setdefault(link.label, []).append(node)
            self._incoming_index = index
        return self._incoming_index.get(label, [])
