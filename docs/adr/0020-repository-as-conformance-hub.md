---
title: The repository is a conformance hub; consumption moves to per-language satellites
status: proposed
date: 2026-07-22
tags: [architecture, repository, conformance, governance, scope]
related: [0004, 0006, 0016, 0018, 0019]
superseded-by: null
---

# ADR 0020 — The repository is a conformance hub

## Status
Proposed.

## Context
ADR 0019 introduces a shared, language-neutral core (models, invariants,
hashing) consumed by the engine and by direct producers, and leaves its
language, packaging, and hosting open. At the same time the project is growing
past a single Python implementation: a producer already lives in a separate
Rust fork, converters and consumers in other languages are anticipated, and a
golden-fixture corpus is becoming the thing that says what "conformant" means.

A repository that mixes the *standard* (prose, schema, fixtures) with *one*
implementation cannot serve many implementations even-handedly, and — as ADR
0019 noted — has already produced a duplicate definition of the format on the
producer's side. The layout has to be decided so the shared core has a home and
so a third-party SDK can prove itself against the standard rather than against
this repository's Python.

## Decision
This repository becomes a **conformance hub**: it defines what CND is and what
conforms to it, and consumption moves out to per-language satellites.

**Hub layout** (existing directories kept — `spec/` and `docs/` are *not*
collapsed into one; the norm and the decision log stay distinct):

```
spec/        cnd-spec.md — the normative prose            (exists)
docs/        adr/ + proposals/ — the decision log         (exists)
schema/      manifest + declarative-form JSON Schema
fixtures/    the golden corpus — a versioned release artifact per tag
python/      the reference stack (schema source, ADR 0004) — TRANSITIONAL
crates/      cnd-core, cnd-engine (ADR 0019) — empty until then
```

**Satellites** (separate repositories): per-language consumer SDKs
(`cnd-sdk-js`, `cnd-sdk-go`, …) and the producer fork (`cnd-typst`). A
satellite is spun out only once the core it depends on exists — a satellite
without a real dependency is a fork moved for nothing.

**One reference stack at a time.** This is non-negotiable, because two
concurrent definitions of the format are exactly the duplication this wave
removes. Today `python/` is the reference and the schema is generated from its
models (ADR 0004). When `cnd-core` lands, the schema is generated from Rust
(via `schemars`), ADR 0004 relocates to the core, and `python/` **leaves the
hub** to become the `cnd-sdk-python` satellite — a binding on `cnd-core`, a
consumer rather than a definition.

**Fixtures are the load-bearing conformance mechanism**, not a folder. The
corpus is versioned and published in lockstep with the spec version, and is
the only thing that keeps a third-party satellite honest. Per ADRs 0016 and
0018 it carries `manifest → expected hash` and `(old, new) → expected matching`
vectors alongside `declarative → expected manifest`.

**Sequencing.** Prototype the source form, builder, and matcher in Python
(the models already exist), freeze the form against the golden corpus, then
port to Rust locked by that corpus. The corpus, not the choice of first
language, is what prevents divergence.

## Consequences
- Renaming the repository (to drop the language-specific `-sdk` suffix from the
  standard's home) breaks any downstream repository that pins this one by git
  URL or tag: those pins and import paths must be updated in a coordinated
  change. GitHub redirects the rename, but a pinned tag and package metadata do
  not update themselves.
- The golden corpus becomes a release artifact with its own CI, and — once the
  core is native — multi-platform wheels raise both CI cost and the bar for
  outside contributors, who must now build Rust. These are the accepted price
  of a single cross-language core.
- ADR 0006 scope is intact: the hub defines the manifest representation; SDKs
  and producers are downstream. The declarative form's normativity stays
  deferred (ADR 0019).
- `schema/` may need to rise out of `spec/` if it must hold the declarative
  form's schema at the same rank as the manifest's; that placement rides with
  the declarative form's normativity decision, not this ADR.
- The end state is one reference core (Rust) plus satellites; the Python stack
  in the hub is a transitional reference with a defined exit, not a permanent
  second implementation.
