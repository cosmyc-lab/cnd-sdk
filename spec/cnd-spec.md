# CND Specification

Status: **draft v0.1**. This document is the reference specification for the
CND (Context Native Document) manifest format. The JSON Schema at
[`schema/cnd-manifest.schema.json`](schema/cnd-manifest.schema.json) is
generated from — and must stay in sync with — the Pydantic models in
[`src/cnd/core/`](../src/cnd/core/); that generated schema is the
machine-readable source of truth. This document is the human-readable prose
companion.

## Scope

This specification covers the **manifest format**: the JSON structure a
compiler (such as `typst-cnd`) emits to describe a compiled document as a
tree of typed, cross-referenceable nodes, and the base operations (text
rendering, traversal, display) that any conformant consumer can rely on.

It does **not** cover chunking, embedding, storage, or retrieval strategies —
those are consumer concerns, out of scope for the standard itself.

## 1. Introduction

A CND manifest is the interchange format between a document compiler and any
downstream consumer (search index, RAG pipeline, editor, etc.). It captures:

- Document-level metadata (title, authors, date, language).
- The document body as a tree of typed nodes (headings, paragraphs, tables,
  quotes, code, math, figures, lists).
- A cross-reference graph between nodes, independent of the tree structure.

## 2. The CND Manifest

Top-level JSON structure (see `CndManifest` in `src/cnd/core/manifest.py`):

| Field | Type | Description |
|---|---|---|
| `id` | UUID | Manifest identifier, generated if absent. |
| `cnd_version` | string | Version of the CND format the manifest conforms to. |
| `doc_hash` | string | Content hash of the source document. |
| `compiled_at` | datetime | Compilation timestamp. |
| `doc` | [`DocMetadata`](#3-document-metadata) | Bibliographic metadata. |
| `nodes` | array of [node](#5-node-types) | Top-level document body. |

## 3. Document metadata

`DocMetadata`:

| Field | Type | Description |
|---|---|---|
| `title` | string | Document title. |
| `authors` | array of string | Author names. |
| `date` | `DocDate` \| null | Partial or full document date (`year`, optional `month`, `day`). |
| `keywords` | array of string | Free-form keywords. |
| `description` | string \| null | Optional abstract/summary. |
| `lang` | string \| null | Document language code. |

## 4. Node base

Every node (see `NodeBase` in `src/cnd/core/nodes.py`) shares:

| Field | Type | Description |
|---|---|---|
| `id` | UUID | Stable node identifier. |
| `label` | string \| null | Human-assigned label (e.g. a Typst `<label>`). |
| `refs_to` | array of [`NodeRef`](#5-cross-reference-graph) | Outgoing cross-references. |
| `refs_from` | array of [`NodeRef`](#5-cross-reference-graph) | Incoming cross-references. |
| `state_metadata` | object | Free-form extension bag for compiler- or consumer-specific state. Not interpreted by the standard. |
| `location` | `NodeLocation` | Physical position in the compiled document (`page`, `span`, `page_span`, `parent_span`, `span_count`). |

## 5. Cross-reference graph

Nodes link to each other through **`NodeRef`** objects — the canonical form
is the only form accepted by this standard:

```json
{ "id": "0184480d-3d42-479d-8472-65a5fee07208", "label": "eq-golden" }
```

| Field | Type | Description |
|---|---|---|
| `id` | UUID, required | Target (for `refs_to`) or source (for `refs_from`) node identifier. |
| `label` | string \| null | Human-readable label, when known. |

Example, a paragraph referencing an equation and a table:

```json
{
  "type": "paragraph",
  "text": "See @eq-golden and @tab-signals.",
  "refs_to": [
    { "id": "0184480d-3d42-479d-8472-65a5fee07208", "label": "eq-golden" },
    { "id": "1ccb26eb-f6d8-49b2-92eb-3a4bf554091c", "label": "tab-signals" }
  ]
}
```

Bidirectional consistency: if node A has `{ "id": B, "label": "tab-x" }` in
`refs_to`, node B must list `{ "id": A, "label": … }` in `refs_from` (label
may be `null` when A has no label).

Bare UUID strings or `[label, id]` tuples are **not** valid CND — a
conformant producer must always emit the canonical `{id, label}` object.

## 6. Node types

All node types inherit the [node base](#4-node-base) fields plus `type`
(a discriminator literal) and their own fields below. See
`src/cnd/core/nodes.py` for the authoritative definitions.

### 6.1 `heading`

| Field | Type |
|---|---|
| `level` | int |
| `numbering` | string |
| `text` | string |
| `heading_path` | array of string |
| `children` | array of node |

### 6.2 `paragraph`

| Field | Type |
|---|---|
| `text` | string |
| `lang` | string \| null |

### 6.3 `table`

| Field | Type |
|---|---|
| `kind` | `"table"` \| `"grid"` |
| `content_kind` | `"data"` \| `"content"` \| null |
| `caption` | string \| null |
| `fig_number` | string \| null |
| `cells` | array of `TableCell` (`row`, `col`, `rowspan`, `colspan`, `is_header`, `text`) |
| `raw_typst` | string \| null |

`kind: "grid"` distinguishes a layout grid from a semantic table; both share
the same cell model.

`content_kind` is an optional producer-supplied hint consumed by
`mode="auto"` rendering (§7): `"content"` for a table whose cells read fine
inlined as text (a short comparison table, a parameter list), `"data"` for
one that doesn't (a numeric measurement grid). Unset — the common case
today, since nothing currently sets it — is treated as `"data"`.

### 6.4 `quote`

| Field | Type |
|---|---|
| `text` | string |
| `attribution` | string \| null |
| `block` | bool |
| `lang` | string \| null |

### 6.5 `code`

| Field | Type |
|---|---|
| `text` | string |
| `lang` | string \| null |
| `block` | bool |

### 6.6 `math`

| Field | Type |
|---|---|
| `text` | string |
| `raw_typst` | string \| null |
| `numbering` | string \| null |
| `block` | bool |

### 6.7 `figure`

| Field | Type |
|---|---|
| `caption` | string \| null |
| `fig_number` | string \| null |
| `kind` | string \| null |
| `alt` | string \| null |
| `path` | string \| null |
| `raw_typst` | string \| null |

### 6.8 `list`

| Field | Type |
|---|---|
| `ordered` | bool |
| `tight` | bool |
| `items` | array of `ListItem` (`text`, `number`, nested `children`) |

## 7. Text rendering (`to_text()`)

Every node type exposes a zero-argument `to_text()` method producing a
plain-text representation suitable for embedding or display:

- `heading`, `paragraph`, `math` — return their `text` verbatim.
- `quote` — text, plus `\n— attribution` when present.
- `code` — fenced with the language tag (` ```lang `).
- `list` — rendered as a Markdown bullet or numbered list, recursively.
- `table`, `figure` — rendered as a parseable placeholder:
  `[[figure:<id> kind="..." number="..." caption="..." header="..."]]`,
  since tabular/visual content cannot always be flattened to plain text.
  `header`, present when the table has at least one non-empty cell in its
  header row (cells flagged `is_header`, or row 0 when none are), is the
  header row's cell text joined with `" | "` — placeholder mode preserves
  some of the table's structure even though it doesn't inline the cells.

`to_text()` itself never takes a mode argument and its output for every
node type is unchanged from the above — a table/figure node's placeholder
is always what a caller gets by calling `to_text()` directly.

### 7.1 Mode-aware rendering (`node_text.render_node_text`)

`table` nodes additionally support rendering their cells inline as a
Markdown grid instead of a placeholder, via
`cnd.core.node_text.render_node_text(node, mode=...)` (or
`table_node_text(node, mode=...)` for a `TableNode` directly) —
`to_text()` is unaffected; this is a separate, opt-in entry point. `mode`
is one of:

- `"placeholder"` (default) — always the placeholder, matching `to_text()`.
- `"inline"` — always a Markdown grid of the table's `cells`, honoring
  `rowspan`/`colspan` (a spanned cell's text is placed once, at its own
  `(row, col)`; the rest of the span is left blank — Markdown has no
  native merged-cell syntax) and using the header row (`is_header` cells,
  or row 0) for the separator row. Falls back to the placeholder if the
  table has no cells.
- `"auto"` — defers to the table's own `content_kind` (§6.3): inline when
  it's `"content"`, placeholder when it's `"data"` or unset. There is no
  content-based classifier — an unset hint is never guessed at, only
  taken as `"data"`.

Every other node type ignores `mode` and returns its own `to_text()`
unchanged; a future node type can opt into mode-aware rendering the same
way without `to_text()`'s own contract changing.

## 8. Traversal and visitors

- `CndManifest.iter()` / `iter_nodes()` walk the node tree depth-first,
  yielding each node paired with a `NodeTraverseContext` (`depth`,
  `heading_path`, `parent`).
- `BaseVisitor` dispatches to a `visit_<type>` hook per node type, with
  `should_stop_descent()` to prune branches.
- `NodeDisplayVisitor` (requires the `display` extra) renders a colorized
  trace of the tree for terminal inspection.

## 9. Versioning

Manifests declare the format version they conform to via `cnd_version`.
Every change to the node schema is a PR against this repository (`cnd-sdk`),
tagged as a new release; consumers pin to a tag.

## Out of scope

Chunking strategies, embedding generation, vector storage backends,
and any indexing pipeline built on top of CND manifests are consumer
concerns and are **not** part of this standard.
