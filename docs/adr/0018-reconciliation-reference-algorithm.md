---
title: Reconciliation (diff and id inheritance) is a versioned reference algorithm, not a format guarantee
status: proposed
date: 2026-07-22
tags: [identity, reconciliation, diff, sdk, non-normative]
related: [0006, 0015, 0016, 0017]
superseded-by: null
---

# ADR 0018 — Reconciliation is a versioned reference algorithm

## Status
Proposed.

## Context
ADR 0015 decided that durable node identity is not a property of the format:
CNDs are immutable build artifacts, and the only exact durable identity is a
label. It pointed at an SDK facility to give consumers *best-effort* continuity
for everything unlabelled — a way to answer "is this the same node as in the
previous build?" — without promising it in the format.

That facility has to be pinned down: what it computes, and whether the way it
computes it is normative for CND. Two questions ride together — a **diff**
between two CNDs, and **id inheritance** when rebuilding (a new build that
keeps a previous build's ids where nodes correspond). Both are the same
matching problem viewed twice: the diff reports the correspondence, the rebuild
consumes it.

The tempting move is to make the matching normative, on the reasoning that id
inheritance writes matched ids *into* the produced CND, so two implementations
that match differently would produce different CNDs. That reasoning does not
hold: newly-introduced nodes get fresh UUIDs and `built_at` differs, so two
independent implementations can never produce byte-identical CNDs from the same
inputs anyway. Cross-implementation equality is unattainable by construction,
so it cannot be the thing a normative matcher protects.

## Decision
The SDK provides reconciliation as a **versioned reference algorithm**
("matching v1"), **not** a normative part of the format.

- **`diff(a, b) → CndDiff`** classifies each node as added, removed, changed
  (matched, content hash differs), moved (matched, hash equal, path differs),
  or unchanged, with a per-pool diff. Pool entries match on their required
  label, so pools are always exact.
- **`reconcile(new, previous) → CND`** returns `new` with the ids of matched
  nodes inherited from `previous`.

**Reconciliation is a post-hoc pass over two built CNDs, not a parameter of the
build.** An earlier draft exposed it as `build(source, previous=…)`, which
confined it to the declarative door and would have forced every direct-door
producer to re-implement matching for itself. As a standalone
`CND × CND → CND` it is **door-agnostic**: the same pass serves a CND that came
from the builder and one a compiler emitted directly. It is also a pure
document→value function, so it crosses a language boundary at no cost under
ADR 0019's boundary rule, and it keeps any external consumer's need for the
reference implementation down to models, `validate` and hashing.

Nothing is lost by making it post-hoc: id inheritance was always "build with
fresh ids, match, then remap", so the matching already ran after construction —
this only exposes it as a function instead of hiding it in a parameter. All
four matching keys (label, content hash, structural path, type) are present in
the built CND.

The matcher runs in passes, strongest key first:
1. **label** — exact, survives edit and move;
2. **content hash + structural path** — unchanged, in place;
3. **content hash alone** — moved but unchanged; this pass recovers the nodes
   an insertion shifted;
4. **structural path + type** — same slot, edited content;
5. otherwise a new id.

Ties within a pass (equal-hash duplicates) break by reading order.

**Why non-normative.** What reconciliation protects is *id continuity within
one pipeline* — a local property, not an interoperability guarantee — and that
is exactly what a versioned reference algorithm delivers. A normative
heuristic would also be frozen at v1: any later improvement to the matching
would become a breaking change to the standard rather than a new algorithm
version. Keeping it out of the format lets the algorithm improve on its own
cadence.

## Consequences
- Consumers get the versioning the format deliberately omits (ADR 0015): keep
  the CNDs you call versions, and `diff` tells you what moved between them.
  This is an SDK facility under ADR 0006, creating no conformance obligation on
  producers.
- **Documented limitation.** The combined case defeats the heuristic: a node
  that is both edited *and* has another inserted above it misses passes 2–3
  (content changed) and pass 4 (path shifted), and gets a fresh id. This is the
  diff problem; sequence-alignment tools do better and still miss. The claim is
  best-effort for unlabelled nodes, exact for labelled ones — never more.
- **Label-keyed edges (ADR 0017) make id inheritance cheap.** Because edges
  carry labels, not ids, the remap rewrites only node and pool ids — it never
  has to chase ids through the link families. The remap is a final
  whole-document pass with one `{new_id: old_id}` map; it must assert the map
  is injective and that no inherited id collides with a freshly minted one
  before applying.
- Content hashing (ADR 0016) is the matcher's key input; the two ship
  together, and the golden-fixture corpus gains `(old, new) → expected
  matching` vectors so a second implementation can reproduce v1 exactly.
- Held in reserve: if cross-implementation interoperability of `reconcile` is
  ever needed, a conformance profile ("an implementation that offers id
  inheritance implements matching vN") can be declared without making the base
  format depend on it.
- Because `reconcile` is door-agnostic, a direct-door producer that wants id
  continuity does not need the builder at all — it emits a CND and runs the
  pass. That keeps the reference implementation's required surface for any
  external consumer down to models, `validate` and hashing (ADR 0022).
