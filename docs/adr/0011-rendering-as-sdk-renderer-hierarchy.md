---
title: Rendering is an SDK renderer hierarchy; nodes are pure data
status: proposed
date: 2026-07-18
tags: [rendering, sdk, breaking-change, architecture]
related: [0006]
superseded-by: null
---

# ADR 0011 — Rendering as an SDK renderer hierarchy

## Status
Proposed.

## Context
Every node type carries a `to_text()` method, baking exactly one text
form into the data classes, with verbosity configuration bolted on beside
it (`render_node_text(mode=...)`, proposal 0001). Supporting a second
output format would mean another method on every node, and the spec (§7)
currently reads as if the format itself mandates a rendering contract —
which oversteps ADR 0006's CND-only scope.

## Decision
Nodes become pure data: `to_text()` and `render_node_text` are removed.
Rendering lives in a class hierarchy in the zero-dependency core:
`NodeRenderer` (`src/cnd/core/render.py`), an ABC with one abstract
method per node type and one final concrete `render(node)` that
match-dispatches over the discriminated union with `assert_never`. That
double lock makes incompleteness fail both at runtime (abstract-method
instantiation) and at type-check (exhaustiveness). `MarkdownRenderer` is
the concrete renderer; verbosity is constructor configuration, orthogonal
to format. "Raw" is not a renderer — it is Pydantic's own serialization.
The rich display visitor consumes a renderer by composition and stays in
the optional extra.

This also fixes the layer seam: a **renderer** maps one *node* to a text
fragment; a **converter** maps a whole *CND* to a complete
standalone document artifact (front-matter, assembled sections, pools
rendered) and is built on top of renderers. Converters are future work
(proposal 0007). Both are SDK facilities: spec §7 becomes a non-normative
note, and the format mandates no rendering method.

## Consequences
- A new output format is one `NodeRenderer` subclass; node types never
  change for rendering reasons, and new node types force every renderer
  to say what they do with them.
- Breaking SDK change: every `to_text()` caller migrates to
  `MarkdownRenderer().render(node)` (proposal 0006).
- The format spec and the rendering surface can now evolve independently;
  whole-document conversion has a defined home instead of leaking into
  node methods.
