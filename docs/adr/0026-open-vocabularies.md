---
title: Open vocabularies — known values, free values, a fallback per field
status: accepted
date: 2026-10-13
tags: [schema, extensibility, 0.5.0]
related: [0010]
superseded-by: null
---

# ADR 0026 — Open vocabularies

## Status
Accepted.

## Context
Several CND fields take a value from a list the specification defines,
but must also accept values an author or producer invents. `figure.kind`
already worked this way (ADR 0010): `"image"` and `"table"` sit beside an
author's `"atom"` or `"theorem"`. Format 0.5.0 adds more fields of the
same nature — the kind of an admonition (`"warning"`, but also an
author's `"example"`), the kind of an inline mark, the kind of a table —
and existing ones already behave this way without saying so: `code.lang`,
`raw.format`, `source.type`.

Each field had its own unwritten rules: whether a producer may invent a
value, what a consumer does with one it does not know, how a common
invented value becomes standard. A closed enum would force a
specification revision for every new producer or author convention. A
plain string with no contract leaves producers minting near-duplicates
(`"warn"` beside `"warning"`) and consumers failing in different ways.

## Decision
These fields are **open vocabularies**, and they share one contract
(docs/proposals/0013, principle 3):

1. **Known values** have a definition in the specification. A producer
   uses a known value whenever one fits; it does not mint `"warn"` when
   `"warning"` exists.
2. **Free values** are any other string, written as is.
3. **Consumers never fail on an unknown value.** Each open field
   documents its fallback — ignore the value, treat it as unstated, or
   render a generic form.
4. **Promotion.** A free value in wide use becomes a known value in a
   minor version.

The open vocabularies of format 0.5.0 are `figure.kind`,
`admonition.kind`, `Mark.kind`, `table.kind`, `code.lang`, `raw.format`,
`source.type`, and the keys of `doc.extra`.

Closed enumerations stay closed where a consumer must understand the
value exactly to process the data. The node `type` discriminator is one:
an unknown node type cannot be read.

## Consequences
- **No `x-` prefix.** A prefixed free value has to be renamed everywhere
  on the day it becomes standard; that is the lesson of RFC 6648, which
  deprecated the practice for protocol parameters. A free value is
  written as is, and promotion changes nothing in existing files.
- **Every open field documents its fallback** in the specification
  (spec §6.0). A field added later as an open vocabulary must come with
  one, or it is not open.
- **Promotion happens in a minor version**: a new known value adds a
  definition and never changes the meaning of an existing file.
- The schema types these fields as plain strings. The known values live
  in the specification and, in the reference SDK, in constants such as
  `KNOWN_MARK_KINDS` and `KNOWN_ADMONITION_KINDS`; validation never
  rejects a free value.
