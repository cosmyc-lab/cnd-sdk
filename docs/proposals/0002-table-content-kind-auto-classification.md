---
title: Automatic classification for TableNode.content_kind
status: draft
date: 2026-07-14
tags: [rendering, to_text, tables, config]
related: [0001]
superseded-by: null
---

# Proposal — Automatic classification for `TableNode.content_kind`

## Status
Draft. Split out of proposal 0001 at implementation time: 0001 shipped the
rendering mechanism (`mode="placeholder"|"inline"|"auto"`) and the explicit
`content_kind` hint field, but deliberately left `"auto"` mode's behavior
on an *unset* hint as "treat as data" rather than guessing — no classifier
ships yet. This proposal is that classifier, recorded so the idea isn't
lost, not a commitment to implement in any particular release.

## Motivation
`content_kind` (0001, spec §6.3) is producer-supplied. Nothing in the
compilation pipeline sets it today, so on a CND where no producer has
opted in, `mode="auto"` behaves identically to `mode="placeholder"` for
every table — the mode gains no value until either a producer starts
setting the hint, or the SDK can derive a reasonable default from the
table's own cell content when the hint is absent.

## Proposed change
Two independent classification strategies for the "hint is unset" case in
`mode="auto"` — not necessarily mutually exclusive, and this proposal does
not yet pick one over the other:

1. **Cell-content heuristic.** Estimate the ratio of numeric-looking to
   textual cell content (excluding the header row) and classify against a
   threshold: numeric-heavy → `"data"`, text-heavy → `"content"`. Cheap,
   deterministic, no external dependency — consistent with this SDK's
   `pydantic`-only footprint (docs/adr/0005). The open work is defining
   and testing the threshold itself: what counts as "numeric-looking"
   (bare numbers vs. units vs. mixed alphanumeric codes), what ratio is
   the cutoff, and whether it should vary by table size (a 2-cell table
   and a 200-cell table don't classify the same way at the same ratio).

2. **Caller-supplied classification callback.** A hook a caller passes in
   at render time — e.g. an LLM call, or any other classifier the caller
   already runs — that receives the table's cells (or its placeholder/
   caption) and returns `"data"` or `"content"`. Consistent with
   ADR 0006 (scope: manifest representation only) and the same reasoning
   already used for the LLM-summary idea noted in 0001: the SDK does not
   own *how* a classification is produced, only how the result plugs into
   rendering. This is strictly more general than option 1 (a caller can
   implement the heuristic itself and pass it as a callback) but adds a
   protocol/interface this SDK would need to define and keep stable.

A third option — running both, heuristic as the default with a callback
override — is also on the table but adds complexity that should only be
taken on once there's a concrete need for both simultaneously.

## Alternatives considered
Shipping a heuristic directly in proposal 0001 rather than splitting it
out. Rejected at implementation time: the threshold was the one genuinely
unspecified part of 0001, nothing yet produces `content_kind` to make the
distinction observable in practice, and an unvalidated classifier
committed as spec/schema behavior is harder to walk back than a documented
gap. Splitting it into its own proposal keeps 0001's "implemented" honest
and lets this piece be designed (and threshold-tested, per the checklist
below) on its own timeline.

## Impact
Additive either way, as long as the default for an unset hint stays
`"data"` (0001's current behavior) unless/until a classifier is actually
wired in and its own default is decided.

## Implementation checklist
- [ ] Decide between the cell-content heuristic, the callback hook, or both
- [ ] If heuristic: define and test the numeric-vs-textual threshold,
      including behavior on small tables and mixed alphanumeric content
- [ ] If callback: define the callback's signature/protocol and where it's
      threaded through (`table_node_text`? a new top-level render entry
      point?) without breaking 0001's existing `mode=` call sites
- [ ] spec/cnd-spec.md §7.1 updated with the chosen behavior
- [ ] tests updated
- [ ] status flipped to `implemented`
