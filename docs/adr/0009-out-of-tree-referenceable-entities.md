---
title: Out-of-tree referenceable entities; pools and typed link families
status: proposed
date: 2026-07-18
tags: [schema, breaking-change, refs, pools]
related: [0002, 0008]
superseded-by: null
---

# ADR 0009 — Out-of-tree referenceable entities

## Status
Proposed.

## Context
Footnotes and bibliography entries are content a document *references*,
not content that occupies a position in its reading flow. Modeling them as
nodes (the direction of the first draft of proposal 0004) forces a fake
tree position on each one and anchors it through the generic ref graph,
which cannot carry citation-specific metadata (form, supplement) without
bloating `NodeRef` for every other use. The manifest needs a place for
referenceable entities that are not blocks, and links to them need to say
which domain their target lives in.

## Decision
The manifest becomes two-tier. `CndManifest` gains two top-level pools,
siblings of `nodes`, always present (default empty): `bibliography` and
`footnotes`. Nodes carry three typed, forward-only (ADR 0008) link
families as separate fields — never one unified list: `refs` resolves in
`nodes`, `cites` in `bibliography`, `footnotes` in the footnotes pool. All
three share the skeleton `{id, label, span?}`; `CiteRef` adds optional
`form` and `supplement`. The resolution domain is carried by the field's
name and type, not by the id's shape — the id field is `id` everywhere,
and ids are globally unique across nodes and pool entries. `label`
mirrors the target's label (denormalized for display without resolving).
`span` is an optional standoff offset pair in Unicode code points into
the containing node's text. `NodeRef`'s canonical `{id, label}` core is
unchanged; `span` is an additive optional field, so ADR 0002 stands.

## Consequences
- Content with no flow position is representable without inventing one;
  the node tree stays a pure reading-order structure.
- A new link family is a new field with its own ref type, not a change to
  `NodeRef` — link metadata grows per-domain, not globally.
- Global id uniqueness lets the SDK's derived reverse index answer "who
  points here" across all families with one scan.
- Breaking format change: pools appear, link fields change; `cnd_version`
  bumps, spec §5 is rewritten, fixtures migrate (proposal 0004).
