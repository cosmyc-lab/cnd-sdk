"""Derived content hashing (docs/adr/0016).

A content hash answers "did this change?" for any consumer, independent
of producer. It is **derived, never serialised** — data a consumer can
compute from what the CND necessarily contains is not a field, the same
line the format draws for reverse edges (docs/adr/0008) and positions
(docs/adr/0012).

Do not confuse it with ``Cnd.source.hash``, which is a producer-supplied
digest of the *input artifact* and is only comparable between two CNDs
from the same producer over the same source.

**What is hashed.** Three rules (docs/proposals/0013):

1. *Defaults are dropped.* The preimage holds only the fields a producer
   set to a non-default value, so an omitted empty list and a written one
   hash the same, and a future optional field cannot move an existing
   hash.
2. *Nested nodes are excluded.* A node's hash is node-local: the
   ``children`` of the node and of its list items, term items and cells
   are not part of it. The tree is covered by ``content_hash``.
3. *Resolved presentation state is excluded:* the node ``id``, its
   ``location`` and its ``numbering`` (inserting a heading renumbers
   everything after it, so a hash covering ``numbering`` would report
   every following node as changed), and the CND's ``built_at``,
   ``source`` and ``cnd_version``.

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
# authored content changing.
_EXCLUDED_NODE_FIELDS = frozenset({"id", "location", "numbering"})
# Container entries whose `children` hold nested nodes (principle 2).
_CONTAINER_ENTRY_FIELDS = ("items", "cells")


def node_hash(node: CndNode) -> str:
    """The content hash of a single node, as ``"sha256:<hex>"``.

    Over the node's own fields with every default-valued field dropped
    (docs/proposals/0013): an omitted empty list and a written one hash the
    same, and a future optional field cannot move an existing hash.

    **Node-local.** Every nested node is excluded, wherever it sits — the
    node's ``children`` and the ``children`` of its list items, term items
    and cells. A list whose item text changed has not itself changed; the
    item's paragraph has. Only those structural keys are stripped: a
    ``children`` key inside ``state_metadata`` is content.
    """
    payload = node.model_dump(
        mode="json", exclude=_EXCLUDED_NODE_FIELDS, exclude_defaults=True
    )
    payload.pop("children", None)
    for field in _CONTAINER_ENTRY_FIELDS:
        for entry in payload.get(field, []):
            entry.pop("children", None)
    return _digest(payload)


def content_hash(cnd: Cnd) -> str:
    """The content hash of a whole CND.

    Folds the ``doc`` metadata, every node of the body and of the footnotes
    paired with its full **path** (``nodes/0/children/4/cells/2/children/0``),
    and both pools. The path, not only the depth: moving a paragraph from
    one cell to the next keeps depth and reading order but changes the
    document. Excluded: ``built_at``, ``source``, ``cnd_version``.
    """
    payload = {
        "doc": cnd.doc.model_dump(mode="json", exclude_defaults=True),
        "nodes": [
            ["/".join(map(str, visit.ctx.path)), node_hash(visit.node)]
            for visit in cnd.iter_all()
        ],
        "bibliography": [pool_entry_hash(entry) for entry in cnd.bibliography],
        "footnotes": [pool_entry_hash(note) for note in cnd.footnotes],
    }
    return _digest(payload)


def pool_entry_hash(entry: BibEntry | Footnote) -> str:
    """The content hash of one pool entry. ``id`` is excluded, and a
    footnote's ``children`` too: its content nodes are hashed as nodes and
    folded into ``content_hash`` by path."""
    exclude = {"id", "children"} if isinstance(entry, Footnote) else {"id"}
    return _digest(
        entry.model_dump(mode="json", exclude=exclude, exclude_defaults=True)
    )


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
