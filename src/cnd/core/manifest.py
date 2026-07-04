from collections.abc import Iterator
from datetime import datetime
from uuid import UUID, uuid4

from pydantic import BaseModel, Field

from cnd.core.nodes import CndNode, NodeTraverse, StopPredicate, iter_nodes


class DocDate(BaseModel):
    """Partial or full document date from manifest metadata."""

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


class CndManifest(BaseModel):
    """Top-level CND manifest produced by the ``typst-cnd`` compiler."""

    id: UUID = Field(default_factory=uuid4)
    cnd_version: str
    doc_hash: str
    compiled_at: datetime
    doc: DocMetadata
    nodes: list[CndNode]

    def iter(
        self,
        *,
        max_depth: int | None = None,
        stop_predicate: StopPredicate | None = None,
    ) -> Iterator[NodeTraverse]:
        """Iterate manifest nodes depth-first with traversal context."""
        return iter_nodes(
            self.nodes,
            max_depth=max_depth,
            stop_predicate=stop_predicate,
        )

    def __iter__(self) -> Iterator[NodeTraverse]:
        return self.iter()