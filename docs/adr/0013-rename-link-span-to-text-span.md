---
title: Rename the link-family span field to text_span
status: accepted
date: 2026-07-18
tags: [schema, refs, naming]
related: [0002, 0009, 0012]
superseded-by: null
---

# ADR 0013 — Rename the link-family span field to text_span

## Status
Accepted (shipped in v0.2.0).

## Context
The three forward link families (`refs`, `cites`, `footnotes`; ADR 0009)
each carry an optional field named `span`: the `[start, end)` position of
the link's marker inside the containing node's rendered text, in Unicode
code points. The bare name `span` is ambiguous — the word has meant at
least two unrelated things in this project's recent history:

- `NodeLocation`'s former position bookkeeping (`span`, `page_span`,
  `parent_span`, `span_count`), removed in ADR 0012. A reader who
  remembers those fields reasonably assumes any `span` is reading-order
  position, not a text offset.
- A source-language span — the byte range a producer maps *from* when
  converting a source document. Producers routinely hold both that and the
  rendered-text offset at once, and nothing in the name distinguishes them.

The field's meaning is specifically an offset *into the node's rendered
text*, and the name should say so. `locator` was considered and rejected:
it reads as a generic pointer, and it collides with an established
"locator" concept in the reference producer's toolchain, trading one
name clash for a worse one.

## Decision
Rename the field from `span` to `text_span` on `NodeRef`, `CiteRef`, and
`FootnoteRef`. The name pins the coordinate space — a span *in the node's
rendered text*. Semantics are unchanged: an optional, additive
`[start, end)` pair of Unicode code-point offsets into the containing
node's rendered text; nullable (a suppressed `form: "none"` citation has
no marker and so no `text_span`; ADR 0009).

This supersedes only the field's *name* as introduced in
`docs/proposals/0004`. That proposal's design — the pools, `TermsNode`, and
the three typed link families — stands unchanged.

## Consequences
- The spec (§5), the generated JSON Schema, the Pydantic models, the
  fixtures, and the tests move to `text_span` in one pass.
- No migration burden in practice: the field is a standoff annotation no
  producer had begun populating, so no manifest in existence carries the
  old key. This is a free rename, not a data migration.
- The name now disambiguates the field from `NodeLocation` position
  bookkeeping (removed, ADR 0012) and from producer-side source spans, at
  the cost of a slightly longer key.
- A future change may populate `text_span` from producers; that work
  inherits the clearer name and is otherwise unaffected by this decision.
