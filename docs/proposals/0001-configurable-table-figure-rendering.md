---
title: Configurable table/figure rendering in to_text()
status: implemented
date: 2026-07-08
tags: [rendering, to_text, tables, config]
related: []
superseded-by: null
---

# Proposal — Configurable table/figure rendering in `to_text()`

## Status
Implemented for tables, with one deliberate reduction in scope: the
content-based classifier described below under "Auto" was never built.
`"auto"` mode ships and resolves purely from the explicit `content_kind`
hint (§6.3 of the spec) — an unset hint is treated as `"data"`, not
guessed. Nothing yet sets `content_kind` on ingestion, so a producer has to
set it explicitly (or a caller can use `"inline"` directly) for a table to
render as text today; the heuristic remains a possible follow-up, not
something this pass claims to have delivered.

Figures (non-table) are unchanged — still placeholder-only. The
motivating cases here (a comparison table, a parameter list, vs. a numeric
measurement grid) are tables specifically; there's no equivalent
data/content distinction defined yet for an image figure.

See `cnd.core.node_text.render_node_text` / `table_node_text`, and spec
§7.1.

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
The general mechanism (§ Proposed change) was built as a separate
`render_node_text(node, mode=...)` / `table_node_text(node, mode=...)`
entry point in `cnd.core.node_text`, rather than adding a `mode` parameter
to every node type's own `to_text()`. Reasons: `to_text()` stays exactly
zero-argument as already documented in spec §7, only `table` actually
varies by mode today (the other seven node types would accept and ignore
the parameter), and a future node type can opt in the same way `table` did
without changing `to_text()`'s contract for anyone else.

The text-vs-numeric classifier for unset `content_kind` was considered and
dropped for this pass: its threshold was the one genuinely unspecified
part of this proposal, nothing produces `content_kind` yet to make "auto"
meaningfully different from "always placeholder" in practice, and shipping
an unvalidated heuristic as committed schema/spec behavior was worse than
shipping the explicit hint alone and leaving "auto" honestly narrow. A
classifier (or an LLM-generated-summary mode, per the callback idea above)
remains open for a future proposal once there's a producer to drive it.

## Impact
Additive — the default stays "always placeholder" (`to_text()`'s own
behavior is completely unchanged; `content_kind` is a new optional field
that existing manifests simply don't set). No existing consumer sees any
change unless it calls the new `mode=` entry point directly.

## Implementation checklist
- [x] Design the general `to_text()` configuration mechanism (not table-only)
- [x] spec/cnd-spec.md updated (§7, "Text rendering", new §7.1)
- [ ] Heuristic for the text-vs-numeric threshold defined and tested —
      deliberately dropped from this pass, see Alternatives considered
- [x] `format_figure_placeholder()` gains header-row content
- [x] Pydantic models / node fields updated (`TableNode.content_kind`)
- [x] tests updated (`tests/test_node_text.py`, plus a real rowspan/colspan
      fixture table in `fixtures/comprehensive_manifest.json`)
- [x] status flipped to `implemented`
