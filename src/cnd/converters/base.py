"""Converter base layer (docs/proposals/0007, docs/adr/0011).

A **renderer** (``cnd.core.render.NodeRenderer``) maps one node to a text
fragment. A **converter** maps a whole ``Cnd`` to one complete, standalone
document artifact, and is built *on top of* a renderer: it walks the tree
in reading order, delegates each node's body to the renderer, and itself
owns everything that only exists at document scope — front matter,
section assembly, marker resolution against the pools, and the footnote
and bibliography sections.

Converters are SDK facilities and **non-normative** (docs/adr/0006,
docs/adr/0011, spec §7): no converter output shape is ever a conformance
requirement. No direction round-trips — a converter is a one-way
projection of a CND onto a foreign artifact, and every converter
documents what it irreducibly drops.
"""

from abc import ABC, abstractmethod
from collections.abc import Iterator
from dataclasses import dataclass
from typing import ClassVar

from cnd.core.cnd import BibEntry, Cnd, DocDate, Footnote
from cnd.core.nodes import (
    CiteRef,
    CndNode,
    FootnoteRef,
    HeadingNode,
    LinkRef,
    NodeRef,
    NodeTraverse,
    NodeTraverseContext,
    child_slots,
    texts_of,
)
from cnd.core.render import NodeRenderer
from cnd.core.text import RichText

__all__ = [
    "ConversionResult",
    "CndConverter",
    "ResolvedMarker",
    "format_date",
    "iter_body",
    "marker_texts",
    "resolve_markers",
]


def format_date(date: DocDate) -> str:
    """A partial or full ``DocDate`` as an ISO-8601 reduced-precision date."""
    parts = [f"{date.year:04d}"]
    if date.month is not None:
        parts.append(f"{date.month:02d}")
        if date.day is not None:
            parts.append(f"{date.day:02d}")
    return "-".join(parts)


@dataclass(frozen=True)
class ConversionResult:
    """One converted document plus what this particular conversion lost.

    ``text`` is the complete artifact. ``warnings`` are *per-document*
    facts a caller may want to act on — an unresolvable link label, an
    image with no path, a bibliography entry with no ``formatted``
    string. They are deliberately flat human-readable strings: a
    structured drop taxonomy would be a bigger promise than a v1
    converter can keep.

    Losses that are the same for *every* document a converter touches are
    **not** warnings — they are irreducible properties of the target
    format and are documented in each converter's class docstring and in
    docs/proposals/0007.
    """

    text: str
    warnings: tuple[str, ...] = ()

    def __str__(self) -> str:
        return self.text


@dataclass
class ResolvedMarker:
    """One forward edge of a block paired with what its label resolved to.

    ``target`` is ``None`` when the label resolves to nothing, which is a
    document defect (``validate()`` reports it) that a converter reports
    rather than raises on. For a ``links`` edge ``target`` is *always*
    ``None`` for a different reason: an ``href`` has no resolution domain
    in the CND (spec §5), so there is nothing to resolve and nothing to
    warn about — a converter that renders a ``links`` marker must not
    read that ``None`` as an unresolved-label defect.

    ``text_index`` is the position, in reading order, of the ``RichText``
    that holds the edge among the texts of the block (see
    ``marker_texts``). ``sort_key`` orders markers by text, then in text
    order where ``text_span`` is available, per spec §8: the enumeration
    order of the families carries no positional claim, and the only
    positional truth about a marker is its span — which indexes its own
    text, so spans of two texts are never compared.
    """

    family: str
    link: NodeRef | CiteRef | FootnoteRef | LinkRef
    target: object | None
    text_index: int = 0

    @property
    def label(self) -> str | None:
        """The three label-keyed families' label, else ``None``.

        ``links`` is href-keyed, not label-keyed (spec §5): a ``LinkRef``
        carries no ``label`` at all, so a ``links`` marker's ``label`` is
        ``None`` rather than an attribute error. A converter that renders
        ``links`` markers reads ``link.href`` instead.
        """
        return getattr(self.link, "label", None)

    @property
    def sort_key(self) -> tuple[int, int, int, int]:
        span = self.link.text_span
        family_rank = {"refs": 0, "cites": 1, "footnotes": 2, "links": 3}[self.family]
        if span:
            return (self.text_index, 0, span[0], family_rank)
        return (self.text_index, 1, family_rank, 0)


def iter_body(cnd: Cnd) -> Iterator[NodeTraverse]:
    """Walk the body of ``cnd`` in reading order, one visit per emitted block.

    Only headings are descended into: a renderer emits just the heading
    line for them. Every other container (figure, list, terms, table,
    layout, quote, admonition) renders its nested nodes itself
    (docs/adr/0010 for figures, docs/proposals/0013 for the rest), so its
    subtree is pruned — descending would emit that content twice. A
    heading nested in such a container is rendered by the container with
    its whole section (``cnd.core.render.expand_headings``).

    The pools do not enter reading order (spec §8) and are therefore not
    part of this walk; a converter emits them as its own sections.
    """
    return cnd.iter(stop_predicate=_prune_rendered_subtrees)


def _prune_rendered_subtrees(node: CndNode, ctx: NodeTraverseContext) -> bool:
    return not isinstance(node, HeadingNode)


def marker_texts(node: CndNode) -> list[tuple[CndNode, RichText]]:
    """The texts whose edges a block's marker line carries, in reading
    order, each with the node that holds it: the node's own texts, then —
    unless the node is a heading, whose content is emitted as blocks of
    their own — every text of every nested node.

    The texts under a heading nested in a container are included: the
    container renders that heading's section itself
    (``cnd.core.render.expand_headings``), so their markers go under the
    container with the text they belong to. A heading held by a footnote
    is expanded by the converter into blocks of its own instead, each
    with its own marker line."""
    texts = [(node, text) for text in texts_of(node)]
    if not isinstance(node, HeadingNode):
        texts.extend(_nested_texts(node))
    return texts


def _nested_texts(node: CndNode) -> list[tuple[CndNode, RichText]]:
    texts: list[tuple[CndNode, RichText]] = []
    for slot in child_slots(node):
        for child in slot.nodes:
            texts.extend((child, text) for text in texts_of(child))
            texts.extend(_nested_texts(child))
    return texts


def resolve_markers(
    cnd: Cnd, node: CndNode, warnings: list[str]
) -> list[ResolvedMarker]:
    """Every forward edge of the block ``node``, resolved against the CND's
    label index.

    The edges come from ``marker_texts(node)``. Markers are ordered text
    by text, and inside a text by ``text_span`` where one exists, then by
    family (see ``ResolvedMarker.sort_key``). A label that resolves to
    nothing, or to the wrong domain for its family (docs/adr/0009),
    appends a warning naming the node that holds the edge, and comes back
    with ``target=None`` — a converter degrades, it does not refuse.
    ``links`` edges come back unresolved and never warn: an ``href`` has
    no resolution domain (spec §5).
    """
    markers: list[ResolvedMarker] = []
    for text_index, (owner, text) in enumerate(marker_texts(node)):
        for family, edges in (
            ("refs", text.refs),
            ("cites", text.cites),
            ("footnotes", text.footnotes),
        ):
            for link in edges:
                target = cnd.resolve(link.label)
                if target is None:
                    warnings.append(
                        f"unresolved {family} label {link.label!r} on node {owner.id}"
                    )
                elif not _in_domain(family, target):
                    warnings.append(
                        f"{family} label {link.label!r} on node {owner.id} resolves "
                        f"outside its family domain"
                    )
                    target = None
                markers.append(ResolvedMarker(family, link, target, text_index))
        markers.extend(
            ResolvedMarker("links", link, None, text_index) for link in text.links
        )
    markers.sort(key=lambda marker: marker.sort_key)
    return markers


def _in_domain(family: str, target: object) -> bool:
    if family == "cites":
        return isinstance(target, BibEntry)
    if family == "footnotes":
        return isinstance(target, Footnote)
    return not isinstance(target, (BibEntry, Footnote))


class CndConverter(ABC):
    """Turn a whole ``Cnd`` into one complete, standalone document.

    Subclasses supply a default ``NodeRenderer`` and the assembly. The
    renderer is injectable so a caller can trade fidelity for terseness
    (``MarkdownRenderer(tables="placeholder")``) without forking the
    converter; the converter never reaches around it for node bodies.
    """

    #: File extension of the produced artifact, without the dot.
    extension: ClassVar[str]
    #: IANA media type of the produced artifact.
    media_type: ClassVar[str]

    def __init__(self, renderer: NodeRenderer | None = None) -> None:
        self.renderer = renderer if renderer is not None else self.default_renderer()

    @classmethod
    @abstractmethod
    def default_renderer(cls) -> NodeRenderer:
        """The renderer used when the caller injects none."""

    @abstractmethod
    def convert(self, cnd: Cnd) -> ConversionResult:
        """Convert ``cnd`` into a complete standalone document."""
