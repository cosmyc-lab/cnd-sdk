---
title: Rust succession plan — Python is the reference until the format freezes
status: proposed
date: 2026-07-22
tags: [architecture, implementation, sequencing, governance]
related: [0004, 0006, 0016, 0020]
superseded-by: null
---

# ADR 0022 — Rust succession plan: Python is the reference until the format freezes

## Status
Proposed.

## Context
ADR 0020 states that the reference stack moves from Python to a ported core
but names neither a trigger nor a rationale — schedule and reasoning are
treated as self-evident. The shared core it refers to exists to end the model
duplication the Typst producer fork carries today.

ADR 0019's boundary rule scopes what "shared" can mean: **nothing is shared as
code across languages** — only the spec and the golden fixture corpus
(ADR 0020) cross that boundary. A shared core is therefore consumed only by
code in the *same* language, which today means the builder and the Typst
producer fork, both Rust. Canonicalization
(JCS, RFC 8785) and Unicode normalization (NFC) have implementations in every
mainstream language, so a satellite SDK in another language does not import a
shared canonicalizer — it calls its own language's library and applies the
format's own exclusion rules (ADR 0016). Hashing, the strongest apparent case
for a shared binary dependency, turns out to be reimplementable-by-fixtures
like everything else.

That removes the strongest apparent justification for a Rust reference stack
— "one shared implementation everyone binds to" was never true across
languages, only within one. Left unstated, "the reference moves to Rust"
reads as a technical necessity the packaging model has already dissolved.
This ADR states the real reason and fixes the trigger and the switch
criterion that ADR 0020 leaves open.

## Decision
At every instant there is exactly **one** reference implementation — the
stack whose behavior defines conformance and whose output the golden corpus
records as ground truth. Succession happens in three phases. No two
implementations are ever co-referential (both defining conformance at once)
without an explicit candidate/canonical hierarchy between them.

**Phase 1 (now) — Python is the sole reference.** Format waves are iterated
in Python: Pydantic remains the schema source (ADR 0004, unchanged), and the
golden fixture corpus is built from day one, in lockstep with every format
change, not backfilled after the fact.

Rationale for staying in Python through active churn: `uv` and `ruff` are
Rust reimplementations of semantics that were frozen *elsewhere*, in an
existing ecosystem, before anyone ported them. They are evidence for porting
a design **after** it stops moving, not for writing the reference
implementation in Rust **while** it is still moving. A Rust reference during
active churn pays for every format change twice — once in the models, once in
reshaping them to something the borrow checker accepts — for no format-freeze
benefit yet earned.

**Phase 2 (triggered by the format freeze) — port the core.** Factual
trigger, not a date: 0.3.0 accepted, schema stable, fixture corpus complete.
`cnd-core` — models, invariants, `validate(cnd)`, hashing — is ported to
Rust, locked by the corpus built in Phase 1.

During the port, the crate is a **candidate**, not the reference. CI runs
both implementations against the fixture corpus; Python stays **canonical**
until Phase 3 flips that. This is the explicit hierarchy the "forbidden"
clause below requires — candidate and canonical are never symmetric.

Scope note: the only external consumer with a real dependency on the crate at
this point is the Typst producer fork (same language, per ADR 0019's
same-language rule). It needs the core only. Porting the builder that
compiles a declaration into a CND is a Phase 3 question, not a Phase 2
necessity — the declaration has no paginating compiler pushing on it the way
the direct door does.

**Phase 3 (the switch) — by its own dedicated ADR.** This ADR fixes the
trigger and the criterion; it does not pre-authorize the switch itself.
Factual switch criterion: the crate passes 100% of the fixture corpus across
N releases, **and** the Typst producer fork consumes it in production — not
merely builds against it in CI.

Effects of the switch, to be enacted by that future ADR: the schema is
generated from the crate instead of from the Pydantic models, so **ADR 0004
is superseded**; the builder is ported; and the CLI becomes a static binary —
a better conformance oracle for a third-party implementer to check against
than a `pip install`, since it carries no interpreter or dependency
resolution step. Python becomes an SDK like any other satellite (ADR 0020) —
either a binding on the crate (preferred, since it retires a second
hand-written implementation) or a conformant reimplementation proven against
the corpus like a fresh-language satellite would be, decided at switch time,
not here. Pydantic loses source-of-truth status at that point, not before.

**The honest rationale.** The move to Rust rests on author preference, on the
sustainability of maintaining motivation for the reference stack over years,
and on binary distribution — not on a technical necessity. Once nothing is
shared as code across languages, "we need Rust so everyone can bind to one
implementation" is not available as a reason, because no cross-language
binding was ever the plan. Naming the real motive is the point of writing
this down: an ADR that states its actual reason ages better than one that
manufactures a constraint to justify a preference.

**Forbidden: two co-referential implementations.** "The core must be Rust"
and "Python keeps the algorithms" must never both hold without the explicit
candidate/canonical hierarchy above. A claim like "the reference moves to
Rust" with no trigger, as ADR 0020 currently reads, is exactly the ambiguity
this ADR removes.

## Consequences
- The fixture corpus becomes the load-bearing artifact of the whole plan, not
  a nice-to-have: Phase 2 is only lockable because the corpus is complete by
  the time the freeze trigger fires. Any gap in corpus coverage at freeze
  time is a gap in the port's safety net, silently — the port will pass CI
  against an incomplete ground truth and look done when it isn't.
- Running two implementations in CI throughout Phase 2 is a real, recurring
  cost — compute, and a second set of failures to triage — accepted
  deliberately as the price of a switch that never has a moment where
  conformance is undefined or contested between two stacks.
- Because nothing is shared as code across language boundaries, a
  third-party satellite SDK (ADR 0020) is never blocked on which phase the
  reference stack is in — it targets spec plus fixtures in Phase 1, 2, or 3
  alike, and this succession plan is invisible to it except as fixture-corpus
  updates.
- The Phase-3 switch supersedes ADR 0004 and needs its own ADR to authorize;
  this ADR only fixes the trigger and the criterion in advance, so that
  decision is not made ad hoc under momentum once the crate looks ready.
- ADR 0020's "one reference stack at a time" now has the phase model behind
  it; a future editor updating ADR 0020's transitional `python/` note should
  point to this ADR rather than re-derive the sequencing.
