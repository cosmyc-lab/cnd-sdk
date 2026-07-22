---
title: Declarative and direct producers — bringing foreign formats into CND
status: draft
date: 2026-07-22
tags: [producers, converters, inbound, doors, plugins]
related: [0006, 0014, 0017, 0019, 0020, 0021]
superseded-by: null
---

# Proposal — Declarative and direct producers

## Status
Draft. Replaces the inbound half of an earlier revision of proposal 0007,
which treated both directions as one "converters" module. ADR 0019 established
that they are not: producing a CND is *production*, governed by two doors, and
has nothing structural in common with rendering a CND out to another artifact.

## Motivation
A consumer holding a document in another format has no supported path into
CND. They construct the CND by hand and re-derive every invariant the schema
cannot express, differently each time, and can produce something that validates
against the schema while violating the specification.

ADR 0019 gives the shape of the answer — two doors, chosen by what the source
holds — but names no concrete producers. This proposal names them, classifies
each, and records what each irreducibly loses.

## Proposed change

### Which door each producer uses

The criterion (ADR 0019) is **what the source holds that the builder cannot
derive** — real pages, or a `number` resolved by the source's own counter
engine — not what kind of tool the producer is.

| Producer | Door | Why |
|---|---|---|
| `markdown → cnd` | declarative | no pages; structure is inferred |
| `html → cnd` | declarative | as above, plus presentational markup discarded |
| `doclang → cnd` | **direct** | carries pages and bounding boxes, which a declaration never transports |
| `typst → cnd` | direct | real pages plus a resolved `number` |

A declarative producer emits a **declaration** and stops; the builder produces
the CND. A direct producer emits the **CND** itself and runs `validate()`.

### Mapping versus inference

Cutting across the doors is a second distinction that drives the order of work
and the honesty of the documentation:

- **Mapping** — the source already carries explicit structure, so the
  conversion is mechanical and its failures are missing-feature failures.
  `doclang → cnd` is in this class.
- **Inference** — the source under-determines document structure, so the
  producer must guess: heading hierarchy, whether a table is data or layout,
  what is a figure versus an image with adjacent text. Failures here are silent
  and semantic. `markdown → cnd` and `html → cnd` are in this class.

Mapping producers land first. Inference producers land last and **must document
their heuristics as heuristics**.

### What each direction loses

| Direction | Principal loss |
|---|---|
| `doclang → cnd` | geometry (bounding boxes), layer classification, thread ids, formatting spans, form/field structures |
| `markdown → cnd` | little is dropped, but structure is *inferred*: heading levels, table semantics, figure grouping |
| `html → cnd` | as above, plus presentational markup discarded wholesale |

No direction round-trips; the losses are documented per producer so no consumer
designs for reversibility.

### The declarative producer contract

Per ADR 0019, a declarative producer is any executable that writes a
declaration on stdout — the declaration *is* the plugin ABI, so a producer may
be written in any language with no FFI and no plugin API to version.

Two things are fixed now:

1. **The declaration carries a version field.** Without it the first evolution
   of the declaration's schema breaks every producer silently.
2. **What the door guarantees is well-formedness, not truth.** Everything a
   declarative producer emits passes through the builder's validation
   bottleneck, so it cannot yield a malformed CND. It can still emit an
   *unbuildable* declaration (duplicate labels, references to absent ones —
   and global label uniqueness makes collisions more likely, since a producer
   sees only its own document), and it can emit a *buildable but false* one:
   an inference producer that invents a reading order yields a perfectly valid
   CND of a document that does not exist. The real benefit is that this wrong
   layer is **hand-correctable in the intermediate declaration** before
   building — which is why `cnd declare` exposes it as a step rather than
   folding it into `cnd build`.

Discovery conventions, naming schemes and a registry are deliberately deferred
until two or three producers exist to generalise from.

### Dependencies

Producers need parsers, which must never become hard dependencies. They ship as
optional extras following the `[display]` precedent (ADR 0005) — a producer
whose extra is missing fails cleanly on explicit import, and importing the
producers package never requires an extra.

## Alternatives considered
**Route every producer through the declarative door.** Rejected in ADR 0019: a
source holding pages would have to push them through a declaration that does
not transport them, which would inflate the declaration into a second normative
wire format.

**Keep one "converters" proposal covering both directions.** Rejected: since
ADR 0019/0020 the two directions have different homes (SDK satellites versus
producers), different contracts, and different lifecycles. Bundling them would
force one document to be superseded for reasons that only concern half of it.

**Let producers assemble the CND directly on the declarative door.** Rejected —
it duplicates invariant enforcement per producer and is exactly what the
builder exists to prevent.

## Impact
Additive; no change to the CND format, its schema, or its conformance sections.
Declarative producers depend on the builder and the declaration's schema
landing first. Direct producers depend on `validate()` being available in their
language.

## Implementation checklist
- [ ] Declaration schema published with its version field
- [ ] `markdown → declaration`, heuristics documented as heuristics
- [ ] `html → declaration`
- [ ] `doclang → cnd` (direct door), with the element-by-element mapping
- [ ] Per-producer loss documentation
- [ ] Fixtures: source → expected declaration, per producer
- [ ] status flipped to `implemented`
