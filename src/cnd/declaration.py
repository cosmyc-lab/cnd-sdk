"""The declaration — the source form the builder compiles into a CND.

A declaration is what a producer with **neither ids nor pagination to
offer** emits: a hand author, a language model, or a foreign-format
producer whose source is unpaginated (markdown, HTML). The builder reads
it and produces the CND (docs/adr/0019, the declarative door).

**Non-normative.** ADR 0006 scopes the standard to the CND; the
declaration is a second surface that stays non-normative until it has
proven itself, and any promotion is a separate ADR. Its schema lives at
``schema/cnd-declaration.schema.json``, a sibling of the CND schema, and
is generated from these models exactly as the CND schema is (ADR 0004) —
so there is no second hand-maintained definition to drift.

**The declaration is the CND minus everything the builder derives.** The
principle is the one the whole format applies (ADR 0008/0012): a field a
consumer — here, the builder — can compute is never carried. Concretely,
a declaration node has no

- ``id`` — the builder mints node ids; they are not durable anyway
  (ADR 0015), so a producer supplying them would only be supplying noise;
- ``location`` — an unpaginated source has no page (ADR 0019);
- ``number`` / ``counter_label`` — resolved counter state, which needs a
  counter engine the declarative producer does not have;
- ``heading_path`` — derivable from the node's position in the tree.

What it keeps is authored content: the ``label`` (the only durable
identity, and it lives in the source — ADR 0015/0017), the link families
keyed by label, and every content field. The value objects that carry no
presentation state — table cells, the link edges, dates, raw source — are
the CND's own, reused rather than re-declared, because a table cell is a
table cell in either form. Only the node types are defined fresh, so the
declaration is free to evolve without dragging the CND along.
"""

from typing import Annotated, Any, Literal, Union

from pydantic import BaseModel, Field

# Authored-content value objects, shared verbatim with the CND: they carry
# no id and no presentation state, so there is nothing to strip.
from cnd.core.cnd import DocDate, DocMetadata, SourceInfo
from cnd.core.nodes import (
    CiteRef,
    FootnoteRef,
    NodeRef,
    RawSource,
    TableCell,
    TermItem,
)

DECLARATION_VERSION = "0.1.0"
"""The version of the declaration schema (ADR 0019 §3).

Versioned independently of ``cnd_version``: the declaration is a distinct,
non-normative surface, and its first cut is not tied to the format's 0.3.0.
Without this field the first evolution of the declaration would break every
producer silently.
"""


class DeclNodeBase(BaseModel):
    """Shared fields for every declaration node.

    The CND's ``NodeBase`` minus ``id`` and ``location``: a declaration
    supplies neither. ``label`` is the durable identity and is authored;
    the link families are authored and resolve by label (ADR 0017).
    """

    label: str | None = None
    refs: list[NodeRef] = Field(default_factory=list)
    cites: list[CiteRef] = Field(default_factory=list)
    footnotes: list[FootnoteRef] = Field(default_factory=list)
    state_metadata: dict[str, Any] = Field(default_factory=dict)


class DeclHeadingNode(DeclNodeBase):
    """A section heading. No ``number``/``counter_label`` (resolved by the
    builder's counter engine) and no ``heading_path`` (derivable from tree
    position)."""

    type: Literal["heading"]
    level: int
    text: str
    children: list["DeclNode"] = Field(default_factory=list)


class DeclParagraphNode(DeclNodeBase):
    type: Literal["paragraph"]
    text: str
    lang: str | None = None


class DeclTableNode(DeclNodeBase):
    type: Literal["table"]
    kind: Literal["table", "grid"] = "table"
    content_kind: Literal["data", "content"] | None = None
    cells: list[TableCell] = Field(default_factory=list)
    raw: RawSource | None = None


class DeclQuoteNode(DeclNodeBase):
    type: Literal["quote"]
    text: str
    attribution: str | None = None
    block: bool = True
    lang: str | None = None


class DeclCodeNode(DeclNodeBase):
    type: Literal["code"]
    text: str
    lang: str | None = None
    block: bool = True


class DeclMathNode(DeclNodeBase):
    type: Literal["math"]
    text: str
    raw: RawSource | None = None
    block: bool = True


class DeclImageNode(DeclNodeBase):
    type: Literal["image"]
    path: str | None = None
    alt: str | None = None


class DeclFigureNode(DeclNodeBase):
    """A captioned float wrapper. Keeps ``kind`` — the counter selector is
    authored — but not the resolved ``number``/``counter_label``."""

    type: Literal["figure"]
    kind: str | None = None
    caption: str | None = None
    children: list["DeclNode"] = Field(default_factory=list)
    raw: RawSource | None = None


class DeclListItem(BaseModel):
    """One item of a declaration list.

    ``number`` is an **override**, not a resolved ordinal: absent means
    "number this item sequentially", present means an explicit start or
    skip (markdown's ``3.`` on the first item of an ordered list). This is
    the one place the declaration keeps a ``number`` the CND resolves — it
    keeps the *authored* half (the override) and drops the *derived* half
    (the running ordinal), the same line drawn for figure numbers.
    """

    text: str
    number: int | None = None
    children: list["DeclListItem"] = Field(default_factory=list)


class DeclListNode(DeclNodeBase):
    type: Literal["list"]
    ordered: bool = False
    tight: bool = True
    items: list[DeclListItem] = Field(default_factory=list)


class DeclTermsNode(DeclNodeBase):
    type: Literal["terms"]
    tight: bool = True
    items: list[TermItem] = Field(default_factory=list)


DeclNode = Annotated[
    Union[
        DeclHeadingNode,
        DeclParagraphNode,
        DeclTableNode,
        DeclQuoteNode,
        DeclCodeNode,
        DeclMathNode,
        DeclFigureNode,
        DeclImageNode,
        DeclListNode,
        DeclTermsNode,
    ],
    Field(discriminator="type"),
]

DeclListItem.model_rebuild()
DeclHeadingNode.model_rebuild()
DeclFigureNode.model_rebuild()


class DeclBibEntry(BaseModel):
    """A bibliography entry in a declaration — ``BibEntry`` minus ``id``.

    The content floor still applies at build time: an entry must carry
    ``formatted``, a structured field, or both. It is a builder check, not
    a shape the schema expresses.
    """

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


class DeclFootnote(BaseModel):
    """A footnote in a declaration — ``Footnote`` minus ``id``."""

    label: str
    text: str


class Declaration(BaseModel):
    """The source form a producer emits and the builder compiles.

    No ``id``, ``built_at`` or ``cnd_version`` — all three are the
    builder's to supply. ``source`` is kept, optional: a producer
    converting ``notes.md`` legitimately records what it converted from,
    and provenance is not resolved presentation state.
    """

    declaration_version: str = DECLARATION_VERSION
    source: SourceInfo | None = None
    doc: DocMetadata
    nodes: list[DeclNode]
    bibliography: list[DeclBibEntry] = Field(default_factory=list)
    footnotes: list[DeclFootnote] = Field(default_factory=list)


__all__ = [
    "DECLARATION_VERSION",
    "Declaration",
    "DeclBibEntry",
    "DeclCodeNode",
    "DeclFigureNode",
    "DeclFootnote",
    "DeclHeadingNode",
    "DeclImageNode",
    "DeclListItem",
    "DeclListNode",
    "DeclMathNode",
    "DeclNode",
    "DeclNodeBase",
    "DeclParagraphNode",
    "DeclQuoteNode",
    "DeclTableNode",
    "DeclTermsNode",
    # re-exported CND value objects the declaration reuses
    "CiteRef",
    "DocDate",
    "DocMetadata",
    "FootnoteRef",
    "NodeRef",
    "RawSource",
    "SourceInfo",
    "TableCell",
    "TermItem",
]
