---
title: Configurable table/figure rendering in to_text()
status: draft
date: 2026-07-08
tags: [rendering, to_text, tables, config]
related: []
superseded-by: null
---

# Proposal — Configurable table/figure rendering in `to_text()`

## Status
Draft. Not scheduled — recorded here so the idea isn't lost, not a commitment
to implement in any particular release.

## Motivation
`to_text()` currently renders every `table` and `figure` node as a single
parseable placeholder (`format_figure_placeholder()` in
`src/cnd/core/node_text.py`), regardless of the table's content. That's a
reasonable default — tabular structure generally can't be flattened to prose
— but it treats two very different kinds of tables identically:

- A **content-bearing** table (short, mostly text in its cells — a
  comparison table, a small parameter list) often carries meaning that would
  read fine inlined as text.
- A **data** table (numeric-heavy — a measurement grid, a CSV-style dump)
  gains little from being inlined; a placeholder is already the right call.

Right now there's no way for a producer or a consumer to say which kind a
given table is, or to override the placeholder behavior at all.

## Proposed change
Introduce a rendering mode for table/figure nodes with three states:

- **Force placeholder** — always emit the placeholder, regardless of content
  (today's only behavior).
- **Force inline** — always render the table's cell content as text instead
  of a placeholder.
- **Auto** (default) — decide per-node. When a table declares an explicit
  content-kind hint, use it. When it doesn't, fall back to a heuristic that
  estimates the ratio of textual vs. numeric cell content and classifies the
  table as content-bearing (→ inline) or data (→ placeholder) from a
  threshold.

A further mode worth keeping on the table (no pun intended) for later: an
**LLM-generated summary** as a third text representation, opt-in only, driven
by a caller-supplied callback rather than any dependency this SDK would ship
with (consistent with ADR 0006 — the SDK doesn't own how a summary gets
produced, only how the result plugs into rendering).

Independent of all of the above, and cheap to do on its own: even in
placeholder mode, `format_figure_placeholder()` could include the table's
header-row text (distinct from `caption`, which today is the only
human-readable hint carried) so a placeholder alone still preserves some of
the table's structure, not just its identity.

This should land as a general rendering-configuration mechanism usable by
any node type's `to_text()`, not a table-only special case — and it should
stay opinion-free about *why* a consumer wants inline vs. placeholder text
(embedding quality is one motivation, not the only one, and not this SDK's
concern per ADR 0006). That likely means this proposal's scope should grow
to cover `to_text()` configuration more generally rather than shipping a
table-specific flag in isolation.

## Alternatives considered
Not yet explored — this proposal is a placeholder for the idea itself, to be
fleshed out before implementation.

## Impact
Additive if the default stays "always placeholder" (today's behavior) —
existing consumers see no change unless they opt into a different mode.
Becomes a breaking change only if "auto" is ever made the default.

## Implementation checklist
- [ ] Design the general `to_text()` configuration mechanism (not table-only)
- [ ] spec/cnd-spec.md updated (§7, "Text rendering")
- [ ] Heuristic for the text-vs-numeric threshold defined and tested
- [ ] `format_figure_placeholder()` gains header-row content
- [ ] Pydantic models / node fields updated if an explicit content-kind hint is added
- [ ] tests updated
- [ ] status flipped to `implemented`
