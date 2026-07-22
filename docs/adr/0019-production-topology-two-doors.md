---
title: Production topology — a declarative door and a direct door over one shared contract
status: proposed
date: 2026-07-22
tags: [architecture, builder, engine, validation, scope]
related: [0006, 0011, 0016, 0017]
superseded-by: null
---

# ADR 0019 — Production topology: two doors over one contract

## Status
Proposed.

## Context
Today a manifest reaches a consumer one way: a compiler writes the JSON
directly. The reference producer is a Rust binary that emits the manifest and,
to do so, **redefines the CND models on its own side and re-implements the
invariant checks by hand in its test suite** — a second definition of the
format that must agree with this repository's models with nothing enforcing
the agreement.

Two developments press on this. First, a declarative source form (a builder)
is planned so a manifest can be authored by hand or by a language model, and so
the markdown/HTML/DocLang converters (proposal 0007) have a supported path in.
Second, ADR 0017 (label-keyed edges) and the invariants that are not
expressible in JSON Schema (global label uniqueness, refs-target-has-label,
pagination all-or-nothing) need to be enforced *somewhere*, once, rather than
re-derived by every producer.

The question is whether **all** producers should go through the declarative
form, or whether direct emission stays a first-class path — and where the one
definition of the format's invariants should live.

## Decision
Production has **two doors over one shared contract.**

**The declarative door.** A source form (YAML/JSON, carrying no ids and no
pages) is compiled into a manifest by the engine. This is the path for
producers that have neither ids nor pagination to offer: hand authors, language
models, and the inbound converters, which cease to be a special case and become
ordinary declarative producers.

**The direct door.** A rich paginating compiler emits the manifest JSON itself,
through the shared core (below) plus a `validate(manifest)` entry point. Direct
emission stays first-class; routing every producer through the declarative form
is **rejected**, because a compiler holds information the engine cannot derive —
real pages, and the `number` its counter engine resolved. Forcing those through
the declarative form would inflate it into a full intermediate format with two
dialects: a *second normative wire format*, which ADR 0006 exists to prevent.
A direct consequence worth stating: **the declarative form never transports
`location` or `number`**, and stays small by construction.

**One shared core.** A single, language-neutral implementation holds the
models, the invariants, and the hashing (ADR 0016), and is consumed by both the
engine and any direct producer — ending the model-and-check duplication the
Rust producer carries today.

**One contract, two enforcements — not of equal strength.** The invariants
split in two:
- *Redundancy* invariants (the same fact stated twice must agree) are made
  **unrepresentable** by the declarative form — it removes the second place.
  The label-mirror is the archetype: with label-keyed edges there is no second
  copy to disagree.
- *Referential* invariants (a reference must resolve, in the right domain,
  unambiguously) remain **detected** — by the builder at build time and by
  `validate()` for direct producers.

The two doors are therefore not equally strong, but the difference is not
"checked vs. unchecked": it is that `build()` cannot be bypassed, whereas
`validate()` can be forgotten. This is the same "verifiable, not promised" line
CND draws for hashes (ADR 0016), applied to invariants.

## Consequences
- The declarative form becomes a **contract for producers**, hence a second
  surface to specify and version. It is kept **non-normative until it has
  proven itself**; ADR 0006's scope is unchanged, and any promotion is a
  separate future ADR.
- `validate()` gives a direct producer a spec to target instead of hand-rolled
  test assertions; the shared core lets it drop its duplicate model definition
  entirely. The reference producer's fresh-per-build UUIDs are, under ADR 0015,
  now *correct* rather than a defect.
- The builder is the inbound mirror of the renderer hierarchy (ADR 0011):
  renderers take a node out to text, the builder brings a source in to a
  manifest, and invariant enforcement lives once on each side.
- Enforcement is centralised but not equalised: consumers of a manifest from
  the direct door rely on the producer having run `validate()`. The format's
  own guarantee to a consumer is what ADR 0016/0017 and the conformance section
  state, independent of which door produced the manifest.
- The shared core's language, packaging, and the repository layout that hosts
  it are a separate decision (ADR 0020).
