---
title: Production topology — two doors, two ABIs, and one boundary rule
status: proposed
date: 2026-07-22
tags: [architecture, builder, producers, validation, scope]
related: [0006, 0011, 0015, 0016, 0017]
superseded-by: null
---

# ADR 0019 — Production topology: two doors, two ABIs, one boundary rule

## Status
Proposed. Revised 2026-07-22: the door classification was wrong for one
producer class, the build component is renamed, and the boundary rule is
stated.

## Context
Today a CND reaches a consumer one way: a compiler writes it directly. The
reference Typst producer, to do that, **redefines the models on its own side
and re-implements the invariant checks by hand in its test suite** — a second
definition of the format with nothing enforcing its agreement with this
repository's.

Two developments press on this. A **declaration** (a source form carrying no
ids and no pages) is planned so a CND can be authored by hand or by a language
model, and so producers reading foreign formats have a supported path in.
Meanwhile the invariants that JSON Schema cannot express — global label
uniqueness, a label on every `refs` target, pagination all-or-nothing — must be
enforced once rather than re-derived by every producer.

Three questions follow, and this ADR answers all three: which producers go
through the declaration, where the format-reading producers live, and what may
cross a language boundary at all.

## Decision

### 1. Two doors, chosen by what the source holds

**The declarative door.** A declaration is compiled into a CND by the
**builder**. This serves producers that have neither ids nor pagination to
offer: hand authors, language models, and those foreign-format producers whose
source is unpaginated — markdown, HTML.

**The direct door.** A producer that holds what the builder cannot derive —
real pages, a `number` its own counter engine resolved — emits the CND itself
and passes `validate()`. This covers the Typst compiler **and DocLang**, whose
entire purpose is carrying pages and bounding boxes.

The criterion is **what the source holds that the builder cannot derive**, not
what kind of tool the producer is. An earlier draft of this ADR put all
foreign-format producers on the declarative side; that was wrong for DocLang,
and routing it through the declaration would discard the one thing it uniquely
supplies.

Routing every producer through the declaration is **rejected** for the same
reason: it would inflate the declaration into a full intermediate format with
two dialects — a *second normative wire format*, which ADR 0006 exists to
prevent. The consequence is worth stating positively: **the declaration never
transports `location` or `number`**, and stays small by construction.

The build component is named **`cnd-builder`**. "Engine" named nothing, and the
prose of this repository already called it the builder.

### 2. Producers are not part of the builder

A producer is a producer, not a layer of the builder. The decisive reason is
the seam: **the declaration is only a contract if real producers materialise
it.** If the builder turned markdown into a CND internally, it would bypass the
very seam it defines, and the seam would rot for want of use.

Supporting reasons: parsers are not dependencies of a build component;
inference heuristics churn faster than the builder may churn; and a producer in
any language can emit a declaration. A practical benefit falls out — for an
inference-based producer, the intermediate declaration is exactly where a human
corrects the guesses (heading levels, what is a figure) before building.

### 3. Two ABIs, one per door

- **Declarative door**: a producer is any executable that writes a declaration
  on stdout. **The declaration is the plugin ABI** — language-agnostic, no FFI,
  no plugin API to version.
- **Direct door**: a producer's ABI is "emit a CND, pass `validate()`". There
  is no plugin protocol here, and none is needed.

One plugin decision is taken now and only one: **the declaration carries a
version field.** Without it the first evolution of the format breaks every
producer silently. Discovery conventions, naming schemes and a registry are
deliberately deferred until two or three producers exist to generalise from.

**What the declarative door guarantees, stated correctly.** Everything a
declarative producer emits passes through the builder's validation bottleneck.
That is **well-formedness, not truth**, and the distinction matters:

- a producer can emit an *unbuildable* declaration — duplicate labels, or
  references to absent ones. Global label uniqueness (ADR 0017) makes collisions
  *more* likely, not less, because a producer sees only its own document and not
  the label space it lands in;
- a producer can emit a *buildable but false* declaration — a heuristic that
  invents a reading order yields a perfectly valid CND of a document that does
  not exist.

The real benefit is not impossibility of invalidity; it is that the
semantically wrong layer is hand-correctable in the intermediate declaration.

### 4. One contract, two enforcements of unequal strength

Invariants split in two. *Redundancy* invariants — the same fact stated twice
must agree — are made **unrepresentable** by the declaration, which removes the
second place. *Referential* invariants — a reference must resolve, in the right
domain — remain **detected**, by the builder at build time and by `validate()`
for direct producers.

The asymmetry is not "checked vs. unchecked": it is that `build()` cannot be
bypassed while `validate()` can be forgotten. Same line CND draws for hashes
(ADR 0016) — verifiable, not promised — applied to invariants.

### 5. The boundary rule

**Nothing is shared as code across languages.** Sharing happens as
specification plus the golden fixture corpus; an implementation proves itself
against the corpus. A native core bound into every language would create a de
facto canonical implementation and remove the incentive to implement the
standard at all.

What may cross a boundary is decided by **interface shape**, not by how hard
the thing is to write:

- A **value function** — document in, value out — crosses any boundary
  losslessly: in-process, FFI, or subprocess. `validate`, `hash`, `build` and
  `reconcile` are value functions.
- A **traversal** is control flow — iterators, visitors, walk state — and
  crosses no boundary without becoming monstrous. The core carries one for its
  **own internal use** (`validate` walks the tree, the document hash folds node
  hashes in reading order), not to lend.

The rule to hold: **only pure document→value functions cross; anything with a
lifecycle** — an incremental index, session state, a walk — **belongs to the
host language.**

## Consequences
- The declaration becomes a contract for producers, hence a second surface to
  specify and version. It stays **non-normative until it has proven itself**;
  ADR 0006's scope is unchanged and any promotion is a separate ADR.
- `validate()` gives a direct producer a specification to target instead of
  hand-rolled test assertions, and lets it drop its duplicate model definition.
  The reference producer's fresh-per-build UUIDs are, under ADR 0015, correct
  rather than a defect.
- The builder is the inbound mirror of the renderer hierarchy (ADR 0011):
  renderers take a node out to text, the builder brings a declaration in to a
  CND, and invariant enforcement lives once on each side.
- **Because traversal is per-language, its semantics must be specified in prose
  and covered by the corpus.** Two questions are currently unanswered and will
  be answered differently by different implementations if left open: do the
  out-of-tree pools enter reading order, and at what point? What is the order
  among the three link families? Reading order is already normative and the
  reconciliation matcher already breaks ties "by reading order", so the
  semantics is *already* semi-normative without being written. The corpus needs
  `CND → expected id sequence` vectors, or SDKs will diverge exactly where it is
  invisible.
- Consumers of a CND from the direct door rely on the producer having run
  `validate()`. What the format guarantees a consumer is what ADR 0016/0017 and
  the conformance section state, independent of the door.
- Repository layout and what the hub ships are ADR 0020; the implementation
  language and its schedule are ADR 0022.
