---
title: Cross-references resolve by target label; drop the id from link families
status: accepted
date: 2026-07-22
tags: [schema, breaking-change, refs, labels, identity]
related: [0002, 0008, 0013, 0015]
superseded-by: null
---

# ADR 0017 — Cross-references resolve by target label

## Status
Accepted. Supersedes ADR 0002.

## Context
A cross-reference edge is today the canonical shape `{id, label, text_span?}`
(ADR 0002): the `id` is the resolution key, and `label` is a denormalised
mirror of the target's own label, kept in sync by the invariant
`link.label == target.label` (spec §5).

ADR 0015 established that node ids are **not durable** across builds. An edge
keyed by id therefore points at a handle that the next build regenerates: with
the reference producer minting fresh ids every build, the id in a link is only
meaningful within the single CND that produced it. That is acceptable for
a consumer reading one CND, but it makes two things needlessly hard:

- **Id remapping has to rewrite every edge.** The reconciliation facility
  (ADR 0015) inherits a previous build's ids; because edges carry ids, every
  inherited id must be chased through every `refs`/`cites`/`footnotes` entry
  and rewritten consistently, or the graph silently breaks. This is an entire
  class of remap bugs that exists only because the edge duplicates the id.
- **Authoring by hand or by model is impossible.** Neither can mint a UUID,
  so neither can write an id-keyed edge.

Meanwhile the `label` is already carried on every edge (it must be, to satisfy
the mirror), and the pools it may point into — bibliography and footnotes —
are keyed by a **required** label already (spec §5.1, §5.2). The id is thus
redundant with the label as a pointer, and strictly worse: non-durable, and
needing rewrites the label never needs.

Typst references confirm the shape of the world: `@key` resolves a label
`<key>`; an element with no label cannot be referenced. Every real edge
already targets something that carries a name.

## Decision
**Cross-reference edges carry the target's `label` as the pointer, not its
id.** The `id` field is removed from all three link families. An edge becomes
`{label, text_span?}` (`cites` additionally keeps `form` and `supplement`;
`text_span` per ADR 0013 is unchanged).

1. **Resolution is by label**, through an index the SDK builds
   (`label → target`). The resolution *domain* is still carried by the field
   the edge appears in — `refs` → nodes, `cites` → `bibliography`,
   `footnotes` → `footnotes` — never by the shape of the label, exactly as
   spec §2 already states for ids.

2. **Labels are globally unique within a CND**, across nodes and pool
   entries alike, mirroring the id-uniqueness rule (§2). A label therefore
   resolves to exactly one target. Comparison is over the whole string, so a
   node label `sec:x` and a bibliography label `x` never collide; the common
   prefix convention keeps cross-domain collisions theoretical without the
   format having to prescribe it.

3. **The mirror invariant is removed.** `link.label == target.label` becomes
   vacuous once the label *is* the pointer — there is no longer a second copy
   to keep in sync.

4. **A node's `label` stays optional in general but is required for any node
   that is the target of a `refs` edge.** This is a conditional invariant,
   not expressible in JSON Schema; it lives in the prose spec and is enforced
   by the validator. Pool entries already require a label, so `cites` and
   `footnotes` targets are covered by their existing rules.

## Consequences
- **Edges survive rebuilds and id remapping for free.** The reconciliation
  facility's id inheritance no longer touches edges at all, since edges carry
  no ids — the remap-rewrite class of bugs disappears.
- **Content hashing simplifies.** An edge contributes its label (content) to
  `node_hash`; there is no link-id to exclude, so ADR 0016's exclusion set
  loses the "link target ids" case it anticipated.
- **The forward-only reverse index (ADR 0008) is now label-keyed.**
  `incoming()` is built from edge labels rather than ids; its contract is
  unchanged.
- **Global label uniqueness is stricter than the producer.** Typst permits
  duplicate labels and only fails when an ambiguous reference is resolved;
  CND rejects the duplicate outright, because here the label is the pointer
  and an ambiguous pointer is a defect. The producer must **fail** on
  duplicate labels rather than disambiguate silently (suffixing would invent
  data; dropping a duplicate would choose arbitrarily). This surfaces a
  latent producer bug earlier and is a conformance error, not a coercion.
- **Referencing an unlabelled node is no longer possible** — but it never
  happened in practice, since a producer only emits an edge to something the
  source named, and hand/model authoring references by name by construction.
- **ADR 0002 is superseded.** It bundled two rules: the canonical NodeRef
  form (retired here) and `doc_hash` as the sole hash-field name. The latter
  is separately revised by the 0.3.0 field wave (the `source` block); 0002 is
  marked superseded by *this* ADR because its NodeRef decision no longer
  describes the format, and the hash-field-name change is recorded with the
  field wave.
- Breaking change, folded into the 0.3.0 wave: schema, models, spec §2/§5,
  and fixtures all drop the edge `id` and gain the uniqueness and
  target-label rules.
