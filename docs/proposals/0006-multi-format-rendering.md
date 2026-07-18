---
title: Multi-format rendering via renderer classes; remove to_text()
status: implemented
date: 2026-07-18
tags: [rendering, sdk, breaking-change]
related: [0006, 0011]
superseded-by: null
---

# Proposal — Multi-format rendering via renderer classes; remove `to_text()`

## Status
Implemented. SDK-level companion to ADR 0011. **Supersedes proposal 0001**
(configurable table/figure rendering in `to_text()`): the verbosity modes
0001 introduced survive unchanged as renderer configuration, but the
`to_text()` / `render_node_text(mode=...)` surface they were bolted onto
is removed. Proposal 0001 is marked `superseded-by: 0006`.

## Motivation
`to_text()` on every node bakes exactly one output format into the data
classes, and proposal 0001 had to add a parallel entry point
(`render_node_text(mode=...)`) just to make verbosity configurable
without touching that contract. A second format (HTML, or a future
DocLang) would mean another method on every node type. Rendering is an
SDK concern layered on the format, not part of it (ADR 0006) — it
belongs in classes that dispatch over nodes, not in methods on them.

## Proposed change

### Nodes become pure data
`to_text()` is removed from every node type; `render_node_text(mode=...)`
is absorbed. "Raw" output is not a renderer — it is Pydantic's own
`repr()` / `model_dump_json()`; nothing is added for it.

### `NodeRenderer` ABC in the zero-dependency core
`src/cnd/core/render.py`: one abstract method per node type
(`render_heading`, `render_paragraph`, `render_table`, `render_quote`,
`render_code`, `render_math`, `render_figure`, `render_list`,
`render_terms`, `render_image`) and one concrete final `render(node)`
that `match`-dispatches over the discriminated union with `assert_never`.
Incomplete subclasses fail at instantiation (ABC) and at type-check
(exhaustiveness) — a new node type forces every renderer to answer for
it.

### `MarkdownRenderer(NodeRenderer)`
The one concrete content renderer. Verbosity is constructor
configuration, orthogonal to format:

```python
MarkdownRenderer(tables: NodeTextMode = "placeholder",
                 figures: NodeTextMode = "placeholder")
```

`NodeTextMode = Literal["placeholder", "inline", "auto"]` survives from
proposal 0001; `"auto"` resolves from `content_kind` exactly as
proposals 0001/0002 defined. Concrete forms: heading → `#`×level + text;
paragraph/math → text; quote → text + attribution line; code → fenced
block; list → bullets/numbers (existing helper); terms → a markdown
definition-list form (`**term**` + indented description); table →
inline pipe grid / placeholder / auto by `content_kind`; image →
`![alt](path)`, never empty (bracket placeholder when pathless), never
the caption (that is the wrapper's); figure → placeholder
`[[figure:id kind=… number=… caption=… summary=…]]` with `summary`
derived from children, or inline = children rendered recursively under a
`*Figure N: caption*` line. The `cnd.core.node_text` helpers become
shared plumbing the renderer calls.

### Spec change
Spec §7 is rewritten as "Rendering (SDK, non-normative)": the format
mandates no rendering method; the reference SDK provides renderers;
`MarkdownRenderer` produces CommonMark-ish text whose exact details are
not normative.

## Alternatives considered
**Keep `to_text()` and thread `mode=` through it** — proposal 0001's
shipped approach. Superseded: it scales per-format as a method on every
node, and per-config as parameters on every method; a renderer class
scales as one subclass per format with config in its constructor.

**A `RawRenderer` for debug output.** Rejected — Pydantic already
serializes the model faithfully; a renderer would duplicate it.

**Fold the rich `NodeDisplayVisitor` into the renderer hierarchy.**
Rejected — `rich` is an optional extra and the core must not import it
(CLAUDE.md invariant, ADR 0005); the display visitor *consumes* a
renderer for its text parts by composition.

## Impact
Breaking SDK change (package 0.3.0, alongside format 0.2.0): every
`to_text()` / `render_node_text` caller migrates to
`MarkdownRenderer().render(node)`. The manifest format itself is
untouched by this proposal except for §7 becoming non-normative. Default
behavior is preserved: a default-constructed `MarkdownRenderer` renders
tables and figures as placeholders, as `to_text()` did.

## Implementation checklist
- [x] spec/cnd-spec.md §7 rewritten as non-normative SDK note
- [x] `NodeRenderer` ABC + `MarkdownRenderer` in `src/cnd/core/render.py`
- [x] `to_text()` removed from all node types; `render_node_text` removed
- [x] `NodeDisplayVisitor` consumes a renderer; handles new node types
- [x] tests render every node type from fixtures through
      `MarkdownRenderer`
- [x] tests updated, tests/test_schema.py passes
- [x] status flipped to `implemented`; proposal 0001 marked superseded
