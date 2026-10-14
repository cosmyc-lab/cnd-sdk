---
title: Content hashing, 0.5 amendments — defaults dropped, nested nodes excluded, paths in the document hash
status: accepted
date: 2026-10-13
tags: [hashing, identity, derived, change-detection, 0.5.0]
related: [0016, 0018]
superseded-by: null
---

# ADR 0028 — Content hashing, 0.5 amendments

## Status
Accepted. Supersedes ADR 0016, whose decision it restates in full and
amends.

## Context
ADR 0016 defined the derived content hash: a node hash and a document
hash, computed by any consumer, independent of producer, answering "did
this change?". It was written for the 0.3.0 field set, where most
content was a flat string on the node and only a few node types held
nested nodes in `children`.

Format 0.5.0 (docs/proposals/0013) changes three things the hash
depends on.

1. **Optional lists are everywhere.** Every `RichText` carries `marks`
   and four link families, each defaulting to an empty list that a
   producer may omit. Under ADR 0016, `{"value": "x"}` and
   `{"value": "x", "marks": []}` hash differently although they are the
   same content, and every future optional field would move every hash,
   as `links: []` did at 0.4.0.
2. **Nested nodes sit in more places.** A list item, a term item, a
   table or layout cell and a footnote all hold block nodes in
   `children`. Excluding only the node's own `children` would make a
   list's hash change whenever any item's paragraph changed.
3. **Depth no longer captures placement.** Moving a paragraph from cell
   1 to cell 2 of a table keeps its depth and its place in reading order
   and leaves every node-local hash unchanged, yet the document changed.

`numbering` also replaces `number` and `counter_label`.

## Decision
The SDK exposes `node_hash(node)`, `pool_entry_hash(entry)` and
`content_hash(cnd)`, and the specification defines the algorithm
normatively (spec §10). The hashes are **derived, never serialized**
into the CND.

**Canonical serialization (unchanged from ADR 0016).** Take the hashable
value, normalize every string — keys and values — to Unicode **NFC**,
serialize with [RFC 8785 JSON Canonicalization Scheme
(JCS)](https://www.rfc-editor.org/rfc/rfc8785), hash the bytes with
**SHA-256**, and render as `"sha256:<hex>"`. Both canonicalizations are
external references, so an implementation in any language can reproduce
the bytes.

**Rule 1 — defaults are dropped.** Before normalization, a field that the
schema declares with a default and that holds exactly that default is
removed: `null`, `[]` and `{}` where those are the defaults, `false` for
`ordered` and `is_header`, `1` for `rowspan` and `colspan`. This applies
at every level the schema models (a `RichText`, a `Mark`, a `Cell`, a
`ListItem`, a `DocDate`), not inside a free-form object
(`state_metadata`, `BibEntry.fields`). A required field is never
dropped, even when empty.

**Rule 2 — a node hash is node-local.** It covers the node's own fields,
excluding:

- `id` — not durable (ADR 0015); a hash covering it would inherit the
  very instability the hash exists to route around;
- `location` and `numbering` — resolved presentation state, which changes
  without the authored content changing;
- every nested node: the node's `children`, and the `children` of each
  entry of its `items` and `cells`. The entries themselves (a cell's
  coordinates, an item's `checked`, a term's `term`) stay. Only those
  structural keys are removed; a `children` key inside `state_metadata`
  is content.

The exclusion is stated as a principle plus the current list — *exclude
resolved presentation state and nested nodes, hash everything else* — and
the list is maintained as the field set evolves. A pool entry is hashed
over its fields except `id`; a footnote entry also excludes `children`,
whose nodes are hashed as nodes.

**Rule 3 — the document hash uses paths.** `content_hash(cnd)` hashes an
object with four keys: `doc` (defaults dropped); `nodes`, the
`[path, node_hash]` pairs of every node of the full walk (body, then
footnote content; spec §8) in walk order, with the path as a `/`-joined
string such as `nodes/0/children/4/cells/2/children/0`; and the entry
hashes of `bibliography` and of `footnotes`, in pool order. The CND's
`id`, `built_at`, `source` and `cnd_version` are excluded.

## Consequences
- **Every hash changes at 0.5.0**, as at 0.4.0. `fixtures/hashes.json`
  is regenerated, and a persisted pre-0.5 hash is not comparable. This is
  allowed by the pre-1.0 policy (ADR 0027). In-process reconciliation
  (ADR 0018) hashes both sides with one library and is unaffected.
- **Omission is free.** A producer may write or omit an empty list, and
  a future optional field with a default does not move an existing
  hash. The cost is that a second implementation must know each field's
  default; the schema states it, and the conformance vectors catch a
  mistake.
- **Excluding `numbering`** keeps change detection orthogonal to
  renumbering: inserting a heading renumbers every following node, and
  a hash covering it would report each of them as changed — precisely
  what the moved-but-unchanged matching pass of ADR 0018 must not see.
- **Node-local hashes make reconciliation finer.** An edited list item
  changes its paragraph's hash, not the list's; adding an item or a cell
  changes the container's.
- **Placement is content.** Moving a node between cells, items or
  sections changes the document hash even when depth and reading order
  do not.
- The hash remains change-detection, not identity: two identical
  paragraphs in one document share a hash. Pairing them across builds is
  reconciliation's problem.
- The conformance corpus keeps its `CND → expected hash` vectors
  (`fixtures/hashes.json`) so a non-Python implementation can prove it
  computes the same bytes.
