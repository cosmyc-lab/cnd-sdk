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
- ``numbering.value`` — the resolved running counter value ("2.1.1",
  "3"), which needs a counter engine the declarative producer does not
  have;
- ``heading_path`` — derivable from the node's position in the tree.

What it keeps is authored content: the ``label`` (the only durable
identity, and it lives in the source — ADR 0015/0017), every text with
its marks and link families, and every content field. It also keeps
**``numbering.name``** on the counter-bearing nodes: unlike the value,
the counter word has an authored half the builder cannot derive — a
heading or equation has no ``kind`` to derive a word from, and a figure
with a custom ``kind`` carries a word only the author knows
(docs/proposals/0013, "Numbering"). A list item likewise keeps
``number``, as an authored *override* of the sequential ordinal.

**Shorthand** (docs/proposals/0013, "Declaration"). Wherever the CND
holds a ``RichText``, a declaration accepts a plain string, which builds
``{"value": "<string>"}`` with no marks and no edges, or the full object.
The full object *is* the CND's ``RichText``, so everything a text can
carry — marks, ``refs``, ``cites``, ``footnotes`` and ``links`` — is
available to a producer that computes offsets. The shorthand lives here
only: the CND models stay strict about their shape.

The value objects that carry no presentation state — ``RichText``, its
marks and edges, ``RawSource``, the document metadata — are the CND's
own, reused rather than re-declared. Everything that holds nested nodes
(list items, term items, cells, footnotes) is declared fresh, because a
CND node requires an ``id`` a declaration never carries.
"""

from typing import Annotated, Any, Literal, Union

from pydantic import AfterValidator, BaseModel, ConfigDict, Field

# Authored-content value objects, shared verbatim with the CND: they carry
# no id and no presentation state, so there is nothing to strip.
from cnd.core.cnd import DocDate, DocMetadata, SourceInfo
from cnd.core.text import (
    CiteRef,
    FootnoteRef,
    LinkRef,
    Mark,
    NodeRef,
    RawSource,
    RichText,
)

DECLARATION_VERSION = "0.2.0"
"""The version of the declaration schema (ADR 0019 §3).

Versioned independently of ``cnd_version``. ``0.2.0`` is the first
breaking change: texts became rich text, node-level link families moved
into them, ``number`` and ``counter_label`` became ``numbering.name``, and
list items, term items, cells and footnotes hold nodes
(docs/proposals/0013). A ``0.1.0`` declaration is refused by the builder
rather than misread.
"""


def _as_rich_text(value: "str | RichText") -> RichText:
    """The shorthand: a plain string is a text with no marks and no edges."""
    return RichText(value=value) if isinstance(value, str) else value


DeclText = Annotated[Union[str, RichText], AfterValidator(_as_rich_text)]
"""A ``RichText`` slot in a declaration: a plain string or the full object.

Typed as the union so the generated schema says ``anyOf: [string,
RichText]``; after validation the value is always a ``RichText``."""


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

    **This strictness stops at the reused value objects.**
    ``extra="forbid"`` is per model and does not reach what the
    declaration shares with the CND (``RichText``, its marks and edges,
    ``DocMetadata``): those keep the CND's lenient config, since forbidding
    on them would change CND parsing. A stray key on a node, a list item,
    a term item, a cell, a footnote or at the top level is caught; one
    *inside* a text object or a link edge is not. The open extension bags
    (``state_metadata``, ``fields``) are dict-typed and unaffected — they
    still hold arbitrary keys.
    """

    model_config = ConfigDict(extra="forbid")


class DeclNumbering(_Strict):
    """The authored half of ``Numbering``: the counter word alone.

    Present means "this element carries this word" ("Listing",
    "Théorème"); the builder's counter engine supplies the value. There is
    no ``value`` field, so a declaration cannot carry one.
    """

    name: str | None = None


class DeclNodeBase(_Strict):
    """Shared fields for every declaration node.

    The CND's ``NodeBase`` minus ``id`` and ``location``: a declaration
    supplies neither. ``label`` is the durable identity and is authored.
    The link families live in the node's texts, as in the CND.
    """

    label: str | None = None
    state_metadata: dict[str, Any] = Field(default_factory=dict)


class DeclHeadingNode(DeclNodeBase):
    """A section heading. No ``heading_path`` (derivable from tree
    position) and no resolved number.

    ``level`` starts at 1 — there is no level 0. Constraining it here
    makes the invalid input unrepresentable rather than a counter-engine
    crash at build time (ADR 0019 §4's own philosophy: reject at the
    door, not downstream)."""

    type: Literal["heading"]
    level: Annotated[int, Field(ge=1)]
    text: DeclText
    numbering: DeclNumbering | None = None
    children: list["DeclNode"] = Field(default_factory=list)


class DeclParagraphNode(DeclNodeBase):
    type: Literal["paragraph"]
    text: DeclText


class DeclQuoteNode(DeclNodeBase):
    type: Literal["quote"]
    attribution: DeclText | None = None
    children: list["DeclNode"] = Field(default_factory=list)


class DeclCodeNode(DeclNodeBase):
    type: Literal["code"]
    text: str
    lang: str | None = None
    title: str | None = None


class DeclMathNode(DeclNodeBase):
    type: Literal["math"]
    text: str
    raw: RawSource | None = None
    numbering: DeclNumbering | None = None


class DeclImageNode(DeclNodeBase):
    type: Literal["image"]
    path: str | None = None
    alt: str | None = None


class DeclFigureNode(DeclNodeBase):
    """A captioned wrapper. Keeps ``kind`` (the category, and the counter
    the engine draws from) and ``numbering.name`` (authored for a custom
    ``kind`` the builder has no localized word for)."""

    type: Literal["figure"]
    kind: str | None = None
    caption: DeclText | None = None
    description: DeclText | None = None
    numbering: DeclNumbering | None = None
    children: list["DeclNode"] = Field(default_factory=list)
    raw: RawSource | None = None


class DeclAdmonitionNode(DeclNodeBase):
    type: Literal["admonition"]
    kind: str
    title: DeclText | None = None
    children: list["DeclNode"] = Field(default_factory=list)


class DeclListItem(_Strict):
    """One item of a declaration list; its content is nodes.

    ``number`` is an **override**, not a resolved ordinal: absent means
    "number this item sequentially", present means an explicit start or
    skip (markdown's ``3.`` on the first item of an ordered list). It keeps
    the *authored* half (the override) and drops the *derived* half (the
    running ordinal), the same line drawn for ``numbering``.

    Resolution rule the builder follows (pinned so two builders cannot
    diverge): an item with no ``number`` takes the previous sibling's
    resolved number plus one, starting from 1; an item *with* a ``number``
    takes it verbatim, and following items count on from there. So a
    ``number`` **rebases** the rest of the list rather than only labelling
    its own item. Ignored on an ``ordered: false`` list, which has no
    ordinals. A nested list is a ``list`` node among the children and
    counts on its own.
    """

    number: int | None = None
    checked: bool | None = None
    children: list["DeclNode"] = Field(default_factory=list)


class DeclListNode(DeclNodeBase):
    type: Literal["list"]
    ordered: bool = False
    items: list[DeclListItem] = Field(default_factory=list)


class DeclTermItem(_Strict):
    term: DeclText
    children: list["DeclNode"] = Field(default_factory=list)


class DeclTermsNode(DeclNodeBase):
    type: Literal["terms"]
    items: list[DeclTermItem] = Field(default_factory=list)


class DeclCell(_Strict):
    """One cell of a declared ``table`` or ``layout``; content is nodes."""

    row: int
    col: int
    rowspan: int = Field(default=1, ge=1)
    colspan: int = Field(default=1, ge=1)
    is_header: bool = False
    children: list["DeclNode"] = Field(default_factory=list)


class DeclTableNode(DeclNodeBase):
    """``kind`` is the author's statement (``"data"``, ``"content"``, or
    any other value of the open vocabulary); the builder never guesses
    one."""

    type: Literal["table"]
    kind: str | None = None
    cells: list[DeclCell] = Field(default_factory=list)


class DeclLayoutNode(DeclNodeBase):
    type: Literal["layout"]
    cells: list[DeclCell] = Field(default_factory=list)


DeclNode = Annotated[
    Union[
        DeclHeadingNode,
        DeclParagraphNode,
        DeclQuoteNode,
        DeclCodeNode,
        DeclMathNode,
        DeclImageNode,
        DeclFigureNode,
        DeclAdmonitionNode,
        DeclListNode,
        DeclTermsNode,
        DeclTableNode,
        DeclLayoutNode,
    ],
    Field(discriminator="type"),
]

for _model in (
    DeclHeadingNode,
    DeclQuoteNode,
    DeclFigureNode,
    DeclAdmonitionNode,
    DeclListItem,
    DeclTermItem,
    DeclCell,
):
    _model.model_rebuild()


class DeclBibEntry(_Strict):
    """A bibliography entry in a declaration — ``BibEntry`` minus ``id``.

    The content floor still applies at build time: an entry must carry
    ``formatted``, a structured field, or both. It is a builder check, not
    a shape the schema expresses.
    """

    label: str
    formatted: DeclText | None = None
    type: str | None = None
    authors: list[str] = Field(default_factory=list)
    title: str | None = None
    year: int | None = None
    container: str | None = None
    doi: str | None = None
    url: str | None = None
    fields: dict[str, Any] = Field(default_factory=dict)


class DeclFootnote(_Strict):
    """A footnote in a declaration — ``Footnote`` minus ``id``. Its content
    is nodes, which the builder mints ids for like any other node."""

    label: str
    children: list[DeclNode] = Field(default_factory=list)


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
    "DeclAdmonitionNode",
    "DeclBibEntry",
    "DeclCell",
    "DeclCodeNode",
    "DeclFigureNode",
    "DeclFootnote",
    "DeclHeadingNode",
    "DeclImageNode",
    "DeclLayoutNode",
    "DeclListItem",
    "DeclListNode",
    "DeclMathNode",
    "DeclNode",
    "DeclNodeBase",
    "DeclNumbering",
    "DeclParagraphNode",
    "DeclQuoteNode",
    "DeclTableNode",
    "DeclTermItem",
    "DeclTermsNode",
    "DeclText",
    # re-exported CND value objects the declaration reuses
    "CiteRef",
    "DocDate",
    "DocMetadata",
    "FootnoteRef",
    "LinkRef",
    "Mark",
    "NodeRef",
    "RawSource",
    "RichText",
    "SourceInfo",
]
