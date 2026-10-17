---
title: Typst authoring markers — labelled metadata and a code-title state key
status: accepted
date: 2026-10-17
tags: [typst, authoring, toolchain, 0.5.0]
related: [0023]
superseded-by: null
---

# ADR 0030 — Typst authoring markers

## Status
Accepted. Extends ADR 0023. ADR 0023's decision stands: the authoring
package is a pure-Typst file whose only contract is data a stock toolchain
can produce, and a helper takes already-built content.

## Context
Format 0.5.0 adds facts an author states and no Typst construct carries:
the document's printed `status` and `version` and its other title-page
pairs (spec §3), the kind and title of an admonition (spec §6.11), and the
title of a code listing (spec §6.5). ADR 0023 gave the package one
mechanism, the `cnd.metadata` state, used for the table kind. That
mechanism fits a property of one span of content. It does not fit a
document-level fact, which has no span, nor a callout whose children are
whole blocks.

## Decision
Three helpers join `cnd.typ`, each using the mechanism that fits.

- `cnd.document(status:, version:, extra:)` emits one labelled `metadata`
  element, `<cnd-document>`, whose value is
  `(status:, version:, extra:)`. A reader finds it with
  `query(<cnd-document>)`. It rejects a non-string `extra` value and any
  `extra` key that repeats a `DocMetadata` field name (`title`, `authors`,
  `date`, `keywords`, `description`, `lang`, `status`, `version`, `extra`),
  the same rule as spec §3. The title, authors, date, keywords,
  description and language keep coming from Typst's own `set document(..)`
  and `set text(lang: ..)`.
- `cnd.admonition(body, kind:, title:)` emits `<cnd-admonition>` (value
  `(kind:, title:)`), then a styled block holding the title, when given,
  as its first child under `<cnd-admonition-title>`, then the body, then
  `<cnd-admonition-end>`. A reader pairs the two markers and reads the
  content between them as the admonition's children. `kind` is an open
  vocabulary (spec §6.0).
- `cnd.code(body, title:)` brackets already-built content with a
  `code-title` key in the `cnd.metadata` state, set before and removed
  after, exactly as `table` does with `table-kind`. It takes content so the
  span stays at the document's call site (ADR 0023).

Labelled `metadata` markers serve facts with no span of their own: they
are queryable on any toolchain and cost nothing in the output. The state
key serves a property of one piece of content, which the emitter already
reads by following that content. A third mechanism was not needed.

There is no helper for a task-list item's `checked` flag: Markdown-style
checkboxes are not authored in Typst, and the field stays absent from
Typst-produced CNDs until a construct for it exists.

## Consequences
- A document gains `#cnd.document(..)`, `#cnd.admonition(..)` and
  `#cnd.code(..)` as opt-in markup. One that uses none compiles as before.
- The package's public contract grows by four label names
  (`cnd-document`, `cnd-admonition`, `cnd-admonition-title`,
  `cnd-admonition-end`) and one state key (`code-title`). Changing a
  value's shape is a compatibility concern for every producer reading it.
- Inside `cnd.typ`, the built-in `metadata` is reached as `std.metadata`,
  because the package binds `metadata` to its state.
- The admonition's visual style is a plain left rule. A document that
  wants another look wraps its own styling around the call or sets its
  own show rules; the markers are unaffected.
