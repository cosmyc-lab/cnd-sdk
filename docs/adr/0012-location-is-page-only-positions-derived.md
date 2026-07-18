---
title: NodeLocation carries layout facts only (page); positions are SDK-derived
status: accepted
date: 2026-07-18
tags: [schema, breaking-change, location, traversal]
related: [0008]
superseded-by: null
---

# ADR 0012 — NodeLocation carries layout facts only (page); positions are SDK-derived

## Status
Accepted (shipped in v0.2.0).

## Context
`NodeLocation` has carried five producer-supplied integers: `page`, `span`
(reading-order index), `page_span` (per-page index), `parent_span`, and
`span_count`. Four of the five are position bookkeeping, and position is
derivable: the node tree is emitted in document reading order, so a
depth-first traversal reproduces `span` exactly, sibling enumeration
reproduces a within-parent index, and grouping by `page` reproduces
`page_span`. ADR 0008 already established the principle for edges: data a
consumer can derive from what the manifest necessarily contains is not
serialized, because materialized derivations add producer passes and a
consistency surface without adding information.

The bookkeeping fields had, in fact, already rotted: `parent_span` in the
producer was the parent heading's span rather than any within-parent index,
hand-maintained fixtures disagreed with the actual sibling indices in up to
17 places per file, figure wrappers introduced duplicate `span` values, and
`span_count` was `1` in every manifest ever emitted with no documented
meaning. Redundant fields drift; derived values cannot.

The one thing traversal cannot reconstruct is layout: where the page
breaks fell. The Typst introspector exposes a per-element position
(`PagedIntrospector::position(loc)` → page + point) but no per-element
extent, so a bounding box is not cheaply available to the producer today.

## Decision
`NodeLocation` is reduced to layout facts only: a single field `page`, the
page on which the node begins in the compiled document. `span`,
`page_span`, `parent_span`, and `span_count` are deleted, along with
`NodeLocation`'s span-based ordering.

Reading order becomes a normative invariant of the format (spec §2):
depth-first traversal of `nodes` IS document reading order, and producers
MUST emit in that order. On that foundation the SDK's traversal engine
derives positions and attaches them to every yielded
`NodeTraverseContext`: `doc_index`/`doc_count`, `sibling_index`/
`sibling_count`, and `page_index`/`page_count` (1-based, computed during
the walk; totals from a cheap pre-pass cached on the manifest, mirroring
`incoming()`). Bounding boxes are deliberately deferred: `page` is a
one-field extension point where a future `page_end` or `bbox` proposal can
land if a producer can ever supply them.

## Consequences
- The class of manifests whose position fields contradict their own tree
  order becomes unrepresentable; the producer's position bookkeeping
  (per-page counters, parent-span recursion) is deleted rather than fixed.
- Every consumer gets richer position data than the format ever carried —
  each index now ships with its total, and pruned traversals still report
  document-true positions — uniformly from the traversal context instead
  of from a field only some producers filled correctly.
- A node spanning multiple pages is recorded only by its starting page;
  `span_count` never actually carried that information (always `1`), but
  the door closes on that reading until an explicit extent field is
  proposed.
- Breaking format change, folded into the `cnd_version` 0.2.0 wave: spec
  §2/§4/§8 updated, schema regenerated, fixtures shrink to
  `{"page": N}`, and the `typst-cnd` emitter drops everything but the
  introspector page lookup.
