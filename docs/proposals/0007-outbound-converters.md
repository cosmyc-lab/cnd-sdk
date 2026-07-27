---
title: Outbound converters — a whole CND to a complete document artifact
status: draft
date: 2026-07-18
tags: [converters, rendering, sdk, outbound]
related: [0006, 0011, 0014, 0019, 0020, 0021]
superseded-by: null
---

# Proposal — Outbound converters: a whole CND to a document artifact

## Status
Draft — **partially implemented**. Targets 1 (markdown) and 2 (html) ship
in `src/cnd/converters/`; target 3 (doclang) is not started, so the status
stays `draft` rather than `implemented`.

Revised 2026-07-22 and **narrowed to the outbound direction only**. An earlier
revision extended this proposal to cover `foreign → CND` as well; that
direction has since been decided to be *production*, not consumption — it is
governed by ADR 0019's two doors and specified separately. Converting a CND
into some other artifact and producing a CND from some other format no longer
share an architecture, a home, or a lifecycle, so they no longer share a
document. Vocabulary follows ADR 0021: the built artifact is **the CND**.

## Motivation
ADR 0011's renderers answer "give me text for this *node*" — a fragment,
consumed by chunkers, display, or embedding pipelines. They deliberately
do not answer "give me this *document*": a complete standalone artifact
needs everything a fragment doesn't — document front-matter, sections
assembled in order from the tree, and the out-of-tree pools
(bibliography, footnotes — proposal 0004) rendered into actual reference
lists and note sections with resolved markers. Today a consumer wanting a
whole document has to hand-assemble that from renderer output; the SDK
should own the assembly once.

## Proposed change
A new `converters/` module in the SDK. The layer split, per ADR 0011:

- A **renderer** (`NodeRenderer`) maps one node to a text fragment.
- A **converter** maps a whole `Cnd` to one complete, standalone
  document artifact, and is *built on top of* a renderer: it walks the
  tree in order, delegates each node's body text to the renderer, and
  itself owns everything that only exists at CND scope — title/
  metadata front-matter, section assembly, resolving `cites`/`footnotes`
  markers against the pools, and emitting the bibliography and footnote
  sections from the pools.

Targets, in intended order:

1. **cnd → markdown** — a real `.md` file: front-matter, assembled
   sections, footnotes and a bibliography section rendered from the
   pools. Built directly on `MarkdownRenderer`.
2. **cnd → html** — a full standalone `.html` document (not fragments).
3. **cnd → doclang** — DocLang is now sourced and its positioning recorded in
   ADR 0014, which unblocks this target; the element-by-element mapping is
   still to be designed. Known permanent loss: the citation model
   (`CiteRef.form`/`supplement`, the bibliography pool's structured fields)
   has no typed target in DocLang.

Converters are SDK facilities, non-normative for the format (ADR 0006 /
ADR 0011): no converter output shape ever becomes a conformance
requirement, and the module must not add hard dependencies.

**Where these live.** An outbound converter reads a built CND and emits
something else — that is *consumption*, and it is built on the renderer
hierarchy, which is per-language and non-normative (ADR 0011, spec §7). Under
ADR 0020 it therefore belongs with the per-language SDKs rather than with the
conformance hub, and it travels with the Python stack when that stack leaves
the hub. Nothing here is part of what the hub certifies.

## Alternatives considered
**Grow renderers until they cover whole documents.** Rejected — a
renderer is dispatch-per-node and has no CND in hand; pool
resolution and document assembly would force CND context into every
render method signature. The two layers have different inputs by design.

**Leave assembly to consumers.** The status quo; workable but every
consumer re-implements pool resolution and ordering. Owning it once in
the SDK is the point of this proposal — rejected as the end state, fine
as the interim.

## Impact
Additive, SDK-only — no change to the CND format, schema, or spec
conformance sections. The concrete converter API (streaming vs. string,
asset handling for `ImageNode` paths) is undecided and part of the work.

## What shipped
`src/cnd/converters/`, zero new dependencies:

- `base.py` — `CndConverter` (the ABC, takes an injectable `NodeRenderer`,
  one `convert(cnd) -> ConversionResult` method), `ConversionResult`
  (`text` plus flat per-document `warnings`), `iter_body` (reading-order
  walk that prunes figure subtrees, since a renderer's `render_figure`
  already owns them), `resolve_markers` (label resolution with family
  domain checks, ordered by `text_span` where one exists).
- `markdown.py` — `MarkdownConverter` on `MarkdownRenderer`, plus
  `format_bib_entry`.
- `html.py` — `HtmlConverter` and the `HtmlNodeRenderer` it is built on.
  That renderer lives with the converter, not in `cnd.core.render`:
  spec §7 enumerates the renderers the core ships, and adding to that
  list is an ADR 0011 / spec decision, not a converter's to take in
  passing.

Golden documents in `tests/golden/`, regenerated by
`scripts/regen_converters_golden.py`. They are non-normative.

**Two losses per converter are documented in the class docstrings**: the
irreducible ones (the same for every document — `text_span` positions,
`state_metadata`, `location.page`, most of `CiteRef.form`, `RawSource`,
`BibEntry.fields`) and the per-document ones, which surface as
`ConversionResult.warnings`. Neither direction round-trips and no
converter claims reversibility.

**Known gap — the bibliography.** `BibEntry.formatted` is nullable since
0.3.0. `format_bib_entry` prefers it verbatim when present; when it is
`None` it composes a deliberately minimal string from the lifted fields
(`authors`, `year`, `title`, `container`, `doi`, `url`) and warns. That
composition follows **no** citation style and does not read the `fields`
blob. Turning structured fields into a styled reference is a style
engine's job and stays out of scope for the SDK — a caller who needs real
styling runs one and sets `formatted`.

## Implementation checklist
- [ ] Source and pin the DocLang specification (blocking for target 3)
- [x] Design the converter API (input CND, renderer injection,
      output type)
- [x] `converters/` module with cnd→markdown built on `MarkdownRenderer`
- [x] cnd→html standalone document converter
- [ ] cnd→doclang converter once the spec exists
- [x] tests: full-document golden outputs from fixtures
- [x] spec note (non-normative, mirroring §7's rendering note)
- [ ] status flipped to `implemented`
