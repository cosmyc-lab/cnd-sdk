"""Node matching across two CNDs — reference algorithm "matching v1"
(docs/adr/0018).

The matcher answers "is this the same node as in the previous build?"
for two built CNDs. It is a **versioned reference algorithm, not part of
the format**: it protects id continuity within one pipeline, a local
property, and is free to improve on its own cadence under a new version
tag. Nothing here creates a conformance obligation on a producer.

The claim it makes is deliberately narrow: **exact for labelled nodes,
best-effort for everything else**. A label is the only durable identity
CND has (docs/adr/0015), so a labelled node survives both edit and move;
an unlabelled one is recovered by heuristics that can miss (see
``ADR 0018`` and the ``diff`` docstring for the documented failure).

The passes run strongest key first, and a node matched by an earlier
pass is never reconsidered by a later one:

1. ``label`` — exact, survives edit and move;
2. ``node_hash`` + structural path — unchanged, in place;
3. ``node_hash`` alone — moved but unchanged; recovers the nodes an
   insertion shifted;
4. structural path + ``type`` — same slot, edited content;
5. otherwise unmatched (a new node on the ``new`` side, a removed one on
   the ``old`` side).

Ties within a pass — equal-hash duplicates, two nodes competing for one
slot — break by reading order: the earliest unmatched candidate wins.
"""

from collections.abc import Callable, Iterable
from dataclasses import dataclass
from typing import Literal, Optional

from cnd.core.cnd import BibEntry, Cnd, Footnote
from cnd.core.hashing import node_hash, pool_entry_hash
from cnd.core.nodes import CndNode

MATCHER_VERSION = "v1"
"""The version of the reference algorithm implemented here (docs/adr/0018)."""

MatchPass = Literal["label", "hash+path", "hash", "path+type"]
"""Which pass matched a pair."""

PASS_LABEL: MatchPass = "label"
PASS_HASH_PATH: MatchPass = "hash+path"
PASS_HASH: MatchPass = "hash"
PASS_PATH_TYPE: MatchPass = "path+type"

StructuralPath = tuple[int, ...]
"""A node's slot in the tree: 1-based sibling indices from the root down."""


@dataclass(frozen=True)
class NodeEntry:
    """One node of a CND with everything the matcher keys on.

    ``order`` is the node's 1-based position in reading order and is what
    breaks ties: the tree is normatively in reading order, so "earliest
    candidate" is a document fact rather than a walk artifact.
    """

    node: CndNode
    path: StructuralPath
    hash: str
    order: int

    @property
    def label(self) -> Optional[str]:
        return self.node.label

    @property
    def type(self) -> str:
        return self.node.type


@dataclass(frozen=True)
class NodeMatch:
    """A pair of nodes the matcher considers the same node."""

    old: NodeEntry
    new: NodeEntry
    matched_by: MatchPass


@dataclass(frozen=True)
class NodeMatching:
    """The full correspondence between two CNDs' node trees.

    ``matches`` is in ``new``-side reading order; the unmatched lists keep
    their own side's reading order.
    """

    matches: tuple[NodeMatch, ...]
    unmatched_old: tuple[NodeEntry, ...]
    unmatched_new: tuple[NodeEntry, ...]
    version: str = MATCHER_VERSION


@dataclass(frozen=True)
class PoolEntry:
    """One out-of-tree pool entry (bibliography or footnote) with its hash.

    A pool entry's ``label`` is required by the format, so pool matching is
    exact by construction — no heuristic ever runs on a pool.
    """

    entry: "BibEntry | Footnote"
    hash: str

    @property
    def label(self) -> str:
        return self.entry.label


@dataclass(frozen=True)
class PoolMatching:
    """The label-keyed correspondence between two pools."""

    matches: tuple[tuple[PoolEntry, PoolEntry], ...]
    unmatched_old: tuple[PoolEntry, ...]
    unmatched_new: tuple[PoolEntry, ...]


def entries(cnd: Cnd) -> list[NodeEntry]:
    """Every node of ``cnd`` in reading order, keyed for matching.

    The structural path is derived from the traversal context rather than
    from a second walk: the walk is depth-first pre-order, so truncating
    the running path to the current depth and appending the sibling index
    yields the absolute slot of every node.
    """
    result: list[NodeEntry] = []
    path: list[int] = []
    for order, visit in enumerate(cnd.iter(), start=1):
        del path[visit.ctx.depth :]
        path.append(visit.ctx.sibling_index)
        result.append(
            NodeEntry(
                node=visit.node,
                path=tuple(path),
                hash=node_hash(visit.node),
                order=order,
            )
        )
    return result


def pool_entries(pool: Iterable["BibEntry | Footnote"]) -> list[PoolEntry]:
    """A pool as matchable entries, in declaration order."""
    return [PoolEntry(entry=entry, hash=pool_entry_hash(entry)) for entry in pool]


def match_nodes(old: Cnd, new: Cnd) -> NodeMatching:
    """Pair the nodes of ``old`` and ``new`` under matching v1."""
    return match_entries(entries(old), entries(new))


def match_entries(
    old_entries: list[NodeEntry], new_entries: list[NodeEntry]
) -> NodeMatching:
    """The matcher proper, over pre-computed entries.

    Split out from ``match_nodes`` so a caller that already walked both
    CNDs — a diff computing statuses over the same entries — does not walk
    and hash them twice.
    """
    matches: list[NodeMatch] = []
    remaining_old = list(old_entries)
    remaining_new = list(new_entries)

    for name, key in (
        (PASS_LABEL, _key_label),
        (PASS_HASH_PATH, _key_hash_path),
        (PASS_HASH, _key_hash),
        (PASS_PATH_TYPE, _key_path_type),
    ):
        paired, remaining_old, remaining_new = _run_pass(
            remaining_old, remaining_new, key
        )
        matches.extend(
            NodeMatch(old=old_entry, new=new_entry, matched_by=name)
            for old_entry, new_entry in paired
        )
        if not remaining_old or not remaining_new:
            break

    matches.sort(key=lambda match: match.new.order)
    return NodeMatching(
        matches=tuple(matches),
        unmatched_old=tuple(remaining_old),
        unmatched_new=tuple(remaining_new),
    )


def match_pool(
    old: Iterable["BibEntry | Footnote"], new: Iterable["BibEntry | Footnote"]
) -> PoolMatching:
    """Pair two pools on their required ``label`` — exact, never heuristic."""
    old_entries = pool_entries(old)
    new_entries = pool_entries(new)
    by_label = {entry.label: entry for entry in old_entries}

    matches: list[tuple[PoolEntry, PoolEntry]] = []
    unmatched_new: list[PoolEntry] = []
    matched_labels: set[str] = set()
    for entry in new_entries:
        counterpart = by_label.get(entry.label)
        if counterpart is None:
            unmatched_new.append(entry)
            continue
        matches.append((counterpart, entry))
        matched_labels.add(entry.label)

    return PoolMatching(
        matches=tuple(matches),
        unmatched_old=tuple(
            entry for entry in old_entries if entry.label not in matched_labels
        ),
        unmatched_new=tuple(unmatched_new),
    )


_KeyFn = Callable[[NodeEntry], Optional[tuple]]


def _key_label(entry: NodeEntry) -> Optional[tuple]:
    return None if entry.label is None else (entry.label,)


def _key_hash_path(entry: NodeEntry) -> Optional[tuple]:
    return (entry.hash, entry.path)


def _key_hash(entry: NodeEntry) -> Optional[tuple]:
    return (entry.hash,)


def _key_path_type(entry: NodeEntry) -> Optional[tuple]:
    return (entry.path, entry.type)


def _run_pass(
    old_entries: list[NodeEntry], new_entries: list[NodeEntry], key: _KeyFn
) -> tuple[list[tuple[NodeEntry, NodeEntry]], list[NodeEntry], list[NodeEntry]]:
    """One pass: pair the entries whose ``key`` agrees, return the rest.

    Candidates are consumed in reading order, which is the tie-break rule:
    with two equal-hash duplicates on each side, the first ``new`` node
    takes the first ``old`` one.
    """
    buckets: dict[tuple, list[NodeEntry]] = {}
    for entry in old_entries:
        entry_key = key(entry)
        if entry_key is not None:
            buckets.setdefault(entry_key, []).append(entry)

    paired: list[tuple[NodeEntry, NodeEntry]] = []
    matched_old: set[int] = set()
    remaining_new: list[NodeEntry] = []
    for entry in new_entries:
        candidate = _take(buckets, key(entry))
        if candidate is None:
            remaining_new.append(entry)
            continue
        paired.append((candidate, entry))
        matched_old.add(candidate.order)

    remaining_old = [
        entry for entry in old_entries if entry.order not in matched_old
    ]
    return paired, remaining_old, remaining_new


def _take(
    buckets: dict[tuple, list[NodeEntry]], entry_key: Optional[tuple]
) -> Optional[NodeEntry]:
    """Pop the earliest unconsumed candidate for ``entry_key``, if any."""
    if entry_key is None:
        return None
    bucket = buckets.get(entry_key)
    if not bucket:
        return None
    return bucket.pop(0)
