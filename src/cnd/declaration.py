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
- ``number`` — the resolved running counter value ("2.1.1", "3"), which
  needs a counter engine the declarative producer does not have. Its one
  authored half — a list item's start override — survives on
  ``DeclListItem``;
- ``heading_path`` — derivable from the node's position in the tree.

What it keeps is authored content: the ``label`` (the only durable
identity, and it lives in the source — ADR 0015/0017), the link families
keyed by label, and every content field. It also keeps **``counter_label``**
on the counter-bearing nodes — unlike ``number`` this has an authored half
the builder cannot derive: a heading or equation has no ``kind`` to derive
a word from, and a figure with a custom ``kind`` carries a word the author
supplied and nothing else encodes (the very reason it is a field, per
proposal 0010). Dropping it while keeping the list-number override would
be the same authored/derived split resolved two opposite ways. The value objects that carry no
presentation state — table cells, the link edges, dates, raw source — are
the CND's own, reused rather than re-declared, because a table cell is a
table cell in either form. Only the node types are defined fresh, so the
declaration is free to evolve without dragging the CND along.
"""

from typing import Annotated, Any, Literal, Union

from pydantic import BaseModel, ConfigDict, Field

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


class _Strict(BaseModel):
    """Base for the declaration-specific models: an unknown field is a
    **rejection**, not a silent drop.

    The declaration is authored by hand or by a language model, and its
    whole purpose is to be hand-corrected before building (ADR 0019, spec
    §12). A typo — ``capton`` for ``caption`` — that vanished silently
    would defeat that: the mistake is invisible precisely where it is
    meant to be caught. So a stray key raises. Forward compatibility does
    not need silent tolerance here — ``declaration_version`` signals a
    version mismatch explicitly.

    **This strictness is partial by construction.** ``extra="forbid"`` is
    per model and does not reach the value objects reused from the CND
    (``TableCell``, the link edges, ``DocMetadata``): those keep the CND's
    lenient config, since forbidding on them would change CND parsing. A
    stray key on a node or at the top level is caught; one *inside* a
    table cell or a link edge is not. The open extension bags
    (``state_metadata``, ``fields``) are dict-typed and unaffected — they
    still hold arbitrary keys.
    """

    model_config = ConfigDict(extra="forbid")


class DeclNodeBase(_Strict):
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
    """A section heading. No ``number`` (the builder's counter engine
    resolves it) and no ``heading_path`` (derivable from tree position).
    ``counter_label`` is kept: a heading has no ``kind`` to derive a word
    from, so any word ("Chapter", "Partie") is authored.

    ``level`` starts at 1 — there is no level 0. Constraining it here
    makes the invalid input unrepresentable rather than a counter-engine
    crash at build time (ADR 0019 §4's own philosophy: reject at the
    door, not downstream)."""

    type: Literal["heading"]
    level: Annotated[int, Field(ge=1)]
    text: str
    counter_label: str | None = None
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
    counter_label: str | None = None
    block: bool = True


class DeclImageNode(DeclNodeBase):
    type: Literal["image"]
    path: str | None = None
    alt: str | None = None


class DeclFigureNode(DeclNodeBase):
    """A captioned float wrapper. Keeps ``kind`` (the authored counter
    selector) and ``counter_label`` (authored for a custom ``kind`` the
    builder has no localized word for), but not the resolved ``number``."""

    type: Literal["figure"]
    kind: str | None = None
    caption: str | None = None
    counter_label: str | None = None
    children: list["DeclNode"] = Field(default_factory=list)
    raw: RawSource | None = None


class DeclListItem(_Strict):
    """One item of a declaration list.

    ``number`` is an **override**, not a resolved ordinal: absent means
    "number this item sequentially", present means an explicit start or
    skip (markdown's ``3.`` on the first item of an ordered list). This is
    the one place the declaration keeps a ``number`` the CND resolves — it
    keeps the *authored* half (the override) and drops the *derived* half
    (the running ordinal), the same line drawn for figure numbers.

    Resolution rule the builder follows (pinned so two builders cannot
    diverge): an item with no ``number`` takes the previous sibling's
    resolved number plus one, starting from 1; an item *with* a ``number``
    takes it verbatim, and following items count on from there. So a
    ``number`` **rebases** the rest of the list rather than only labelling
    its own item. Ignored on an ``ordered: false`` list, which has no
    ordinals.
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


class DeclBibEntry(_Strict):
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


class DeclFootnote(_Strict):
    """A footnote in a declaration — ``Footnote`` minus ``id``."""

    label: str
    text: str


class Declaration(_Strict):
    """The source form a producer emits and the builder compiles.

    No ``id``, ``built_at`` or ``cnd_version`` — all three are the
    builder's to supply. ``source`` is kept, optional: a producer
    converting ``notes.md`` legitimately records what it converted from,
    and provenance is not resolved presentation state.

    ``declaration_version`` is **required**, matching the CND's required
    ``cnd_version``. It exists to stop the first evolution of the schema
    from breaking every producer silently (ADR 0019 §3); an omitted
    version defaulting to "current" is exactly the silent assumption it
    guards against, so absence is an error, not "latest".
    """

    declaration_version: str
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
