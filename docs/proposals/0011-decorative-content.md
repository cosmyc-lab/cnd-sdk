---
title: Content marked decorative is never emitted
status: implemented
date: 2026-10-10
tags: [producers, normative, accessibility]
related: [0004, 0009]
superseded-by: null
---

# Proposal — Content marked decorative is never emitted

## Status
Implemented (spec §2). Producer behaviour only, so there is no schema change and no `cnd_version` bump.

## Motivation
A built page carries content that means nothing on its own: logos, ornaments, icons before a heading, watermarks, rules, page backgrounds, a cover's artwork. An author sees it as presentation. A CND that emits it hands it to every consumer as content:
- an ornament glyph lands in a paragraph's text;
- a logo becomes an image node between two sections;
- a watermark word is indexed and retrieved as if the author had written it.

The consumer cannot tell these apart from real content after the fact. Only the author knows, at the source.

Source formats already give authors a way to say it:
- **Tagged PDF:** an *artifact* is content that is not part of the logical structure.
- **Typst:** `pdf.artifact` marks exactly that.
- **HTML:** `aria-hidden="true"` and `role="presentation"` / `role="none"` tell assistive technology to skip an element.

The specification is silent today. One producer may honour the marker while another emits the content, and the same source then yields different CNDs.

## Proposed change
Add a normative rule to §2:

> **Decorative content (normative)**: content the source marks as
> decorative — present for presentation only, carrying no meaning — is not
> part of the document. A producer MUST NOT emit it: it yields no node, no
> text inside another node's text, no pool entry, and no link edge.

Consequences the rule spells out:

1. **References into decorative content.** A label inside decorative content does not exist in the CND. A reference to it from kept content therefore yields no `refs` edge. The reference's rendered text, if any, stays in the kept node's text like any other words. Every edge in a conformant CND still resolves (§5).
2. **Footnotes.** A footnote declared inside decorative content gets no pool entry. Neither its own marker nor a re-reference to it from kept content yields a `footnotes` edge. Rendered ordinals are layout results: a kept footnote keeps the label the built document shows, even when a decorative footnote consumed a number before it.
3. **Nesting.** Everything inside decorative content is decorative, whatever its element kind (heading, table, figure, list…).
4. **The declarative door** (§12) is unaffected: a declaration simply does not declare decorative content.

What counts as a decorative marker is the producer's mapping from its source format, as with every other element mapping (§6). Informative mappings:

| Source | Marker |
|---|---|
| Typst | `pdf.artifact(..)` |
| Tagged PDF | Artifact content (ISO 32000, `/Artifact` marked content) |
| HTML | `aria-hidden="true"`, `role="presentation"`, `role="none"` |

The rule does not make anything decorative by inference. A producer that guessed, for example by treating every image without alt text as decorative, would drop content the author meant. Only an explicit marker counts.

## Alternatives considered
- **A `decorative: true` flag on nodes.** Rejected. Every consumer would have to filter, and one that forgot would leak the content. A field nobody should read is noise in the tree, and the rule that derived data is never serialized argues against fields that exist only to be ignored.
- **Leave it to consumers** (strip by heuristics). Rejected. A consumer cannot recover what only the author knew, and each would guess differently.
- **A dedicated node type** holding decorative content for renderers that want it. Rejected for now. No consumer has asked for it, and a CND describes meaning, not page decoration. If a use appears, it is an additive change.

## Impact
- **Producers:** must honour their format's decorative marker. The reference Typst producer already drops artifacts for every element kind.
- **Consumers:** nothing to do. Content they no longer receive was noise.
- **Conformance:** not checkable from a CND alone, since a validator cannot see what was dropped. It is a producer obligation, tested by the producer's own suite.

## Implementation checklist
- [x] Spec §2: "Decorative content (normative)"
- [x] `docs/README.md` index row
- [x] `CHANGELOG.md` entry
