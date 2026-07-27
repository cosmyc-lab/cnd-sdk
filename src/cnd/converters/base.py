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
    FigureNode,
    FootnoteRef,
    NodeRef,
    NodeTraverse,
    NodeTraverseContext,
)
from cnd.core.render import NodeRenderer

__all__ = [
    "ConversionResult",
    "CndConverter",
    "ResolvedMarker",
    "format_date",
    "iter_body",
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
    """One forward edge of a node paired with what its label resolved to.

    ``target`` is ``None`` when the label resolves to nothing, which is a
    document defect (``validate()`` reports it) that a converter reports
    rather than raises on. ``sort_key`` orders markers in text order when
    ``text_span`` is available, per spec §8: the enumeration order of the
    families carries no positional claim, and the only positional truth
    about a marker is its span.
    """

    family: str
    link: NodeRef | CiteRef | FootnoteRef
    target: object | None

    @property
    def label(self) -> str:
        return self.link.label

    @property
    def sort_key(self) -> tuple[int, int, int]:
        span = self.link.text_span
        family_rank = {"refs": 0, "cites": 1, "footnotes": 2}[self.family]
        if span:
            return (0, span[0], family_rank)
        return (1, family_rank, 0)


def iter_body(cnd: Cnd) -> Iterator[NodeTraverse]:
    """Walk the body of ``cnd`` in reading order, one visit per emitted block.

    Figures are yielded but their subtree is pruned: a figure is a
    wrapper node (docs/adr/0010) and a renderer's ``render_figure``
    already owns its children, so descending into them would emit the
    wrapped content twice. Headings are descended into normally — a
    renderer emits only the heading line for them.

    The pools do not enter reading order (spec §8) and are therefore not
    part of this walk; a converter emits them as its own sections.
    """
    return cnd.iter(stop_predicate=_prune_figure_children)


def _prune_figure_children(node: CndNode, ctx: NodeTraverseContext) -> bool:
    return isinstance(node, FigureNode)


def resolve_markers(
    cnd: Cnd, node: CndNode, warnings: list[str]
) -> list[ResolvedMarker]:
    """Every forward edge of ``node``, resolved against the CND's label index.

    Returns the markers in text order where ``text_span`` says so, and in
    the ``refs``, ``cites``, ``footnotes`` family order otherwise. A label
    that resolves to nothing, or to the wrong domain for its family
    (docs/adr/0009), appends a warning and comes back with
    ``target=None`` — a converter degrades, it does not refuse.
    """
    markers: list[ResolvedMarker] = []
    for family, links in (
        ("refs", node.refs),
        ("cites", node.cites),
        ("footnotes", node.footnotes),
    ):
        for link in links:
            target = cnd.resolve(link.label)
            if target is None:
                warnings.append(
                    f"unresolved {family} label {link.label!r} on node {node.id}"
                )
            elif not _in_domain(family, target):
                warnings.append(
                    f"{family} label {link.label!r} on node {node.id} resolves "
                    f"outside its family domain"
                )
                target = None
            markers.append(ResolvedMarker(family=family, link=link, target=target))
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
