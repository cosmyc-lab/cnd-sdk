"""CND validation — the invariants JSON Schema cannot express.

The schema settles shape: which fields exist, of what type. What it
cannot state is anything relational or document-wide — that a label is
unique across the whole CND, that an edge resolves in *its own* domain,
that pagination is all-or-nothing. Those are checked here.

This is the enforcement half of one contract with two enforcements of
unequal strength (docs/adr/0019): a declarative producer cannot bypass
the builder, while a direct producer can forget ``validate()``. The
asymmetry is deliberate and named rather than papered over.

The function is a value function — CND in, list of violations out — so
it crosses any boundary (docs/adr/0019 §5).
"""

from dataclasses import dataclass

from cnd.core.cnd import BibEntry, Cnd, Footnote
from cnd.core.nodes import CndNode

# The lifted bibliographic fields; an entry satisfies the content floor
# with a `formatted` string or with at least one of these.
_BIB_STRUCTURED_FIELDS = (
    "type",
    "authors",
    "title",
    "year",
    "container",
    "doi",
    "url",
    "fields",
)


@dataclass(frozen=True)
class Violation:
    """A single broken invariant.

    ``rule`` is a stable identifier a caller can branch on; ``message``
    is for humans. ``where`` names the offending node, entry or label —
    a CND has no path syntax, so it is the most specific handle
    available.
    """

    rule: str
    message: str
    where: str

    def __str__(self) -> str:
        return f"[{self.rule}] {self.where}: {self.message}"


def validate(cnd: Cnd) -> list[Violation]:
    """Every invariant this CND breaks, in a stable order. Empty means valid.

    Returns rather than raises: a producer wants the whole list, not the
    first failure, and a caller that prefers an exception can raise on a
    non-empty result. Shape errors are Pydantic's job and have already
    been raised by the time a ``Cnd`` exists.
    """
    violations: list[Violation] = []
    violations += _check_label_uniqueness(cnd)
    violations += _check_link_domains(cnd)
    violations += _check_pagination(cnd)
    violations += _check_bibliography_floor(cnd)
    return violations


def _check_label_uniqueness(cnd: Cnd) -> list[Violation]:
    """Labels are globally unique within a CND (docs/adr/0017).

    Global rather than per-domain, because that is what lets an edge name
    its target by label alone. A producer sees only its own document and
    not the label space it lands in, so collisions are the likely failure
    and must be caught rather than silently resolved to the first match.
    """
    seen: dict[str, str] = {}
    violations: list[Violation] = []

    def claim(label: str | None, owner: str) -> None:
        if label is None:
            return
        if label in seen:
            violations.append(
                Violation(
                    "label-not-unique",
                    f"label is already claimed by {seen[label]}",
                    f"@{label} on {owner}",
                )
            )
            return
        seen[label] = owner

    for visit in cnd.iter():
        claim(visit.node.label, f"{visit.node.type} {visit.node.id}")
    for entry in cnd.bibliography:
        claim(entry.label, f"bibliography entry {entry.id}")
    for note in cnd.footnotes:
        claim(note.label, f"footnote {note.id}")
    return violations


def _check_link_domains(cnd: Cnd) -> list[Violation]:
    """Each link family resolves in its own domain (docs/adr/0017).

    Existence is not enough: labels are unique across the whole CND, so a
    ``cites`` edge naming a heading resolves to *something*. The family an
    edge sits in fixes what that something must be.

    This subsumes the "a refs target must carry a label" rule — an
    unlabelled node is unreachable by any edge, so nothing can point at
    it in the first place.
    """
    violations: list[Violation] = []
    families: tuple[tuple[str, type | tuple[type, ...], str], ...] = (
        ("refs", (), "a node"),
        ("cites", BibEntry, "a bibliography entry"),
        ("footnotes", Footnote, "a footnote"),
    )
    for visit in cnd.iter():
        node = visit.node
        where = f"{node.type} {node.id}"
        for family, expected, described in families:
            for link in getattr(node, family):
                target = cnd.resolve(link.label)
                if target is None:
                    violations.append(
                        Violation(
                            "link-unresolved",
                            f"{family} edge names a label nothing carries",
                            f"@{link.label} on {where}",
                        )
                    )
                    continue
                if not _in_domain(target, expected):
                    violations.append(
                        Violation(
                            "link-wrong-domain",
                            f"{family} edge must resolve to {described}, "
                            f"got {type(target).__name__}",
                            f"@{link.label} on {where}",
                        )
                    )
    return violations


def _in_domain(target: object, expected: type | tuple[type, ...]) -> bool:
    """Whether ``target`` sits in the domain a family resolves into.

    ``refs`` points into the tree, whose members are a discriminated union
    of node classes rather than one type — it is expressed here as "not a
    pool entry", which is the same statement without enumerating a union
    that grows.
    """
    if expected == ():
        return not isinstance(target, (BibEntry, Footnote))
    return isinstance(target, expected)


def _check_pagination(cnd: Cnd) -> list[Violation]:
    """Pagination is all-or-nothing (docs/proposals/0008).

    Either every node carries a ``location`` or none does. This removes
    the "unknown page" vs. "not paginated" ambiguity without adding a
    field, and it is what makes ``Cnd.paginated`` safe to derive from the
    first node alone.
    """
    located: list[CndNode] = []
    unlocated: list[CndNode] = []
    for visit in cnd.iter():
        (located if visit.node.location is not None else unlocated).append(visit.node)

    if not located or not unlocated:
        return []

    # Report the minority — it is the anomaly, and a short list is more
    # actionable than the same finding repeated across a whole document.
    partial, expected = (
        (unlocated, "carry a location") if len(unlocated) <= len(located)
        else (located, "omit their location")
    )
    return [
        Violation(
            "pagination-partial",
            f"CND is partially paginated; these nodes should {expected}",
            f"{node.type} {node.id}",
        )
        for node in partial
    ]


def _check_bibliography_floor(cnd: Cnd) -> list[Violation]:
    """An entry must carry ``formatted``, structured fields, or both.

    ``formatted`` is nullable because a hand author has no style engine,
    and the structured fields are optional because a compiler may only
    have the rendered string. Neither being present leaves an entry a
    citation can reach but nothing can display.
    """
    return [
        Violation(
            "bib-entry-empty",
            "entry has neither `formatted` nor any structured field",
            f"@{entry.label} (bibliography entry {entry.id})",
        )
        for entry in cnd.bibliography
        if entry.formatted is None and not _has_structured_fields(entry)
    ]


def _has_structured_fields(entry: BibEntry) -> bool:
    return any(getattr(entry, name) for name in _BIB_STRUCTURED_FIELDS)
