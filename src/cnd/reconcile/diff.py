"""``diff(old, new) -> CndDiff`` — what moved between two builds
(docs/adr/0018; the ``moved`` rule is matching v3's, docs/adr/0032).

A CND carries no version history: it is an immutable build artifact and
its node ids are not durable (docs/adr/0015). A consumer that keeps the
CNDs it calls versions gets versioning back from this function, which
reports the correspondence the matcher found and classifies it.

The classification of a matched pair, in this order — a node is never
both:

- ``changed`` — matched, ``node_hash`` differs;
- ``moved`` — matched, hash equal, and the node was **re-parented** or
  **reordered** (below);
- ``unchanged`` — matched, hash equal, neither re-parented nor
  reordered.

An unmatched node is ``added`` on the ``new`` side and ``removed`` on the
``old`` side.

**What counts as a move.** A node's parent is the node whose slot holds
it, the body for a top-level node, or its note for a footnote's content.

- *Re-parented*: the ``new`` node's parent is not the counterpart of the
  ``old`` node's parent (an unmatched parent is nobody's counterpart; a
  note's counterpart is the note the pool matching paired it with). Also
  re-parented: a node that changed item or cell inside a parent whose own
  hash is equal — that parent kept its items or cells, so they line up
  one to one, and changing cell is changing place.
- *Reordered*: among the matched siblings that share a parent on both
  sides, taken in ``new`` order, keep a longest run whose ``old`` order
  is increasing; every sibling outside it is reordered. Among several
  longest runs, the one that keeps the earliest ``new`` siblings wins, so
  in a swap of two siblings the later one in ``new`` order is reported.

A node merely shifted by an insertion or a removal before it is neither:
the sibling index in its path changed, its order relative to its matched
siblings did not. Before matching v3 any path difference was a move,
which reported every node after an insertion as moved.
"""

from bisect import bisect_left
from dataclasses import dataclass
from typing import Literal, Optional

from cnd.core.cnd import Cnd
from cnd.reconcile.match import (
    MATCHER_VERSION,
    NEW_FOOTNOTES,
    MatchPass,
    NodeEntry,
    NodeMatch,
    PoolEntry,
    PoolMatching,
    PoolMatchPass,
    StructuralPath,
    align_footnote_paths,
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
    """One pool entry's fate.

    ``label`` is the ``new`` entry's label, or the ``old`` one's for a
    removed entry; a renumbered footnote's previous label is
    ``old.label``. ``matched_by`` names the pool pass that paired a
    matched entry (``match_pool``).

    A matched entry is ``unchanged`` when its ``content`` key is equal:
    for a footnote, its content and its fields other than ``label``, so a
    renumbered note is unchanged; for a bibliography entry, its hash.
    """

    status: PoolStatus
    label: str
    old: Optional[PoolEntry] = None
    new: Optional[PoolEntry] = None
    matched_by: Optional[PoolMatchPass] = None


@dataclass(frozen=True)
class PoolDiff:
    """The diff of one out-of-tree pool (bibliography or footnotes).

    A pool has no ``moved``: an entry's order in the pool is not document
    order — entries sit out of the tree, and reordering them changes
    nothing a reader sees.
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
    its predecessor ``removed``. Matching v2 (docs/adr/0029) rescues
    containers whose own hash survived, through its ``container-hash``
    pass; every other node still fails this way. This is the diff
    problem, not an oversight — sequence-alignment tools do better and
    still miss. The claim stays best-effort for unlabelled nodes and
    exact for labelled ones; a producer that wants certainty labels the
    node.
    """
    footnotes = match_pool(old.footnotes, new.footnotes)
    old_entries = entries(old)
    new_entries = align_footnote_paths(entries(new), footnotes)
    matching = match_entries(old_entries, new_entries)
    moved = _moved(matching.matches, old_entries, new_entries)

    changes_by_order: dict[int, NodeChange] = {}
    for match in matching.matches:
        changes_by_order[match.new.order] = NodeChange(
            status=_status(match, moved),
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
        bibliography=_pool_diff(match_pool(old.bibliography, new.bibliography)),
        footnotes=_pool_diff(footnotes),
    )


def _status(match: NodeMatch, moved: set[int]) -> NodeStatus:
    """The status of a matched pair. ``changed`` dominates ``moved``: a
    node that was edited *and* moved is reported as edited, since the
    edit is the fact a consumer acts on."""
    if match.old.hash != match.new.hash:
        return "changed"
    if match.new.order in moved:
        return "moved"
    return "unchanged"


_ROOT = ("nodes",)
_NOTE_ROOTS = ("footnotes", NEW_FOOTNOTES)


def _parent(path: StructuralPath) -> tuple[StructuralPath, Optional[int]]:
    """The path of the slot owner holding ``path``, and the item or cell
    index when that owner is a list, terms, table or layout.

    The owner is the body (``("nodes",)``), a note
    (``("footnotes", label)``) or a node (its path)."""
    if path[0] == "nodes" and len(path) == 2:
        return _ROOT, None
    if path[0] in _NOTE_ROOTS and len(path) == 4:
        return path[:2], None
    if len(path) >= 4 and path[-4] in ("items", "cells"):
        index = path[-3]
        assert isinstance(index, int)
        return path[:-4], index
    return path[:-2], None


def _moved(
    matches: tuple[NodeMatch, ...],
    old_entries: list[NodeEntry],
    new_entries: list[NodeEntry],
) -> set[int]:
    """The ``new`` orders of the matched nodes that moved (module
    docstring: re-parented or reordered)."""
    old_by_path = {entry.path: entry for entry in old_entries}
    new_by_path = {entry.path: entry for entry in new_entries}
    counterpart = {match.new.order: match.old.order for match in matches}

    def owner_old(path: StructuralPath) -> tuple:
        if path == _ROOT or path[0] in _NOTE_ROOTS and len(path) == 2:
            return ("slot", path)
        return ("node", old_by_path[path].order)

    def owner_new(path: StructuralPath) -> tuple:
        if path == _ROOT or path[0] in _NOTE_ROOTS and len(path) == 2:
            # Footnote paths are aligned: a matched note already carries
            # its counterpart's label, an unmatched one cannot equal any.
            return ("slot", path)
        order = counterpart.get(new_by_path[path].order)
        return ("node", order) if order is not None else ("unmatched", path)

    moved: set[int] = set()
    siblings: dict[tuple, list[tuple[int, tuple[int, ...]]]] = {}
    for match in matches:
        old_parent, old_slot = _parent(match.old.path)
        new_parent, new_slot = _parent(match.new.path)
        owner = owner_new(new_parent)
        if owner != owner_old(old_parent):
            moved.add(match.new.order)
            continue
        if old_slot != new_slot and owner[0] == "node":
            if old_by_path[old_parent].hash == new_by_path[new_parent].hash:
                moved.add(match.new.order)
                continue
        # The old position inside the parent: item or cell index first,
        # then the child index — comparable across slots of one parent.
        position = tuple(
            step
            for step in match.old.path[len(old_parent):]
            if isinstance(step, int)
        )
        siblings.setdefault(owner, []).append((match.new.order, position))

    for group in siblings.values():
        group.sort()
        kept = _earliest_longest_increasing([position for _, position in group])
        moved.update(
            order for index, (order, _) in enumerate(group) if index not in kept
        )
    return moved


def _earliest_longest_increasing(keys: list[tuple[int, ...]]) -> set[int]:
    """Indices of a longest strictly increasing subsequence of ``keys``,
    the one that is lexicographically smallest in indices: it keeps the
    earliest elements wherever there is a choice. O(n log n).

    ``keys`` are distinct. ``longest[i]`` is the length of the longest
    increasing run starting at ``i``, computed right to left as a longest
    decreasing run ending at ``i``; a greedy left-to-right pick of the
    first index able to continue a run of the remaining length then yields
    the earliest one."""
    longest = [0] * len(keys)
    tails: list[tuple[int, ...]] = []
    for i in range(len(keys) - 1, -1, -1):
        negated = tuple(-k for k in keys[i])
        at = bisect_left(tails, negated)
        if at == len(tails):
            tails.append(negated)
        else:
            tails[at] = negated
        longest[i] = at + 1

    kept: set[int] = set()
    need = max(longest, default=0)
    last: Optional[tuple[int, ...]] = None
    for i, key in enumerate(keys):
        if need and longest[i] == need and (last is None or key > last):
            kept.add(i)
            last = key
            need -= 1
    return kept


def _pool_diff(matching: PoolMatching) -> PoolDiff:
    changes = [
        PoolChange(
            status=(
                "unchanged"
                if match.old.content == match.new.content
                else "changed"
            ),
            label=match.new.label,
            old=match.old,
            new=match.new,
            matched_by=match.matched_by,
        )
        for match in matching.matches
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
