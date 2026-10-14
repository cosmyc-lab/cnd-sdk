"""Node matching across two CNDs — reference algorithm "matching v2"
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
5. (v2) ``node_hash`` alone, for containers only — see below;
6. otherwise unmatched (a new node on the ``new`` side, a removed one on
   the ``old`` side).

Ties within a pass — equal-hash duplicates, two nodes competing for one
slot — break by reading order: the earliest unmatched candidate wins.

**Matching v2** (format 0.5, docs/proposals/0013) keeps the passes of v1
and changes what they run over. The matcher walks the full walk (spec
§8): every node of the body, including those inside list items, term
items, cells, quotes and admonitions, then the content of every
footnote. The structural path is the spec §8 path, so the first
paragraphs of two different cells sit in two different slots; inside a
footnote the pool index is replaced by the note's label, so reordering
the pool moves nothing. Finer nodes make the matcher finer too: an
edited list item is matched and reported on its own, where a whole list
used to be marked changed. Finally, a node hash excludes nested nodes
(spec §10), so two containers of the same shape hash alike; in the two
hash passes a list, terms, table, layout, quote or admonition is
therefore keyed on its node hash plus a digest of its descendants'
hashes, which stops a surviving container taking the id of a deleted
twin. Headings and figures are left out on purpose: their hash already
carries their text or caption, and a heading whose section changed has
not itself changed (spec §10), so a moved heading stays recognisable.
A last
pass (reported as ``hash``) then pairs the containers still unmatched on
their node hash alone, so a container whose nested content was edited and
that also shifted position keeps its id; twins have already paired
through the digest. The remaining limit: two headings or figures with identical titles can
still swap. The node hash itself is unchanged.
"""

import hashlib
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from typing import Literal, Optional

from cnd.core.cnd import BibEntry, Cnd, Footnote
from cnd.core.hashing import node_hash, pool_entry_hash
from cnd.core.nodes import CndNode, FigureNode, HeadingNode, child_slots

MATCHER_VERSION = "v2"
"""The version of the reference algorithm implemented here (docs/adr/0018)."""

MatchPass = Literal["label", "hash+path", "hash", "path+type"]
"""Which pass matched a pair."""

PASS_LABEL: MatchPass = "label"
PASS_HASH_PATH: MatchPass = "hash+path"
PASS_HASH: MatchPass = "hash"
PASS_PATH_TYPE: MatchPass = "path+type"

StructuralPath = tuple[str | int, ...]
"""A node's slot: its spec §8 path, such as ``("nodes", 0, "children", 4,
"cells", 2, "children", 0)``. Inside a footnote the pool index is
replaced by the footnote's label (``("footnotes", "fn-a", "children",
0)``): a pool is keyed by label and its order is not document order, so
reordering the pool must not move the notes' content (see ``entries``)."""


@dataclass(frozen=True)
class NodeEntry:
    """One node of a CND with everything the matcher keys on.

    ``order`` is the node's 1-based position in the full walk (the body in
    reading order, then each footnote's content) and is what breaks ties:
    the tree is normatively in reading order, so "earliest candidate" is a
    document fact rather than a walk artifact.
    """

    node: CndNode
    path: StructuralPath
    hash: str
    order: int
    subtree: str = ""
    """Digest of the hashes of every nested node, in order; empty for a
    node without child slots. A matching key only, never a content hash."""

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
    """Every node of ``cnd`` in full-walk order (the body, then each
    footnote's content), keyed for matching.

    The structural path is the traversal context's ``path``, with one
    deliberate difference: a footnote's pool index is replaced by its
    label. Pool entries match on their label and a pool has no "moved"
    (``PoolDiff``), so the content of a note must not be reported moved
    because the pool was reordered.
    """
    hashes: dict[int, str] = {}
    subtrees: dict[int, str] = {}
    result: list[NodeEntry] = []
    for order, visit in enumerate(cnd.iter_all(), start=1):
        node = visit.node
        result.append(
            NodeEntry(
                node=node,
                path=_matching_path(cnd, visit.ctx.path),
                hash=_hash_of(node, hashes),
                order=order,
                subtree=(
                    ""
                    if isinstance(node, (HeadingNode, FigureNode))
                    else _subtree_of(node, hashes, subtrees)
                ),
            )
        )
    return result


def _hash_of(node: CndNode, hashes: dict[int, str]) -> str:
    if id(node) not in hashes:
        hashes[id(node)] = node_hash(node)
    return hashes[id(node)]


def _subtree_of(
    node: CndNode, hashes: dict[int, str], subtrees: dict[int, str]
) -> str:
    """Digest of the descendants' hashes in preorder, slot by slot."""
    if id(node) in subtrees:
        return subtrees[id(node)]
    slots = child_slots(node)
    if not slots:
        subtrees[id(node)] = ""
        return ""
    parts: list[str] = []
    for slot in slots:
        parts.append("[")
        for child in slot.nodes:
            parts.append(_hash_of(child, hashes))
            parts.append(_subtree_of(child, hashes, subtrees))
        parts.append("]")
    digest = hashlib.sha256("|".join(parts).encode()).hexdigest()
    subtrees[id(node)] = digest
    return digest


def _matching_path(cnd: Cnd, path: tuple[str | int, ...]) -> StructuralPath:
    """``path`` with a footnote's pool index replaced by its label."""
    if path[0] == "footnotes":
        index = path[1]
        assert isinstance(index, int)
        return ("footnotes", cnd.footnotes[index].label, *path[2:])
    return path


def pool_entries(pool: Iterable["BibEntry | Footnote"]) -> list[PoolEntry]:
    """A pool as matchable entries, in declaration order."""
    return [PoolEntry(entry=entry, hash=pool_entry_hash(entry)) for entry in pool]


def match_nodes(old: Cnd, new: Cnd) -> NodeMatching:
    """Pair the nodes of ``old`` and ``new`` under matching v2."""
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
        (PASS_HASH, _key_container_hash),
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
    return (entry.hash, entry.subtree, entry.path)


def _key_hash(entry: NodeEntry) -> Optional[tuple]:
    return (entry.hash, entry.subtree)


def _key_container_hash(entry: NodeEntry) -> Optional[tuple]:
    """Last pass: a container that kept its own hash, whatever its nested
    content did. ``subtree`` is empty for non-containers (and for headings
    and figures), which this pass leaves alone."""
    return (entry.hash,) if entry.subtree else None


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
