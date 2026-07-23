"""``diff(old, new) -> CndDiff`` — what moved between two builds
(docs/adr/0018).

A CND carries no version history: it is an immutable build artifact and
its node ids are not durable (docs/adr/0015). A consumer that keeps the
CNDs it calls versions gets versioning back from this function, which
reports the correspondence the matcher found and classifies it.

The classification of a matched pair, in this order — a node is never
both:

- ``changed`` — matched, ``node_hash`` differs;
- ``moved`` — matched, hash equal, structural path differs;
- ``unchanged`` — matched, hash and path equal.

An unmatched node is ``added`` on the ``new`` side and ``removed`` on the
``old`` side.
"""

from dataclasses import dataclass
from typing import Literal, Optional

from cnd.core.cnd import BibEntry, Cnd, Footnote
from cnd.reconcile.match import (
    MATCHER_VERSION,
    MatchPass,
    NodeEntry,
    PoolEntry,
    entries,
    match_entries,
    match_pool,
)

NodeStatus = Literal["added", "removed", "changed", "moved", "unchanged"]
PoolStatus = Literal["added", "removed", "changed", "unchanged"]


@dataclass(frozen=True)
class NodeChange:
    """One node's fate between the two builds.

    ``old`` is ``None`` for an added node, ``new`` is ``None`` for a
    removed one; both are present otherwise. ``matched_by`` names the
    matcher pass that paired them, which is what tells a caller how much
    to trust the pairing: ``"label"`` is exact, the rest are heuristics.
    """

    status: NodeStatus
    old: Optional[NodeEntry] = None
    new: Optional[NodeEntry] = None
    matched_by: Optional[MatchPass] = None


@dataclass(frozen=True)
class PoolChange:
    """One pool entry's fate, keyed on its required label."""

    status: PoolStatus
    label: str
    old: Optional[PoolEntry] = None
    new: Optional[PoolEntry] = None


@dataclass(frozen=True)
class PoolDiff:
    """The diff of one out-of-tree pool (bibliography or footnotes).

    A pool has no ``moved``: entries are keyed by label and their order in
    the pool is not document order — they sit out of the tree, and
    reordering them changes nothing a reader sees.
    """

    changes: tuple[PoolChange, ...]

    @property
    def added(self) -> tuple[PoolChange, ...]:
        return self._of("added")

    @property
    def removed(self) -> tuple[PoolChange, ...]:
        return self._of("removed")

    @property
    def changed(self) -> tuple[PoolChange, ...]:
        return self._of("changed")

    @property
    def unchanged(self) -> tuple[PoolChange, ...]:
        return self._of("unchanged")

    def _of(self, status: PoolStatus) -> tuple[PoolChange, ...]:
        return tuple(change for change in self.changes if change.status == status)


@dataclass(frozen=True)
class CndDiff:
    """The result of ``diff(old, new)``.

    ``nodes`` is ordered: the nodes present in ``new`` first, in ``new``
    reading order, then the removed ones in ``old`` reading order. The
    status properties filter it and preserve that order.
    """

    nodes: tuple[NodeChange, ...]
    bibliography: PoolDiff
    footnotes: PoolDiff
    matcher_version: str = MATCHER_VERSION

    @property
    def added(self) -> tuple[NodeChange, ...]:
        return self._of("added")

    @property
    def removed(self) -> tuple[NodeChange, ...]:
        return self._of("removed")

    @property
    def changed(self) -> tuple[NodeChange, ...]:
        return self._of("changed")

    @property
    def moved(self) -> tuple[NodeChange, ...]:
        return self._of("moved")

    @property
    def unchanged(self) -> tuple[NodeChange, ...]:
        return self._of("unchanged")

    @property
    def is_empty(self) -> bool:
        """Whether the two CNDs' content corresponds exactly.

        True when every node and every pool entry is ``unchanged``. It is
        not a content-equality test: ``content_hash`` answers that
        question directly and more cheaply (docs/adr/0016).
        """
        return all(change.status == "unchanged" for change in self.nodes) and all(
            change.status == "unchanged"
            for pool in (self.bibliography, self.footnotes)
            for change in pool.changes
        )

    def _of(self, status: NodeStatus) -> tuple[NodeChange, ...]:
        return tuple(change for change in self.nodes if change.status == status)


def diff(old: Cnd, new: Cnd) -> CndDiff:
    """Classify every node and pool entry of ``new`` against ``old``.

    **Documented limitation** (docs/adr/0018). The combined case defeats
    the heuristic: a node that is both edited *and* shifted by an
    insertion above it misses the hash passes (its content changed) and
    the path pass (its slot moved), so it is reported as ``added`` with
    its predecessor ``removed``. This is the diff problem, not an
    oversight — sequence-alignment tools do better and still miss. The
    claim stays best-effort for unlabelled nodes and exact for labelled
    ones; a producer that wants certainty labels the node.
    """
    old_entries = entries(old)
    new_entries = entries(new)
    matching = match_entries(old_entries, new_entries)

    changes_by_order: dict[int, NodeChange] = {}
    for match in matching.matches:
        changes_by_order[match.new.order] = NodeChange(
            status=_status(match.old, match.new),
            old=match.old,
            new=match.new,
            matched_by=match.matched_by,
        )
    for entry in matching.unmatched_new:
        changes_by_order[entry.order] = NodeChange(status="added", new=entry)

    nodes = [changes_by_order[entry.order] for entry in new_entries]
    nodes.extend(
        NodeChange(status="removed", old=entry) for entry in matching.unmatched_old
    )

    return CndDiff(
        nodes=tuple(nodes),
        bibliography=_pool_diff(old.bibliography, new.bibliography),
        footnotes=_pool_diff(old.footnotes, new.footnotes),
    )


def _status(old: NodeEntry, new: NodeEntry) -> NodeStatus:
    """The status of a matched pair. ``changed`` dominates ``moved``: a
    node that was edited *and* shifted is reported as edited, since the
    edit is the fact a consumer acts on."""
    if old.hash != new.hash:
        return "changed"
    if old.path != new.path:
        return "moved"
    return "unchanged"


def _pool_diff(
    old: list[BibEntry] | list[Footnote], new: list[BibEntry] | list[Footnote]
) -> PoolDiff:
    matching = match_pool(old, new)
    changes = [
        PoolChange(
            status="unchanged" if old_entry.hash == new_entry.hash else "changed",
            label=new_entry.label,
            old=old_entry,
            new=new_entry,
        )
        for old_entry, new_entry in matching.matches
    ]
    changes.extend(
        PoolChange(status="added", label=entry.label, new=entry)
        for entry in matching.unmatched_new
    )
    changes.extend(
        PoolChange(status="removed", label=entry.label, old=entry)
        for entry in matching.unmatched_old
    )
    return PoolDiff(changes=tuple(changes))
