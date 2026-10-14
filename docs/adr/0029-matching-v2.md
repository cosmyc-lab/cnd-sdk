---
title: Matching v2 — the full walk, spec §8 paths and container keys
status: accepted
date: 2026-10-14
tags: [identity, reconciliation, diff, sdk, non-normative, 0.5.0]
related: [0015, 0018, 0028]
superseded-by: null
---

# ADR 0029 — Matching v2

## Status
Accepted. Extends ADR 0018. ADR 0018's decision stands: reconciliation is a
versioned reference algorithm, not part of the format. This ADR records what
version 2 of that algorithm computes, as the SDK implements it in
`cnd.reconcile.match` (`MATCHER_VERSION = "v2"`).

## Context
ADR 0018 pinned matching v1 for the 0.4 node model, in which most nodes were
leaves: a list item or a table cell was a string inside its node.

Format 0.5.0 (docs/proposals/0013) changes what there is to match.

- Every body lives in `children`, so list items, term items, cells, quotes,
  admonitions and footnotes hold nodes.
- Footnote content is made of nodes, outside the body walk (spec §8).
- A node hash excludes nested nodes (ADR 0028), so two containers of the same
  shape hash alike, whatever they contain.

Run unchanged on this model, v1 would leave three problems:

- nested nodes would go unmatched;
- footnote content would move whenever the pool is reordered;
- a surviving container could take the id of a deleted twin of the same shape.

## Decision

**The walk.** v2 matches every node of the full walk (spec §8): the body in
reading order, including nodes inside list items, term items, cells, quotes,
admonitions, figures and headings, then the content of each footnote in pool
order. That position is also each node's `order`, the tie-breaker.

**The structural path.** It is the node's spec §8 path, such as
`("nodes", 0, "children", 4, "cells", 2, "children", 0)`. The first
paragraphs of two different cells are therefore in two different slots.

**Footnote content is keyed by its note's label.** Inside a footnote, the pool
index in the path is replaced by the note's label:
`("footnotes", "fn-a", "children", 0)`. Pool entries already match on their
label (ADR 0018), and a pool has no "moved". Reordering the pool therefore
moves nothing, and a note's content matches against the same note's content.

**Containers carry a descendants digest.** A container is a list, terms,
table, layout, quote or admonition. Its key in the hash passes is its node
hash plus a digest of its descendants' hashes, taken slot by slot in
preorder. Without the digest, two tables of the same shape hash alike, and a
deleted table's id could pass to a surviving one.

Headings and figures are excluded from the digest on purpose:

- their own hash already carries their text or caption, so it tells them
  apart;
- a heading whose section changed has not itself changed (ADR 0028). With a
  digest, every edit inside a section would unmatch its heading, and a moved
  section would not be recognised.

Every node that is not a container has an empty digest. Its key is its node
hash alone, as in v1.

**The passes,** strongest first. A node matched by one pass is never
reconsidered by a later one:

1. `label` — exact; survives edit and move.
2. `hash+path` — node hash, digest and structural path agree: unchanged, in
   place.
3. `hash` — node hash and digest agree: moved but unchanged.
4. `path+type` — same slot, same type: edited content.
5. `container-hash` — for containers only, the node hash alone. It pairs a
   container whose nested content was edited and that also shifted. Such a
   container misses passes 2 and 3 (its digest changed) and pass 4 (its path
   changed). Twins have already paired through the digest in passes 2 and 3,
   so this pass sees only what is left.
6. Otherwise the node is unmatched: added on the new side, removed on the old
   side.

Within a pass, ties break by reading order. The last pass reports
`matched_by: "container-hash"`, distinct from `"hash"`. A caller can then tell
"unchanged container" from "container whose own fields survived".

**Empty containers.**

- An empty quote or admonition has one empty `children` slot. Its digest is
  that of an empty slot, so it is a container: it can pair in pass 5.
- A list or terms with no items, and a table or layout with no cells, has no
  slots at all. Its digest is empty, so it behaves like a leaf: it pairs on
  its node hash in passes 2 and 3, and never enters pass 5.
- Either way, nothing nested distinguishes two empty twins, so they pair in
  reading order.

**Conformance vectors.** `fixtures/matching.json` carries
`"matcher_version": "v2"`, and the pairs are under `fixtures/reconcile/`.

- Cases 08 to 10 cover nested nodes and footnote content.
- Case 11 covers the `container-hash` pass.

Reproducing the vectors proves that an implementation runs v2. As under
ADR 0018, it is not a conformance requirement on the format.

## Consequences
- **Finer reports.** An edited list item, or an edited paragraph in a cell, is
  matched and reported on its own; v1 would have marked the whole list
  changed.
- **Known limits.**
  - Two headings, or two figures, with identical titles or captions hash
    alike and carry no digest, so an edit or move can swap their ids.
  - Two twin containers that were both edited and shifted reach pass 5 with
    the same node hash, and pair in reading order, which can swap them.
  - ADR 0018's combined case still holds for every node that is not a
    container: a node that is both edited and shifted by an insertion above
    it is reported as added, and its predecessor as removed (fixture case
    06). Labels remain the only exact identity.
- **No change to hashing.** The digest is a matching key only, computed from
  node hashes. It is never serialised, and it is not a content hash. The node
  hash (ADR 0028) is unchanged.
- **Versioning.** Any later change to the walk, the keys or the passes is
  matching v3: a new `MATCHER_VERSION`, new vectors and a new ADR. It is not a
  regeneration of v2's vectors.
