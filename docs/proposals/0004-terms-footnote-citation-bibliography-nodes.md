---
title: Definition lists, footnotes, and citation/bibliography content are missing from the manifest
status: draft
date: 2026-07-18
tags: [nodes, schema, completeness]
related: []
superseded-by: null
---

# Proposal — Definition lists, footnotes, and citation/bibliography content are missing from the manifest

## Status
Draft. Recorded to track a real coverage gap found by auditing a native
content-element list against what a producer's conversion pass currently
handles — not a commitment to a particular node shape or implementation
order yet.

## Motivation
A CND manifest is meant to be a faithful tree representation of a compiled
document (spec §1: "captures... the document body as a tree of typed
nodes"). Auditing the source language's own native structural elements
against what a producer's conversion pass actually converts turns up four
elements with no conversion path at all today — not mis-rendered, entirely
absent from the resulting manifest:

- Definition lists — a first-class structural element, sibling to
  bulleted/numbered lists, which the manifest already models (`ListNode`).
- Footnotes — supporting prose attached to a point in the document,
  silently dropped.
- Inline citations — references to bibliography entries.
- The bibliography/reference-list section itself — the cited works' own
  bibliographic data (authors, titles, years).

By contrast, decorative or fully-derived content correctly has no node
representation today — an auto-generated table of contents duplicates
information already present in the heading tree, and inline text
formatting/links are already captured as part of their containing
paragraph's text. The four items above are different: they carry content
that exists nowhere else in the tree once dropped.

This is a format-completeness question, not a rendering-policy question —
a manifest missing this content isn't something a consumer can correct
after the fact; the source material simply isn't there to work with.

## Proposed change
Not fully decided — this proposal establishes scope and a starting shape,
not a final schema.

Two of the four are self-contained and structurally straightforward:

1. **A `TermsNode` type**, modeled on the existing `ListNode`/`ListItem`
   pair — a list of (term, description) pairs. Sibling in the
   discriminated `CndNode` union; `to_text()` renders both parts
   unconditionally — a definition list is always textual, with no
   rendering-mode ambiguity the way `TableNode.content_kind` has.
2. **A `FootnoteNode` type**, holding the footnote's own text, linked to
   its anchor point in the surrounding content through the existing
   `refs_to`/`refs_from` cross-reference graph (spec §5) rather than being
   nested inside the anchoring node — footnote content is logically
   attached to a point, not a container.

The other two are a connected pair and structurally harder, because
resolving a citation to the bibliography entry it points at requires
correlating two separate elements rather than simple label matching:

3. **A `BibliographyNode` type** (or a list of structured entries)
   carrying each cited work's bibliographic fields, independent of whether
   any citation to it resolves — this half stands alone and answers "what
   sources does this document draw on" on its own.
4. **Citation edges** — inline citations as `NodeRef`-shaped pointers from
   the citing node to the corresponding bibliography entry, following the
   existing `refs_to` graph pattern rather than inventing a new pointer
   shape.

Whether (3)/(4) ship together or (3) ships first as a standalone addition
is open — (3) alone is useful with no dependency on citation resolution
working.

## Alternatives considered
**Route all four through the existing `FigureNode.kind` field instead of
new node types.** Rejected: `FigureNode` represents a captioned float
(spec §6.7 — `caption`, `fig_number`, `kind`, `alt`, `path`) and none of
these four are that; using it as a catch-all bucket for "any content type
without a proper node yet" is exactly what produced the current situation
where `kind` is a free `string | null` with no enforced vocabulary. A
discriminated node type per content shape keeps `to_text()` and any future
consumer-side visitor exhaustive and type-checked, consistent with how
`QuoteNode`/`CodeNode`/`MathNode` were each given their own type rather
than folded into `FigureNode`.

**Do nothing, treat this as a producer-only concern.** Considered and
rejected for the same reason ADR 0006 keeps this SDK owning the manifest
shape: if a producer cannot represent this content in any manifest node,
no producer implementation can close the gap on its own — the schema has
to grow the vocabulary first.

## Impact
Additive to the schema: new node types joining the `CndNode` discriminated
union, no change to existing node types' meaning. A version bump for the
format (`cnd_version`) is expected, consistent with how prior node-type
additions were versioned. Any producer implementation still needs its own
follow-up work per node type once the schema exists — out of this SDK's
scope per ADR 0006, tracked separately from this proposal.

## Implementation checklist
- [ ] Decide `TermsNode`/`FootnoteNode` field shapes precisely (mirroring
      `ListNode`/`ListItem` and the `refs_to` anchor pattern respectively)
- [ ] Decide whether `BibliographyNode` ships standalone before
      citation-edge resolution, or the two land together
- [ ] Define the citation edge shape (reuse `NodeRef`, or does resolving
      to a bibliography entry need its own pointer type)
- [ ] spec/cnd-spec.md updated with the new node types and, if applicable,
      the citation edge shape
- [ ] spec/schema/cnd-manifest.schema.json regenerated
- [ ] Pydantic models updated (`cnd.core.nodes`)
- [ ] tests updated, tests/test_schema.py passes
- [ ] status flipped to `implemented`
