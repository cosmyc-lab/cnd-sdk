---
title: Terms nodes; footnote and bibliography pools; typed citation edges
status: implemented
date: 2026-07-18
tags: [nodes, pools, refs, schema, breaking-change]
related: [0002, 0008, 0009]
superseded-by: null
---

# Proposal — Terms nodes; footnote and bibliography pools; typed citation edges

## Status
Implemented. This rewrites the earlier draft of this proposal, which recorded
the coverage gap but leaned toward "everything is a node"
(`FootnoteNode`, `BibliographyNode`). That direction is now wrong: the
agreed design is two-tier (ADR 0009) — only content with a reading-flow
position becomes a node; referenceable out-of-flow content becomes
top-level pool entries reached through typed link families.

## Motivation
A CND manifest is meant to be a faithful tree representation of a
compiled document (spec §1). Auditing the source language's native
structural elements against what a producer's conversion pass handles
turns up four elements with no representation at all — not mis-rendered,
absent:

- Definition lists — a first-class structural sibling of the
  bulleted/numbered lists the manifest already models (`ListNode`).
- Footnotes — supporting prose attached to a point in the text.
- Inline citations — references to bibliography entries, including their
  rendering form (`@key` vs. "Author (Year)" vs. suppressed).
- The bibliography itself — the cited works' bibliographic data.

This content exists nowhere else in the tree once dropped; a consumer
cannot reconstruct it after the fact. The four split cleanly across the
two tiers: a definition list is a block in the reading flow (a node); a
footnote or bibliography entry is referenced *from* the flow but sits
outside it (a pool entry).

## Proposed change

### In-tree: `TermsNode`
A new member of the discriminated `CndNode` union, modeled on
`ListNode`/`ListItem`: `type: "terms"`, `items: list[TermItem]`,
`tight: bool = true`. `TermItem = {term: str, description: str}` — flat
text, no `id`, not ref-targetable, same as `ListItem`/`TableCell`.

```json
{
  "type": "terms",
  "items": [
    {"term": "manifest", "description": "The serialized document tree."},
    {"term": "pool", "description": "Out-of-tree referenceable entities."}
  ],
  "tight": true
}
```

### Out-of-tree: two pools on the manifest
Top-level fields on `CndManifest`, siblings of `nodes`, always present
(default `[]`, never null):

- `footnotes: list[Footnote]` with `Footnote = {id, label, text}` — flat
  text only; block/subtree content inside footnotes is deliberately not
  modeled at this cut.
- `bibliography: list[BibEntry]`. Each entry is lossless-plus-curated:
  `id`, `label` (the source `@key`), `rendered` (required — the reference
  string as displayed in the compiled document), a curated typed optional
  subset (`type`, `authors: list[str]`, `title`, `year`, `container`,
  `doi`, `url`), and `raw: dict` — the full source entry (e.g. Hayagriva)
  passed through as *structured JSON*, carrying every field the typed
  subset doesn't.

```json
{
  "bibliography": [
    {
      "id": "6b6f7a2e-…",
      "label": "smith2024",
      "rendered": "Smith, J. (2024). Context-native pipelines. JODS 12(3).",
      "type": "article",
      "authors": ["Smith, J."],
      "title": "Context-native pipelines",
      "year": 2024,
      "container": "JODS",
      "doi": null,
      "url": null,
      "raw": {"type": "article", "page-range": "101-118"}
    }
  ],
  "footnotes": [
    {"id": "0f9c…", "label": "1", "text": "First noted in the 2023 audit."}
  ]
}
```

### Link families on nodes
Per ADR 0009, every node carries three forward-only lists with the shared
skeleton `{id, label, span?}`:

- `refs: list[NodeRef]` — resolves in `nodes`. `NodeRef` keeps its
  canonical `{id, label}` core (ADR 0002) and gains optional
  `span: [int, int] | null` for positioned markers.
- `cites: list[CiteRef]` — resolves in `bibliography`. `CiteRef` adds
  `form: "normal" | "prose" | "full" | "author" | "year" | "none" | null`
  and `supplement: str | null`. `span` must stay nullable: a
  `form: "none"` citation renders no text and has no span.
- `footnotes: list[FootnoteRef]` — resolves in the footnotes pool;
  `FootnoteRef = {id, label, span?}`.

```json
{
  "type": "paragraph",
  "text": "Pipelines drift without manifests [1].",
  "cites": [
    {"id": "6b6f7a2e-…", "label": "smith2024", "span": [34, 37],
     "form": "normal", "supplement": "p. 104"}
  ],
  "footnotes": [
    {"id": "0f9c…", "label": "1", "span": [15, 15]}
  ]
}
```

Invariants (spec §5): the id field is named `id` everywhere — the
resolution domain is carried by the field, not the field name; a link's
`label` mirrors its target's `label`; ids are globally unique across all
nodes and pool entries; spans are offsets in Unicode code points into the
containing node's rendered text.

## Alternatives considered
**Everything as nodes** (this proposal's own first draft): a
`FootnoteNode` anchored through the generic ref graph, a
`BibliographyNode` holding entries. Rejected — footnotes and bibliography
entries have no reading-flow position, so each node would need a fake
`location`, and generic `NodeRef` anchoring cannot carry citation form or
supplement without bloating the shape every other ref uses.

**Route the content through `FigureNode.kind`.** Still rejected, for the
reason the first draft gave: none of these are captioned floats, and a
catch-all `kind` destroys exhaustive, type-checked consumers. ADR 0010
now pins `kind` as a counter selector, never a content discriminator.

**One unified link list with a domain tag per entry.** Rejected —
separate typed fields keep each list homogeneous, let `CiteRef` grow
citation metadata without touching `NodeRef`, and make the resolution
domain statically knowable.

**Bibliography passthrough as a YAML string.** Rejected — `raw` as
structured JSON keeps the manifest self-describing under one schema.

## Impact
Breaking format change, shipped with proposals 0005/0006 in the single
`cnd_version` 0.2.0 bump: two new always-present top-level pools, the
three link families on every node (alongside ADR 0008's
`refs_to`→`refs` rename), one new node type. Fixtures migrate; the
reverse index stays SDK-derived (`CndManifest.incoming`). Producer
support for emitting the new content is out of scope per ADR 0006.

## Implementation checklist
- [x] spec/cnd-spec.md updated (§5 link families and invariants, §6
      `TermsNode`, new out-of-tree entities section)
- [x] spec/schema/cnd-manifest.schema.json regenerated
- [x] Pydantic models updated (`TermsNode`, `Footnote`, `BibEntry`,
      `CiteRef`, `FootnoteRef`, `NodeRef.span`, manifest pools)
- [x] fixtures cover a terms node, a citation + bibliography entry, a
      footnote
- [x] tests updated, tests/test_schema.py passes
- [x] status flipped to `implemented`
