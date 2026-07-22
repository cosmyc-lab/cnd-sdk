---
title: Figure is a wrapper node; content keeps its own node type
status: proposed
date: 2026-07-18
tags: [nodes, schema, breaking-change, figures]
related: [0006]
superseded-by: null
---

# ADR 0010 — Figure as a wrapper node

## Status
Proposed.

## Context
`FigureNode` has been two things at once: the captioned/numbered float
*wrapper* and an image content *carrier* (`path`, `alt` live on it), while
`TableNode` carries its own `caption`/`fig_number` because a captioned
table could not nest inside a figure. Captioning therefore has two homes,
a figure wrapping code or several images is unrepresentable, and
`FigureNode.kind` keeps drifting toward a content discriminator — the
catch-all failure mode proposal 0004 already rejected. Source formats
treat "figure" as exactly a float that can wrap any body; the CND
should too.

## Decision
`FigureNode` becomes a pure wrapper and never a content carrier: it holds
`children: list[CndNode]`, `caption`, `fig_number`, `kind`, and
`raw_typst` for an unconvertible body (then `children` is empty). `kind`
is an open counter/label selector ("image", "table", author-custom) and
is never a content discriminator — content type is the child node's own
`type`. A new `ImageNode` leaf takes `path`/`alt`; `FigureNode` loses
them, and `TableNode` loses `caption`/`fig_number` outright — no
deprecated alias left behind. Bare content outside any float is just the
leaf node with no wrapper. Nested figures (subfigures) are allowed, and
children carry their own `location` — nothing is inherited from the
wrapper.

## Consequences
- A caption/number has exactly one home; the "which field wins" invariant
  between table and figure disappears.
- Any content — code, math, multiple images — can be captioned by
  composition instead of by growing `FigureNode` fields.
- Traversal must descend into every children-bearing node, not just
  `HeadingNode`; a chunker keeps figures atomic via `stop_predicate`.
- Breaking format change: fixtures migrate captioned tables into figure
  wrappers; `cnd_version` bumps (proposal 0005).
