---
title: The repository is a conformance hub; the hub ships a conformance CLI
status: proposed
date: 2026-07-22
tags: [architecture, repository, conformance, governance, scope]
related: [0004, 0006, 0016, 0018, 0019, 0022]
superseded-by: null
---

# ADR 0020 — The repository is a conformance hub

## Status
Proposed. Revised 2026-07-22: the hub ships a *conformance* CLI rather than a
full one, and the satellite layout is stated as a target rather than a
structure to materialise now.

## Context
ADR 0019 establishes two production doors and one rule that governs this
decision: **nothing is shared as code across languages** — sharing happens as
specification plus the golden fixture corpus. That makes the corpus, not any
binary, the thing that says what "conformant" means.

Today this repository mixes the standard (prose, schema) with one Python
implementation, while the producer already lives in a separate fork and
re-derives the models on its side. The layout has to be decided so that a
third-party implementation can prove itself against the standard rather than
against this repository's Python — and so the hub does not quietly acquire
dependencies that invert its own direction.

## Decision

### 1. The hub layout

The repository defines what CND is and what conforms to it:

```
spec/        cnd-spec.md — the normative prose            (exists)
docs/        adr/ + proposals/ — the decision log         (exists)
schema/      the CND schema + the declaration schema
fixtures/    the golden corpus — a versioned release artifact per tag
python/      the reference stack (schema source, ADR 0004)
crates/      the ported core, when ADR 0022's phase 2 begins
```

`spec/` and `docs/` stay distinct: the norm and the decision log are different
things and collapsing them loses that.

### 2. The hub ships a *conformance* CLI

An earlier draft had the hub ship a CLI that bundles format-reading producers.
That is mechanically incompatible with this ADR's own rule, and the conflict
has no soft resolution: if the hub's CLI depended on a producers repository,
the hub would depend on a satellite and the inference-heuristic churn that
ADR 0019 kept out of the builder would enter the hub through the window; and if
it discovered producers as plugins, the plugin machinery ADR 0019 deliberately
defers would become a day-one prerequisite.

**The hub's CLI carries the verbs that *are* conformance**: `validate`, `hash`,
`reconcile`/`diff`, `build` from a declaration, and terminal inspection. That
makes it the **executable oracle of the fixture corpus** — precisely the tool a
third-party SDK author needs, whose question is "does my hash match the
oracle?".

`cnd declare doc.md` and the `cnd build doc.md` convenience shortcut live with
the producers, or arrive later through plugin discovery. The cost is a little
day-one demo comfort, paid to keep this ADR's own boundary rule intact.

### 3. Two repositories now; satellites are a target, not a move

**Now**: the hub, and the Typst producer fork — separate by nature, since it
rebases onto a large upstream.

**Deferred**: a producers repository (markdown, HTML, DocLang stay *packages
inside the hub* while we are the only people writing them) and every
per-language SDK repository (none exists yet).

A breaking wave is one PR, one tag, one coherent state; splitting a repository
later is cheap and merging one back is not. The seam that matters is the
**import** boundary, not the git boundary — "producers ∉ builder" (ADR 0019) is
expressed perfectly well by separate packages, and materialising it as separate
repositories today buys cross-repo version coordination before the first
external user exists.

### 4. Fixtures are the load-bearing mechanism

The corpus is versioned and published in lockstep with the spec version. It is
the only thing keeping a third-party implementation honest, and it must carry:
`declaration → expected CND`, `CND → expected hashes`, `(old, new) → expected
matching` (ADR 0018), and `CND → expected reading-order id sequence`
(ADR 0019).

### 5. One reference stack at a time

Python is the reference today and the schema is generated from its models
(ADR 0004). The trigger, criterion and honest rationale for moving that role to
a ported core are ADR 0022; this ADR only fixes that the role is never held by
two stacks at once.

## Consequences
- Renaming the repository to drop the language-specific suffix from the
  standard's home breaks any downstream repository that pins this one by git
  URL or tag; those pins and import paths need a coordinated update. GitHub
  redirects the rename, but pinned tags and package metadata do not update
  themselves.
- The corpus becomes a release artifact with its own CI, and its completeness
  becomes a blocking concern rather than a nice-to-have — ADR 0022's phase 2 is
  only lockable because the fixtures are complete.
- Deferring the producers repository means the hub temporarily contains
  heuristic packages. The import boundary is what keeps that honest; the split
  is triggered when someone outside starts writing producers, not by a date.
- ADR 0006's scope is intact: the hub defines the representation; SDKs and
  producers are downstream. The declaration's normativity stays deferred
  (ADR 0019).
- `schema/` rises out of `spec/` because it must now hold the declaration's
  schema alongside the CND's, and only the latter is normative.
- The measure that actually matters is not repository topology but this: **can
  a third party write a conformant SDK from the spec and the fixtures without
  talking to us?** While the answer is no, no layout fixes it; once it is yes,
  several layouts work.
