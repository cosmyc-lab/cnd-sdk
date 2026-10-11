---
title: Figure placeholders carry every piece of context the node holds
status: implemented
date: 2026-10-11
tags: [rendering, sdk]
related: [0001, 0006, 0010]
superseded-by: null
---

# Proposal — Figure placeholders carry every piece of context the node holds

## Status
Implemented in the reference SDK's `MarkdownRenderer`. Rendering is not normative (spec §7), so there is no schema change and no `cnd_version` bump.

## Motivation
A placeholder stands for a figure whose body is not rendered as text: a data table, a figure with no convertible content. The text around it is all a reader or a text index gets of that figure. Until now the placeholder carried the kind, the number, the caption, a table's header row and a child summary, and dropped things the node holds:
- the counter label: `number="3"` says nothing about whether it is "Table 3" or "Figure 3";
- a table's row labels: the first column is what readers look a data table up by ("France", "Q3 2025"), and it was absent;
- a table's size: whether fetching the table means three rows or three hundred.

Attribute values were also written unescaped. A caption with a double quote, a line break or `]]` produced a placeholder no parser could split back into attributes.

## Proposed change
The placeholder keeps its shape, `[[figure:<id> key="value" …]]`, and gains attributes, in this order:

| Attribute | From | When |
|---|---|---|
| `kind` | the figure's kind, else its first child's type | always |
| `counter` | `counter_label` | when set |
| `number` | `number` | when set |
| `caption` | `caption` | when set |
| `header` | the header row's cells, joined with ` \| ` | a table, or a figure wrapping exactly one table |
| `rows`, `cols` | the grid's extent, spans included | same |
| `row_labels` | the first column's cells below the header rows, joined with ` \| `; after 20 labels, ` \| … (+N)` | same, with two columns or more |
| `summary` | one short description per child | a figure with children |

Body cells other than the first column stay out on purpose: a placeholder exists so a numeric grid does not flood text consumers. `get`-style access to the full table is the consumer's job, by id.

Attribute values are escaped so the placeholder is always one parseable line:
- `\` and `"` are backslash-escaped;
- any run of whitespace, line breaks included, becomes one space;
- `]]` becomes `] ]`, so the placeholder ends at its first `]]`.

## Alternatives considered
- **Render data tables inline.** Rejected: that is what the `inline` mode is for, and the reason the placeholder exists.
- **Fold the counter label into `number`** (`number="Table 3"`). Rejected: proposal 0010 keeps the two apart so a consumer composes them; a parser reading `number` would get a different value than the node holds.
- **Every column's first cell, or a sample of rows.** Rejected: row labels are what a reader searches by; sampled values are noise without their row.

## Impact
- **Consumers of `MarkdownRenderer` text:** placeholders are longer and carry new attributes. A consumer that parses them with a pattern accepting any `key="value"` pair keeps working; one that matched exact attribute sequences must be updated.
- **Producers:** nothing to do.

## Implementation checklist
- [x] `format_figure_placeholder` gains `counter_label`, `shape`, `row_labels` and escapes values
- [x] `table_shape` and `row_labels_text` in `cnd.core.node_text`; table and figure placeholders use them
- [x] Tests in `tests/test_render.py` (`TestPlaceholderContext`); golden output regenerated
- [x] Spec §7 sentence on what a placeholder carries
- [x] `docs/README.md` index row, `CHANGELOG.md` entry
