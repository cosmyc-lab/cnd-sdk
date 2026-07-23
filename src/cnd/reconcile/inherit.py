"""``reconcile(new, previous) -> Cnd`` — id inheritance (docs/adr/0018).

The other half of reconciliation. Where ``diff`` *reports* the
correspondence the matcher found, this consumes it: it returns ``new``
with the ids of matched nodes and pool entries taken from ``previous``,
so a downstream store that keyed on those ids keeps its keys across a
rebuild.

**It is a standalone pass over two built CNDs, not a build parameter.**
An earlier draft exposed it as ``build(source, previous=…)``, which would
have confined it to the declarative door and forced every direct-door
producer to re-implement matching. As ``CND × CND → CND`` it is
door-agnostic — the same pass serves a CND from the builder and one a
compiler emitted directly — and it is a pure document→value function, so
it crosses a language boundary at no cost (docs/adr/0019 §5).

**Label-keyed edges make this cheap.** Because an edge names its target by
label rather than id (docs/adr/0017), the remap rewrites node and pool ids
only — it never has to chase an id through the three link families. That
is the whole reason this is a single final pass instead of a graph
rewrite.

Inheriting an id is exactly as trustworthy as the match behind it: exact
for labelled nodes, best-effort for the rest. ``reconcile`` therefore
takes the same ``matched_by`` distinction seriously as ``diff`` does — see
``only_exact``.
"""

from dataclasses import dataclass
from uuid import UUID

from cnd.core.cnd import BibEntry, Cnd, Footnote
from cnd.core.nodes import CndNode, FigureNode, HeadingNode
from cnd.reconcile.match import PASS_LABEL, match_nodes, match_pool


class ReconcileError(Exception):
    """The remap could not be applied safely.

    Raised rather than silently skipping the offending pair: a caller
    asked for id continuity, and quietly giving it partial continuity
    would leave a store with keys it cannot explain.
    """


@dataclass(frozen=True)
class Reconciliation:
    """``reconcile``'s result: the new CND plus what was done to it.

    ``inherited`` counts the ids taken from ``previous``; ``minted`` counts
    the nodes and pool entries that kept the fresh id they were built with,
    because nothing in ``previous`` matched them.
    """

    cnd: Cnd
    inherited: int
    minted: int


def reconcile(
    new: Cnd, previous: Cnd, *, only_exact: bool = False
) -> Reconciliation:
    """Return ``new`` with matched ids inherited from ``previous``.

    ``new`` is not mutated — the result is a deep copy, because a CND is an
    immutable build artifact (docs/adr/0015) and a function that rewrote
    its argument's ids in place would make the caller's own copy lie.

    ``only_exact`` restricts inheritance to pairs the **label** pass
    matched. The default is the full matcher, which is what ADR 0018
    specifies; ``only_exact=True`` is for a caller who would rather mint a
    new id than inherit one on a heuristic's word — a store where a wrong
    pairing silently merges two records, for instance.
    """
    remap: dict[UUID, UUID] = {}

    matching = match_nodes(previous, new)
    for match in matching.matches:
        if only_exact and match.matched_by != PASS_LABEL:
            continue
        remap[match.new.node.id] = match.old.node.id

    for old_pool, new_pool in (
        (previous.bibliography, new.bibliography),
        (previous.footnotes, new.footnotes),
    ):
        for old_entry, new_entry in match_pool(old_pool, new_pool).matches:
            remap[new_entry.entry.id] = old_entry.entry.id

    result = new.model_copy(deep=True)
    _check(result, remap)
    _apply(result, remap)
    total = sum(1 for _ in result.iter()) + len(result.bibliography) + len(
        result.footnotes
    )
    return Reconciliation(
        cnd=result, inherited=len(remap), minted=total - len(remap)
    )


def _check(cnd: Cnd, remap: dict[UUID, UUID]) -> None:
    """The two assertions ADR 0018 requires before any remap is applied.

    Both are properties of the *matcher*, not of this function — which is
    exactly why they are checked here rather than assumed. A matcher
    version that broke either would otherwise corrupt a document silently
    instead of failing loudly.
    """
    inherited = list(remap.values())
    if len(set(inherited)) != len(inherited):
        duplicates = {i for i in inherited if inherited.count(i) > 1}
        raise ReconcileError(
            "the remap is not injective: "
            f"{len(duplicates)} previous id(s) claimed by more than one node "
            f"(first: {next(iter(duplicates))})"
        )

    # An id that stays fresh must not equal one being inherited, or two
    # distinct nodes would end up sharing it and global id uniqueness
    # (spec §2) would break.
    kept = {
        holder_id
        for holder_id in _all_ids(cnd)
        if holder_id not in remap
    }
    collisions = kept & set(inherited)
    if collisions:
        raise ReconcileError(
            "an inherited id collides with a freshly minted one: "
            f"{sorted(str(c) for c in collisions)[:3]}"
        )


def _all_ids(cnd: Cnd) -> set[UUID]:
    return (
        {visit.node.id for visit in cnd.iter()}
        | {entry.id for entry in cnd.bibliography}
        | {note.id for note in cnd.footnotes}
    )


def _apply(cnd: Cnd, remap: dict[UUID, UUID]) -> None:
    """Rewrite ids in place on the already-copied CND.

    Nodes and pool entries only: the link families carry labels, so no
    edge needs touching (docs/adr/0017).
    """
    for node in _walk(cnd.nodes):
        replacement = remap.get(node.id)
        if replacement is not None:
            node.id = replacement
    for entry in (*cnd.bibliography, *cnd.footnotes):
        replacement = remap.get(entry.id)
        if replacement is not None:
            entry.id = replacement


def _walk(nodes: list[CndNode]):
    """Every node in the tree. A plain recursive walk rather than
    ``Cnd.iter``: that one caches derived positions on the instance, and
    rewriting ids underneath a cache invites a stale one."""
    for node in nodes:
        yield node
        if isinstance(node, (HeadingNode, FigureNode)):
            yield from _walk(node.children)


__all__ = ["ReconcileError", "Reconciliation", "reconcile"]
