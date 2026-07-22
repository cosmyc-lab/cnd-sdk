---
title: Derived content hashing — canonical serialisation and excluded presentation state
status: proposed
date: 2026-07-22
tags: [hashing, identity, derived, change-detection]
related: [0008, 0012, 0015]
superseded-by: null
---

# ADR 0016 — Derived content hashing

## Status
Proposed.

## Context
ADR 0015 splits identity into two questions and assigns "did this node
change?" to a content hash. That hash needs a normative definition, or every
consumer and producer computes its own and none of them agree.

Two different hashes must not be conflated:

- A **source hash** — a producer-supplied digest of the *input artifact* it
  built from (a field in the CND's `source` block). It answers "did the
  input file change" and is only comparable between two CNDs from the
  **same producer over the same source**. It is a field decision, covered by
  the 0.3.0 field wave, not by this ADR.
- A **derived content hash** — computed over the *CND itself*, per node
  and per document. It answers "did this node's content change" for any
  consumer, independent of producer. This ADR defines it.

The derived hash also has to be usable by the reconciliation/diff facility
ADR 0015 points to: one of its matching passes recognises a moved-but-unchanged
node by its content hash alone. That only works if the hash is stable under
the operations that should count as "moved, not changed" — which forces a
careful choice of what the hash covers.

Following the format's standing principle (data a consumer can derive from
what the CND necessarily contains is not serialised — ADR 0008 for
edges, ADR 0012 for positions), the hash must be **derived, not a field**.

## Decision
The SDK exposes `node_hash(node)` and `content_hash(cnd)`, and the
specification defines the algorithm normatively. The hashes are **never
serialised** into the CND.

**Canonical serialisation.** The hashed input is produced by
[RFC 8785 JSON Canonicalization Scheme (JCS)](https://www.rfc-editor.org/rfc/rfc8785)
over the hashable field subset, with Unicode strings normalised to **NFC**
before hashing. Both are external references rather than a bespoke scheme, so
an independent implementation in any language can reproduce the bytes.

**What is excluded.** The hash covers content and excludes **all resolved
presentation state** — state a producer computed for display, which changes
without the node's authored content changing. Under the 0.3.0 field set that
is: the node `id`, `location`, the resolved `number`, and the CND's
`built_at`. Everything else is content and is hashed: the node `type`, the
text and structural content fields, the node `label`, and the labels carried
by the link families. The exclusion is stated as the principle plus the
current list, so the list is maintained as the field set evolves rather than
frozen.

`content_hash(cnd)` folds the node hashes in reading order together with
the `doc` metadata, so it is stable across a rebuild exactly when no content
changed.

## Consequences
- The excluded-`number` case is the one that would otherwise silently break
  matching: inserting a heading renumbers every following node, so if `number`
  were hashed, the "moved but unchanged" matching pass would miss every
  numbered node after an insertion — precisely the pass meant to recover
  insertions. Excluding resolved presentation state is what keeps
  change-detection orthogonal to renumbering and repagination.
- Excluding `id` is required for the hash to be a *content* key at all: a hash
  that included the id would inherit the very instability (ADR 0015) that the
  hash exists to route around.
- This ADR assumes the 0.3.0 field changes land with it — a resolved `number`
  field and link families that carry labels rather than target ids. If links
  still carried target ids, those ids (being non-durable, ADR 0015) would also
  have to be excluded; label-based links make that exclusion unnecessary.
- A normative, cross-language canonicalisation is now part of the conformance
  surface: the golden-fixture corpus must include CND → expected-hash
  vectors so a non-Python implementation can prove it computes the same bytes.
- The hash is change-detection, not identity: two genuinely identical
  paragraphs in one document share a hash. Pairing them across builds is the
  reconciliation facility's problem (it breaks ties by reading order), not the
  hash's, and this ADR makes no identity claim for equal hashes.
