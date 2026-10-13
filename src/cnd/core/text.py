"""Rich text: prose with standoff marks and its own link families.

Every slot that holds prose is a ``RichText`` (docs/proposals/0013,
principle 1). Every ``[start, end)`` span — a mark or an edge's
``text_span`` — indexes the ``value`` of the ``RichText`` that holds it,
in Unicode code points (docs/adr/0013). Verbatim content (code, math
source, ``raw``) and metadata stay plain strings.
"""

from typing import Literal, Union

from pydantic import BaseModel, Field


class RawSource(BaseModel):
    """The producer's verbatim source for a node, with its language.

    A bare string dropped the one thing a consumer needs to decide whether
    to attempt a parse: which language the content is in. ``format`` is an
    open string (``"typst"``, ``"latex"``, ``"mathml"``…), never a closed
    enum — a new producer must not require a spec revision.
    """

    format: str
    value: str


class NodeRef(BaseModel):
    """Forward cross-reference edge to another node.

    An edge is ``{label, text_span?}``: it names its target by label and
    resolves through the CND's label index (docs/adr/0017, superseding the
    ``{id, label}`` form of docs/adr/0002). ``text_span`` marks where the
    reference marker sits in the ``value`` of the ``RichText`` that holds
    the edge, as a
    ``[start, end)`` pair of Unicode code-point offsets (docs/adr/0013).
    """

    label: str
    text_span: list[int] | None = None


class CiteRef(BaseModel):
    """Forward citation edge; ``label`` resolves in the CND ``bibliography`` pool."""

    label: str
    text_span: list[int] | None = None
    form: Literal["normal", "prose", "full", "author", "year", "none"] | None = None
    supplement: str | None = None


class FootnoteRef(BaseModel):
    """Forward footnote edge; ``label`` resolves in the CND ``footnotes`` pool."""

    label: str
    text_span: list[int] | None = None


class LinkRef(BaseModel):
    """Forward hyperlink edge; ``href`` resolves nowhere in the CND.

    The fourth forward family and the only one not keyed by label: a
    hyperlink's target is outside the document by definition, so it admits
    no resolution domain and has no dangling state — a URL is a URL. The
    scheme is a consumer's business (``https:``, ``doi:``, an application
    scheme); the format only carries the string.
    """

    href: str
    text_span: list[int] | None = None


Edge = Union[NodeRef, CiteRef, FootnoteRef, LinkRef]
"""Any forward edge. Three are label-keyed; ``LinkRef`` is href-keyed."""

KNOWN_MARK_KINDS = frozenset(
    {"strong", "emph", "code", "strike", "sup", "sub", "underline", "highlight", "math"}
)
"""The mark kinds the spec defines. ``Mark.kind`` is an open vocabulary:
any other string is valid, and a consumer that does not know it renders
the covered text unchanged."""

ATOMIC_MARK_KINDS = frozenset({"code", "math"})
"""Verbatim marks: they contain no other mark and no edge span may reach
inside them partially (docs/proposals/0013, Marks rule 4)."""


class Mark(BaseModel):
    """A standoff span of inline formatting inside a ``RichText.value``.

    ``raw`` is the source of the covered text, used by ``math`` (the
    readable linear form lives in ``value``, the formula here).
    """

    start: int
    end: int
    kind: str
    raw: RawSource | None = None


class RichText(BaseModel):
    """Prose: a text, its language, its marks and its forward edges.

    An edge belongs to the text in which its marker opens; its owning
    node is the nearest node holding the text. Every list defaults to
    empty and may be omitted, so ``{"value": "…"}`` is a complete text.
    ``lang`` null inherits from the enclosing text, then the node chain,
    then ``doc.lang``.
    """

    value: str
    lang: str | None = None
    marks: list[Mark] = Field(default_factory=list)
    refs: list[NodeRef] = Field(default_factory=list)
    cites: list[CiteRef] = Field(default_factory=list)
    footnotes: list[FootnoteRef] = Field(default_factory=list)
    links: list[LinkRef] = Field(default_factory=list)

    def edges(self) -> list[Edge]:
        """All forward edges of this text: refs, cites, footnotes, links."""
        return [*self.refs, *self.cites, *self.footnotes, *self.links]


class Numbering(BaseModel):
    """A resolved counter as displayed: ``value`` ("3", "2.1.1", "(1)")
    and the counter word in the document's language (``name``, "Figure").

    Replaces the flat ``number`` + ``counter_label`` pair, so a word
    without a number can no longer be written (docs/proposals/0013).
    """

    value: str
    name: str | None = None
