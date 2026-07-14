---
title: Cross-document references
status: draft
date: 2026-07-14
tags: [refs, schema, resolution, roadmap]
related: []
superseded-by: null
---

# Proposal — Cross-document references

## Status
Draft. Recorded so the idea and its open questions aren't lost, not a
commitment to design or implement in any particular release. Nothing here
is decided — including whether this belongs in the manifest schema at all
versus staying entirely a consumer-side concern.

## Motivation
`refs_to` / `refs_from` (ADR 0002, `NodeRef { id, label? }`) are resolved
by a producer from Typst's own label mechanism: a `#label` on an element,
referenced elsewhere via `@label`, resolved at compile time through
Typst's `Introspector`. That resolution is scoped to a single compilation
— one source file plus its `#include`s, one `Introspector`. There is no
notion of "a label defined in a different file" at the compiler level, so
a producer built on top of Typst cannot honor a reference to a label it
never compiled.

Consumers that hold a whole corpus of manifests, not just one, may still
want a document to point at a specific node in *another* document —
"this section supersedes \<id\> in document B", "this equation reuses the
definition introduced in document A". Today that can only be expressed as
prose, not as a graph edge a consumer can traverse the same way it already
traverses `refs_to`.

## Proposed change
Not decided. Two things constrain any answer:

1. **`refs_to`/`refs_from` are resolved-pointer contracts today.** Every
   `NodeRef` in those lists is guaranteed, by ADR 0002, to point at a real
   node — in practice, a node in the *same* manifest, since that's the
   only thing a producer can verify at compile time. Mixing in pointers
   that might not resolve (the target document hasn't been compiled yet,
   the label moved, the target was never indexed) would break that
   guarantee for every existing consumer of those two fields. Whatever
   ships here needs its own field, not an extension of the existing ones.

2. **No producer can resolve this alone.** A producer only ever sees one
   compilation. Resolving "document A's reference to document B's label"
   requires knowing both documents, which means either a corpus-level
   index outside any single producer invocation, or a second pass after
   the fact.

One direction that has come up, sketched here without commitment: an
explicit opt-in construct at the source level (in the spirit of the
existing `state_metadata` annotation mechanism — see spec
`state_metadata` conventions) that a producer would emit as an
**unresolved** edge — something like a new `refs_external` list, carrying
whatever identifies the target document (a slug, a path, a stable id —
undecided) plus the target label, with no `id` yet. A separate resolution
step, run by whoever holds the corpus (not this SDK, per ADR 0006's scope
boundary — see Alternatives), would then walk indexed manifests, build a
`label -> node id` index per document, and either promote each unresolved
edge to a real pointer or leave it unresolved if the target isn't
indexed or the label no longer exists there.

That shape has a consequence worth naming rather than deciding around:
resolution becomes asynchronous and order-dependent (document B must be
indexed before A's reference to it can resolve), which today's
compile-time resolution simply doesn't have to deal with. Whether that
tradeoff is acceptable, and who owns the resolution step, is exactly the
kind of question this proposal is deferring, not answering.

## Alternatives considered
**Keep this entirely outside the standard.** A consumer could maintain
its own cross-document link table with no manifest-level representation
at all — plain application data, no schema change here. Consistent with
ADR 0006 (scope: manifest representation only): this SDK does not own
retrieval, indexing, or corpus-level concerns, only the manifest shape.
If cross-document references end up looking like "a link table keyed by
document id and node id," that arguably needs no new manifest field, and
this proposal should be closed as "not needed" rather than implemented.
This is the leading alternative and may turn out to be the right answer;
it's listed here rather than assumed because a manifest-level field would
let a reference travel with the document itself (portable across
consumers) in a way a purely external link table can't.

## Impact
Unknown until a direction is picked. If a new field is added, it is
additive to the schema (a new optional list, default empty) and does not
change how `refs_to`/`refs_from` behave for any existing manifest.

## Implementation checklist
- [ ] Decide whether this belongs in the manifest schema at all, or stays
      a consumer-side concern outside this SDK (see Alternatives)
- [ ] If in-schema: define the unresolved-edge shape and how a target
      document is identified (slug? path? a new stable document id?)
- [ ] Decide who runs resolution and when (indexing time? query time?
      a standalone reconciliation job?) — this SDK only has an opinion on
      the manifest shape, not on how a consumer resolves it
- [ ] Define behavior for a reference that never resolves (dangling
      target, moved label) — surfaced how, to whom
- [ ] spec/cnd-spec.md updated with the chosen shape
- [ ] tests updated
- [ ] status flipped to `implemented`
