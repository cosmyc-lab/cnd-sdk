"""Derived content hashing (docs/adr/0016).

A content hash answers "did this change?" for any consumer, independent
of producer. It is **derived, never serialised** — data a consumer can
compute from what the CND necessarily contains is not a field, the same
line the format draws for reverse edges (docs/adr/0008) and positions
(docs/adr/0012).

Do not confuse it with ``Cnd.source.hash``, which is a producer-supplied
digest of the *input artifact* and is only comparable between two CNDs
from the same producer over the same source.

**What is hashed.** Content, and nothing a producer resolved for
display. Excluded under the current field set: the node ``id``, its
``location``, the resolved ``number``, its ``counter_label``, and the
CND's ``built_at``, ``source`` and ``cnd_version``. The exclusion is a principle plus a
list, so the list is maintained as the field set evolves. The ``number``
case is the one that would otherwise break silently: inserting a heading
renumbers everything after it, so a hash covering ``number`` would
report every following node as changed.

**Canonicalisation.** RFC 8785 (JCS) over the hashable subset, with
strings normalised to Unicode NFC first. Both are external references
rather than a bespoke scheme, so an implementation in any language can
reproduce the bytes — which is the whole point of defining this
normatively.

A hash is change-detection, not identity: two identical paragraphs in
one document share a hash, and this module makes no identity claim for
that.
"""

import hashlib
import unicodedata
from typing import Any

import rfc8785

from cnd.core.cnd import BibEntry, Cnd, Footnote
from cnd.core.nodes import CndNode

ALGORITHM = "sha256"

# Resolved presentation state — computed for display, changes without the
# authored content changing. `children` is excluded for a different
# reason: see `node_hash`.
_EXCLUDED_NODE_FIELDS = frozenset(
    {"id", "location", "number", "counter_label", "children"}
)


def node_hash(node: CndNode) -> str:
    """The content hash of a single node, as ``"sha256:<hex>"``.

    ``counter_label`` is excluded alongside ``number``: it is the same
    resolved presentation state, and it changes when the document language
    changes without the authored content changing.

    **Node-local**: a node's children are not hashed into it. A heading
    whose subsection changed has not itself changed, and treating it as
    changed would defeat the reconciliation pass that recognises a
    moved-but-unchanged node (docs/adr/0018). The tree as a whole is
    covered by ``content_hash``, which folds every node's hash.
    """
    payload = node.model_dump(mode="json", exclude=_EXCLUDED_NODE_FIELDS)
    return _digest(payload)


def content_hash(cnd: Cnd) -> str:
    """The content hash of a whole CND, as ``"sha256:<hex>"``.

    Folds every node hash in reading order, both out-of-tree pools, and
    the ``doc`` metadata.

    Each node's hash is paired with its depth, because nesting is
    structure and not presentation — re-parenting a section under a
    different heading changes the document even though the reading order
    and every node-local hash are untouched.

    **The pools are content.** A footnote's text and a bibliography
    entry's fields are authored material; leaving them out would let a
    rewritten footnote pass as an unchanged document — a silent
    false negative of exactly the kind excluding ``number`` is meant to
    avoid in the other direction. They sit out of the tree for
    referencing reasons, not because they are metadata.

    Excluded: ``built_at``, ``source`` and ``cnd_version``. The same
    content built twice, reached from two different input formats, or
    expressed under two format versions is the same content;
    ``source.hash`` answers the separate question of whether the input
    artifact moved.
    """
    payload = {
        "doc": cnd.doc.model_dump(mode="json"),
        "nodes": [[visit.ctx.depth, node_hash(visit.node)] for visit in cnd.iter()],
        "bibliography": [_pool_entry_hash(entry) for entry in cnd.bibliography],
        "footnotes": [_pool_entry_hash(note) for note in cnd.footnotes],
    }
    return _digest(payload)


def _pool_entry_hash(entry: BibEntry | Footnote) -> str:
    """The content hash of one pool entry.

    Only ``id`` is excluded — non-durable, like a node's (docs/adr/0015).
    A pool entry carries no resolved presentation state of its own: it
    has no ``location`` and no ``number``, so the exclusion set is
    narrower than a node's rather than the same one reused.
    """
    return _digest(entry.model_dump(mode="json", exclude={"id"}))


def _digest(payload: Any) -> str:
    canonical = rfc8785.dumps(_normalise(payload))
    return f"{ALGORITHM}:{hashlib.sha256(canonical).hexdigest()}"


def _normalise(value: Any) -> Any:
    """Recursively normalise strings to Unicode NFC.

    Applied to keys as well as values: two producers can emit the same
    field name in different normal forms, and JCS orders keys by their
    code units, so an unnormalised key would both order and serialise
    differently for the same name.
    """
    if isinstance(value, str):
        return unicodedata.normalize("NFC", value)
    if isinstance(value, dict):
        return {_normalise(k): _normalise(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_normalise(item) for item in value]
    return value
