---
title: Forward-only cross-reference edges; drop materialized refs_from
status: proposed
date: 2026-07-18
tags: [schema, breaking-change, refs]
related: [0002]
superseded-by: null
---

# ADR 0008 — Forward-only cross-reference edges

## Status
Proposed.

## Context
Every node has carried both `refs_to` and `refs_from`, with a
bidirectional-consistency invariant (spec §5): if A lists B in `refs_to`,
B must list A in `refs_from`. `refs_from` is derived data — the exact
reverse of the `refs_to` graph. Materializing it buys O(1) access to
incoming edges at the cost of a consistency invariant a producer can
violate, a second back-edge-filling pass in every producer, and
duplication in the manifest. Two facts make that a bad trade:

- A manifest is a document-sized artifact; its reverse index is one O(N)
  pass, cheaply cached. A consumer that can read `refs_from` at all
  necessarily holds the whole manifest and can afford that pass — there is
  no access pattern where the materialized field is irreplaceable.
- Cross-document references (`docs/proposals/0003-cross-document-references.md`)
  make a materialized `refs_from` structurally false: it can only record
  intra-manifest incoming edges, so once another document may reference a
  node, "who references me" becomes an open-world question that no single
  manifest can answer. The field would give an answer that looks complete
  but is wrong by construction.

## Decision
The manifest stores only forward edges. `refs_from` is removed. `refs_to`
is renamed to `refs` — the `_to` suffix is meaningless once no reciprocal
field exists. The reverse index is derived on demand by the SDK
(`CndManifest.incoming(id)`, built lazily on first use), never serialized.
`NodeRef` keeps its canonical `{id, label}` shape unchanged: ADR 0002 is
untouched — this decision removes a field, not a form.

## Consequences
- The class of internally-inconsistent manifests (A → B without B → A)
  becomes unrepresentable; the remaining edge invariants are node-local or
  existence checks, needing no coordination between two nodes.
- Producers drop their second, back-edge-filling pass.
- A consumer wanting incoming edges calls the SDK helper instead of reading
  a field; the answer is identical, computed once per manifest load.
- Breaking format change: `cnd_version` bumps, spec §5 is rewritten, and
  fixtures migrate. Reverse lookups that span documents are explicitly a
  consumer/index concern, not a manifest field.
