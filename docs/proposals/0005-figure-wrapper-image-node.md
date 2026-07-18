---
title: Figure as a wrapper node; new ImageNode; TableNode loses its caption
status: implemented
date: 2026-07-18
tags: [nodes, schema, breaking-change, figures]
related: [0006, 0010]
superseded-by: null
---

# Proposal — Figure as a wrapper node; new ImageNode; TableNode loses its caption

## Status
Implemented. Schema-level companion to ADR 0010.

## Motivation
`FigureNode` conflates the float wrapper with image content (`path`,
`alt` live on it), and `TableNode` carries its own `caption`/`fig_number`
because a captioned table cannot nest inside a figure. That leaves
caption data with two possible homes, makes a figure wrapping code — or
several images — unrepresentable, and pushes `FigureNode.kind` toward
becoming a content discriminator. In the source language a figure is
exactly a captioned/numbered float around an arbitrary body; the
manifest should match.

## Proposed change

### `FigureNode` becomes a wrapper
`type: "figure"`, `kind: str | null` (open counter/label selector —
"image", "table", author-custom like "atom"; never a content
discriminator), `caption: str | null`, `fig_number: str | null`,
`children: list[CndNode] = []`, `raw_typst: str | null`. `path` and
`alt` are removed. Nested figures (subfigures) are allowed and intended.
Children carry their own `location`; nothing is inherited from the
wrapper.

### New `ImageNode` leaf
`type: "image"`, `path: str | null`, `alt: str | null` — the content
`FigureNode` no longer carries. A bare image outside any float is an
`ImageNode` with no wrapper.

### `TableNode` loses `caption` and `fig_number`
Hard removal, no deprecated alias — they live only on the wrapping
`FigureNode`. `TableNode` keeps `kind` (`"table" | "grid"`),
`content_kind`, `cells`, `raw_typst`. A bare table is a `TableNode` with
no caption.

```json
{
  "type": "figure",
  "kind": "image",
  "caption": "Pipeline overview",
  "fig_number": "3",
  "children": [
    {"type": "image", "path": "assets/pipeline.png", "alt": "Pipeline diagram"}
  ],
  "raw_typst": null
}
```

Producer mapping (documented in the spec; the producer itself is out of
scope per ADR 0006): a figure around an image/table/raw block wraps the
corresponding `ImageNode`/`TableNode`/`CodeNode`; a multi-body figure
(e.g. a grid of two images) wraps multiple children; an unconvertible
body yields `children: []` with `raw_typst` filled.

### Traversal
`iter_nodes` generalizes to descend into *any* children-bearing node
(today only `HeadingNode`; now also `FigureNode`), setting `parent`
accordingly. `max_depth`/`stop_predicate` semantics are unchanged — a
chunker treats a figure as atomic via `stop_predicate: type == "figure"`.

## Alternatives considered
**Keep content on `FigureNode`, discriminated by `kind`.** Rejected —
`kind` must stay an open counter selector; using it to switch content
shape recreates the catch-all bucket proposal 0004 rejected and breaks
exhaustive typed consumers.

**Leave a deprecated `caption` on `TableNode`.** Rejected — a "two
possible homes, one must be null" invariant is exactly the class of
cross-field consistency rule ADR 0008 just removed; hard removal in one
breaking migration is cheaper than carrying it.

## Impact
Breaking format change, part of the `cnd_version` 0.2.0 bump with
proposals 0004/0006: fixtures migrate every captioned table into a
figure wrapper and every image figure into wrapper + `ImageNode`;
consumers that read `TableNode.caption` or `FigureNode.path` must read
the wrapper/child instead. Traversal-based consumers see figure children
for the first time and may need `stop_predicate` to keep old chunking
behavior.

## Implementation checklist
- [x] spec/cnd-spec.md updated (§6: figure wrapper semantics, `ImageNode`,
      table field removals, nested figures)
- [x] spec/schema/cnd-manifest.schema.json regenerated
- [x] Pydantic models updated (`FigureNode`, `ImageNode`, `TableNode`)
- [x] `iter_nodes` descends children-bearing nodes
- [x] fixtures migrated; new fixtures cover figure-wrapping-code and a
      bare `ImageNode`
- [x] tests updated, tests/test_schema.py passes
- [x] status flipped to `implemented`
