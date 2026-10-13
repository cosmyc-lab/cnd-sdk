---
title: Inline edges belong to rich text, not to the node
status: accepted
date: 2026-10-13
tags: [schema, breaking-change, refs, rich-text, 0.5.0]
related: [0008, 0009, 0013, 0024]
superseded-by: null
---

# ADR 0025 — Inline edges belong to rich text

## Status
Accepted. Updates where ADRs 0009 and 0024 place the link families; their
other decisions stand.

## Context
Up to format 0.4.0, the four link families (`refs`, `cites`,
`footnotes`, `links`) live on the node base (ADR 0009, ADR 0024), and an
edge's `text_span` locates its marker in "the node's rendered text"
(ADR 0013). That phrase is well defined for a paragraph, which has one
text. It is ambiguous for every node that has several: a table (which
cell?), a figure (the caption, or something else?), a term list (which
term?). Two implementations that render the same node differently place
the same span on different characters, and nothing in the file says
which one was meant.

Format 0.5.0 makes the ambiguity worse and the fix possible at once
(docs/proposals/0013). Prose becomes a `RichText` object — a `value`
string with standoff marks — in every slot that holds prose, and nodes
gain more texts: a figure has a caption and a description, an
admonition a title, a quote an attribution. Marks need to know which
text they index; so do edges. Keeping edges on the node would need a
locator for every multi-text node (`"in": "cells[3]"`), a path string
every consumer must parse and that breaks when the structure moves.
Defining one canonical rendered text per node would tie every span to a
rendering rule, so that changing the rule shifts every span.

## Decision
The four families live on `RichText`, beside `marks`. Every span — a
mark or an edge's `text_span` — indexes the `value` of the `RichText`
that holds it, in Unicode code points (ADR 0013).

1. **An edge belongs to the text where its marker opens.** Its owning
   node is the nearest node that holds that text; an edge in a
   bibliography entry's `formatted` text is owned by the entry.
   `text_span` stays nullable, for a marker that renders no text (a
   `form: "none"` citation) or one that does not close inside the text.
2. **The families keep their contracts.** They stay forward-only
   (ADR 0008): a CND serializes no incoming edge. `refs`, `cites` and
   `footnotes` stay label-keyed and resolve in their family's domain
   (ADR 0017). `links` stays href-keyed and outside label resolution
   (ADR 0024).
3. **No node carries a link family.** The node base keeps `id`, `label`,
   `state_metadata` and `location`.

## Consequences
- `NodeBase` loses `refs`, `cites`, `footnotes` and `links`. A 0.4.0 CND
  does not parse as 0.5.0; under the pre-1.0 policy (ADR 0027) that is
  allowed, and no upgrader is shipped.
- The SDK adds `texts_of(node)` — the node's own texts in document order,
  never a nested node's — and `edges_of(node)`, the edges of those texts
  flattened. Code that used to read one list per node reads one list per
  node again.
- The derived incoming index (`Cnd.incoming`) and validation read texts.
  Validation also checks the edges and marks of a bibliography entry's
  `formatted`, and every `text_span` against the length of its own
  `value`.
- There is no "rendered text of a node" left to define. Renderers may
  render a node however they like without moving any span.
- A node with several texts reports the edges of each text separately in
  the file; a consumer that wants every outbound edge of a node flattens
  them, as `edges_of` does.
