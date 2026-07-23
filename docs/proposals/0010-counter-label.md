---
title: Capture the counter label as its own field, beside the number
status: implemented
date: 2026-07-23
tags: [schema, fields, numbering, localization, 0.3.0]
related: [0012, 0016]
superseded-by: null
---

# Proposal — Capture the counter label as its own field

## Status
Implemented (SDK 0.4.0, format 0.3.0). Additive to the 0.3.0 wave (docs/proposals/0008), which is not yet
published, so it lands under the same `cnd_version` rather than a bump.

## Motivation
Proposal 0008 collapsed three numbering fields into one resolved `number`
and excluded the counter-label word: `"Figure 3"` bakes a locale into data,
and composing the prefix is a rendering decision. That reasoning holds, and
`number` stays as 0008 defined it.

What 0008 got wrong is treating exclusion from `number` as a reason to drop
the word entirely. Two facts, both verified in the reference producer,
show it is not always derivable:

1. Typst resolves a figure's supplement from the **kind and the document
   language** (`figure.rs`, `local_name(lang, region)`). For a built-in
   kind that word *is* derivable — but only by a consumer holding Typst's
   localization table, which no consumer has.
2. For a **custom kind** Typst has no localized name and therefore
   *requires* the author to supply one:

```typ
#figure(circle(radius: 10pt), caption: [A curious atom.],
        kind: "atom", supplement: [Atom])
```

Here the word is authored data with no derivation path at all. Capitalizing
`kind` happens to reproduce it in this example and does not in general —
`kind: "atom", supplement: [Élément]` is equally valid.

So the current format loses information it cannot reconstruct, and every
consumer that wants to render a document faithfully — a converter back to
Markdown, an editor preview — has to invent a word.

## Proposed change

Add a nullable **`counter_label`** to the three node types that carry
`number`: `heading`, `math`, `figure`.

```json
{
  "type": "figure",
  "kind": "atom",
  "number": "1",
  "counter_label": "Atom",
  "caption": "A curious atom."
}
```

It carries the label **as resolved and displayed**, in the document's
language, exactly parallel to `number` carrying the counter value as
displayed. A renderer composing a prefix uses `counter_label` + `number`;
a consumer wanting locale-free structure uses `kind`.

This is the same shape the format already uses for `BibEntry.formatted`
(the reference string as displayed, beside the structured fields that
generated it): a faithful capture of presentation *beside* the structured
data, never fused into it. The defect 0008 fixed was the **fusion**
(`"Figure 3"` in one string), not the presence of the word.

### Naming: `counter_label`, not `supplement`
Typst calls this a supplement, and this format already has a
`supplement` — on `cites`, meaning a locator inside the cited work
(`"p. 12"`, spec §5). Typst carries both senses under one word; importing
that collision would put two unrelated meanings behind one field name in
one schema, which is the reading trap ADR 0021 argues against and the same
collision that forced `BibEntry.raw` to become `fields` in 0008.

`counter_label` also fits the vocabulary already in the spec, where `kind`
is described as "the counter/label selector": `kind` selects the counter,
`number` is its value, `counter_label` is its displayed word.

## Alternatives considered
- **Emit it only when author-supplied** (i.e. only the non-derivable
  case). Rejected: a consumer cannot tell "this figure has no label" from
  "this label was derivable", and deriving it needs a localization table
  the consumer does not have. The field would be present exactly when a
  consumer cannot predict it, which makes it unusable as a rendering
  input.
- **Put it back inside `number`.** Rejected — that is the defect 0008
  fixed. Separate fields let a consumer take the locale-free value alone.
- **Carry it in `state_metadata`.** Rejected: the extension bag is for
  producer-specific state the standard does not interpret. This is a
  general property of numbered elements in any document format, not a
  Typst quirk.
- **Reuse the name `supplement`.** Rejected — see above.

## Impact
Additive and non-breaking within 0.3.0: a nullable field on three node
types. Nothing that reads 0.3.0 today breaks.

- Hashing: `counter_label` is **excluded** from the content hash, for the
  same reason `number` is (ADR 0016). It is resolved presentation state —
  it changes when the document language changes, without the authored
  content changing.
- The reference Typst producer stops discarding the supplement it already
  resolves.

## Implementation checklist
- [x] spec/cnd-spec.md §6 updated (defined once beside `number`)
- [x] schema/cnd.schema.json regenerated
- [x] Pydantic models updated (`heading`, `math`, `figure`)
- [x] excluded from `node_hash`; `fixtures/hashes.json` unchanged as proof
- [x] fixtures carry it where the producer would emit it
- [x] tests updated, tests/test_schema.py passes
- [x] status flipped to `implemented`
