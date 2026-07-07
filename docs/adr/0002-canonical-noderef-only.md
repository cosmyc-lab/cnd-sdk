---
title: Canonical NodeRef {id, label} form only; no legacy shims
status: accepted
date: 2026-07-07
tags: [schema, breaking-change, refs]
related: []
superseded-by: null
---

# ADR 0002 — Canonical NodeRef `{id, label}` form only

## Status
Accepted (shipped in v0.1.0).

## Context
Early manifest producers emitted cross-references in three different
shapes: bare UUID strings, `[label, id]` tuples, and `{id, label}` objects.
Supporting all three required parsing shims and made the JSON Schema
ambiguous — a consumer could not rely on a single shape without also
handling the other two. Similarly, an early field name `source_hash`
survived as a legacy alias of what is now `doc_hash`.

## Decision
The standard accepts exactly one form: `{"id": <uuid>, "label": <string|null>}`
for every entry of `refs_to`/`refs_from`, and `doc_hash` as the only hash
field name. The compatibility shims were removed from the SDK code itself,
not merely hidden from the published schema. Existing fixtures were
rewritten via a canonicalization script rather than kept as tolerated
inputs.

## Consequences
- Producers emitting a legacy shape fail validation immediately — a
  conformance error, not a silent coercion.
- The schema, the Pydantic models, and the prose spec describe the same
  single shape (see ADR 0004 for how the schema is kept in sync).
- Any future ref shape change requires a spec version bump via
  `docs/proposals/`, not a quiet parser change.
