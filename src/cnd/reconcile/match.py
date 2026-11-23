"""Node matching across two CNDs — reference algorithm "matching v3"
(docs/adr/0032, which extends docs/adr/0018 and replaces the footnote
keying of docs/adr/0029).

The matcher answers "is this the same node as in the previous build?"
for two built CNDs. It is a **versioned reference algorithm, not part of
the format**: it protects id continuity within one pipeline, a local
property, and is free to improve on its own cadence under a new version
tag. Nothing here creates a conformance obligation on a producer.

The claim it makes is deliberately narrow: **exact for labelled nodes,
best-effort for everything else**. A label is the only durable identity
CND has (docs/adr/0015), so a labelled node survives both edit and move;
an unlabelled one is recovered by heuristics that can miss (see ADR 0018,
ADR 0029 and the ``diff`` docstring for the documented failures).

**What it walks.** The full walk (spec §8): every node of the body,
including those inside list items, term items, cells, quotes and
admonitions, then the content of every footnote. The structural path is
the spec §8 path, so the first paragraphs of two different cells sit in
two different slots. Finer nodes make the matcher finer too: an edited
list item is matched and reported on its own, where a whole list used to
be marked changed.

**Footnotes first, by content** (v3). Producers often label a note with
its display number, so inserting a note renumbers every note after it: a
label is not a reliable key for a footnote. The footnote pool is
therefore matched before any node, on a digest of each note's content
(``PoolEntry.content``), the label breaking ties; a note whose content
changed falls back to its label (see ``match_pool``). Inside a footnote,
the structural path names the note: on the ``old`` side by its label, on
the ``new`` side by the label of the ``old`` note it was matched with, so
a renumbered note's content stays in place. The content of a note that
matched nothing sits under ``"new-footnotes"`` instead, a slot no ``old``
node occupies. The bibliography still matches on its label: a citation
key is chosen by the author, not numbered by the producer.

**The container key.** A node hash excludes nested nodes (spec §10), so
two containers of the same shape hash alike. A container — a list,
terms, table, layout, quote or admonition — is therefore keyed on its
node hash plus a digest of its descendants' hashes (``subtree``), which
stops a surviving container taking the id of a deleted twin. Headings
and figures are left out on purpose: their hash already carries their
text or caption, and a heading whose section changed has not itself
changed (spec §10), so a moved heading stays recognisable. Every other
node has an empty digest, and its key is its node hash alone.

The passes run strongest key first, and a node matched by an earlier
pass is never reconsidered by a later one:

1. ``label`` — exact, survives edit and move;
2. ``hash+path`` — node hash, container digest and structural path
   agree: unchanged, in place;
3. ``hash`` — node hash and container digest agree: moved but
   unchanged; recovers the nodes an insertion shifted;
4. ``path+type`` — structural path and ``type`` agree: same slot,
   edited content;
5. ``container-hash`` — for containers only, the node hash alone: a
   container whose nested content was edited and that also shifted
   keeps its id (twins have already paired through the digest in
   passes 2 and 3);
6. otherwise unmatched (a new node on the ``new`` side, a removed one on
   the ``old`` side).

Ties within a pass — equal-hash duplicates, two nodes competing for one
slot — break by reading order: the earliest unmatched candidate wins.

Known limits: two headings or figures with identical titles can swap,
and so can two twin containers that were both edited and shifted. The
combined case ADR 0018 documents (an edited node with an insertion
above it) still fails for every node that is not a container; for a
footnote, a note both renumbered and edited pairs on its label, which
may name another note. The node hash and the pool entry hash are
unchanged by any of this: every digest here is a matching key only.
"""

import hashlib
from collections.abc import Callable, Iterable
from dataclasses import dataclass, replace
from typing import Literal, Optional

from cnd.core.cnd import BibEntry, Cnd, Footnote
from cnd.core.hashing import node_hash, pool_entry_hash
from cnd.core.nodes import CndNode, FigureNode, HeadingNode, child_slots

MATCHER_VERSION = "v3"
"""The version of the reference algorithm implemented here (docs/adr/0032)."""

MatchPass = Literal["label", "hash+path", "hash", "path+type", "container-hash"]
"""Which pass matched a pair."""

PASS_LABEL: MatchPass = "label"
PASS_HASH_PATH: MatchPass = "hash+path"
PASS_HASH: MatchPass = "hash"
PASS_PATH_TYPE: MatchPass = "path+type"
PASS_CONTAINER_HASH: MatchPass = "container-hash"

PoolMatchPass = Literal["content", "label"]
"""Which pass matched a pair of pool entries."""

POOL_PASS_CONTENT: PoolMatchPass = "content"
POOL_PASS_LABEL: PoolMatchPass = "label"

NEW_FOOTNOTES = "new-footnotes"
"""The first path element of the content of a ``new`` note that matched no
``old`` note: a slot of its own, which no ``old`` node can occupy."""

StructuralPath = tuple[str | int, ...]
"""A node's slot: its spec §8 path, such as ``("nodes", 0, "children", 4,
"cells", 2, "children", 0)``. Inside a footnote the pool index is
replaced by the footnote's label (``("footnotes", "fn-a", "children",
0)``): a pool's order is not document order, so reordering the pool must
not move the notes' content (see ``entries``). When two CNDs are matched,
the ``new`` side's footnote paths name the matched ``old`` note instead
(see ``align_footnote_paths``)."""


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

    ``content`` is what the entry is matched and compared on. For a
    footnote it is a digest of its own fields except ``id`` and ``label``
    plus the hashes of every node of its content: the note's content, not
    its number. For a bibliography entry it is the pool entry hash. It is a
    matching key only, never a content hash (spec §10 is unchanged).
    """

    entry: "BibEntry | Footnote"
    hash: str
    content: str

    @property
    def label(self) -> str:
        return self.entry.label


@dataclass(frozen=True)
class PoolMatch:
    """A pair of pool entries the matcher considers the same entry."""

    old: PoolEntry
    new: PoolEntry
    matched_by: PoolMatchPass


@dataclass(frozen=True)
class PoolMatching:
    """The correspondence between two pools.

    ``matches`` is in ``new`` pool order; the unmatched lists keep their
    own side's pool order.
    """

    matches: tuple[PoolMatch, ...]
    unmatched_old: tuple[PoolEntry, ...]
    unmatched_new: tuple[PoolEntry, ...]


def entries(cnd: Cnd) -> list[NodeEntry]:
    """Every node of ``cnd`` in full-walk order (the body, then each
    footnote's content), keyed for matching.

    The structural path is the traversal context's ``path``, with one
    deliberate difference: a footnote's pool index is replaced by its
    label. A pool has no "moved" (``PoolDiff``), so the content of a note
    must not be reported moved because the pool was reordered. These are
    one CND's own paths; ``align_footnote_paths`` rewrites the ``new``
    side's against a pool matching.
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
    hashes: dict[int, str] = {}
    subtrees: dict[int, str] = {}
    result: list[PoolEntry] = []
    for entry in pool:
        entry_hash = pool_entry_hash(entry)
        content = (
            _note_content(entry, hashes, subtrees)
            if isinstance(entry, Footnote)
            else entry_hash
        )
        result.append(PoolEntry(entry=entry, hash=entry_hash, content=content))
    return result


def _note_content(
    note: Footnote, hashes: dict[int, str], subtrees: dict[int, str]
) -> str:
    """A note's matching key: its own fields but ``id`` and ``label``, then
    each content node's hash and descendants digest, in order."""
    # The label is blanked rather than dropped so the public pool entry
    # hash can be reused as is; the constant blank weighs nothing.
    parts = [pool_entry_hash(note.model_copy(update={"label": ""}))]
    for child in note.children:
        parts.append(_hash_of(child, hashes))
        parts.append(_subtree_of(child, hashes, subtrees))
    return hashlib.sha256("|".join(parts).encode()).hexdigest()


def match_nodes(
    old: Cnd, new: Cnd, footnotes: Optional[PoolMatching] = None
) -> NodeMatching:
    """Pair the nodes of ``old`` and ``new`` under matching v3.

    The footnote pool is matched first, and the ``new`` side's footnote
    paths are aligned on it (``align_footnote_paths``). A caller that also
    consumes the pool matching passes it as ``footnotes`` — the result of
    ``match_pool(old.footnotes, new.footnotes)`` — so the node alignment
    and its own use of the pool rest on one computation."""
    if footnotes is None:
        footnotes = match_pool(old.footnotes, new.footnotes)
    return match_entries(
        entries(old), align_footnote_paths(entries(new), footnotes)
    )


def align_footnote_paths(
    new_entries: list[NodeEntry], footnotes: PoolMatching
) -> list[NodeEntry]:
    """``new_entries`` with each footnote path naming the matched ``old`` note.

    The content of a note matched with an ``old`` note gets that note's
    label in its path, so a renumbered note's content sits in the same
    slot as before. The content of an unmatched note goes under
    ``NEW_FOOTNOTES``, a slot no ``old`` node occupies: its label may be
    one an ``old`` note had, and that note's content is not its own.
    """
    old_label = {match.new.label: match.old.label for match in footnotes.matches}
    aligned: list[NodeEntry] = []
    for entry in new_entries:
        path = entry.path
        if path[0] == "footnotes":
            label = path[1]
            assert isinstance(label, str)
            if label in old_label:
                path = ("footnotes", old_label[label], *path[2:])
            else:
                path = (NEW_FOOTNOTES, label, *path[2:])
            entry = replace(entry, path=path)
        aligned.append(entry)
    return aligned


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
        (PASS_CONTAINER_HASH, _key_container_hash),
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
    """Pair two pools.

    A bibliography pairs on its required ``label``, the citation key: exact.

    A footnote pool pairs in three passes, each over what the previous
    left (an entry is a footnote when either pool holds footnotes):

    1. ``content`` with the same label — the note is untouched;
    2. ``content`` alone, earliest in pool order first — the note was
       renumbered or relabelled, or moved in the pool;
    3. ``label`` alone — the note's content was edited.

    Splitting the content pass in two is what makes the label a
    tie-breaker: among identical notes, a note keeps the one that had its
    label before any other note can take it. Ties left after that break
    by pool order, so the result is deterministic.
    """
    old_entries = pool_entries(old)
    new_entries = pool_entries(new)
    if not any(
        isinstance(entry.entry, Footnote) for entry in (*old_entries, *new_entries)
    ):
        passes: tuple[tuple[PoolMatchPass, Callable[[PoolEntry], tuple]], ...] = (
            (POOL_PASS_LABEL, lambda e: (e.label,)),
        )
    else:
        passes = (
            (POOL_PASS_CONTENT, lambda e: (e.content, e.label)),
            (POOL_PASS_CONTENT, lambda e: (e.content,)),
            (POOL_PASS_LABEL, lambda e: (e.label,)),
        )

    paired: dict[int, PoolMatch] = {}
    remaining_old = list(enumerate(old_entries))
    remaining_new = list(enumerate(new_entries))
    for name, key in passes:
        buckets: dict[tuple, list[tuple[int, PoolEntry]]] = {}
        for index, entry in remaining_old:
            buckets.setdefault(key(entry), []).append((index, entry))
        taken_old: set[int] = set()
        still_new: list[tuple[int, PoolEntry]] = []
        for index, entry in remaining_new:
            bucket = buckets.get(key(entry))
            if not bucket:
                still_new.append((index, entry))
                continue
            old_index, counterpart = bucket.pop(0)
            taken_old.add(old_index)
            paired[index] = PoolMatch(old=counterpart, new=entry, matched_by=name)
        remaining_old = [(i, e) for i, e in remaining_old if i not in taken_old]
        remaining_new = still_new

    return PoolMatching(
        matches=tuple(paired[index] for index in sorted(paired)),
        unmatched_old=tuple(entry for _, entry in remaining_old),
        unmatched_new=tuple(entry for _, entry in remaining_new),
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
