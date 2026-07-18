# CND Specification

Status: **draft v0.2** (`cnd_version: "0.2.0"`). This document is the
reference specification for the CND (Context Native Document) manifest
format. The JSON Schema at
[`schema/cnd-manifest.schema.json`](schema/cnd-manifest.schema.json) is
generated from — and must stay in sync with — the Pydantic models in
[`src/cnd/core/`](../src/cnd/core/); that generated schema is the
machine-readable source of truth. This document is the human-readable prose
companion.

## Scope

This specification covers the **manifest format**: the JSON structure a
compiler (such as `typst-cnd`) emits to describe a compiled document as a
tree of typed nodes, plus the out-of-tree referenceable pools
(bibliography, footnotes) and the forward-only link families connecting
them.

It does **not** cover chunking, embedding, storage, or retrieval strategies —
those are consumer concerns, out of scope for the standard itself. Text
rendering is an SDK feature, not part of the format (§7).

## 1. Introduction

A CND manifest is the interchange format between a document compiler and any
downstream consumer (search index, RAG pipeline, editor, etc.). It captures:

- Document-level metadata (title, authors, date, language).
- The document body as a tree of typed nodes (headings, paragraphs, tables,
  quotes, code, math, figures, images, lists, definition lists).
- Out-of-tree referenceable entities: a bibliography pool and a footnotes
  pool.
- Forward-only link families from nodes to nodes (`refs`), to bibliography
  entries (`cites`), and to footnotes (`footnotes`), independent of the
  tree structure.

## 2. The CND Manifest

Top-level JSON structure (see `CndManifest` in `src/cnd/core/manifest.py`):

| Field | Type | Description |
|---|---|---|
| `id` | UUID | Manifest identifier, generated if absent. |
| `cnd_version` | string | Version of the CND format the manifest conforms to (`"0.2.0"` for this revision). |
| `doc_hash` | string | Content hash of the source document. |
| `compiled_at` | datetime | Compilation timestamp. |
| `doc` | [`DocMetadata`](#3-document-metadata) | Bibliographic metadata. |
| `nodes` | array of [node](#6-node-types) | Top-level document body. |
| `bibliography` | array of [`BibEntry`](#51-bibliography-pool) | Bibliography pool. Always a list, defaults to empty — never null. |
| `footnotes` | array of [`Footnote`](#52-footnotes-pool) | Footnotes pool. Always a list, defaults to empty — never null. |

**Global id uniqueness**: every `id` in a manifest — node ids and pool-entry
ids alike — is unique across the whole manifest. A link's resolution domain
is carried by the field it appears in (`refs` → nodes, `cites` →
`bibliography`, `footnotes` → `footnotes`), never by the shape of the id.

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
| `refs` | array of [`NodeRef`](#5-cross-references-and-link-families) | Outgoing cross-references to other nodes. |
| `cites` | array of [`CiteRef`](#5-cross-references-and-link-families) | Outgoing citations, resolving in the `bibliography` pool. |
| `footnotes` | array of [`FootnoteRef`](#5-cross-references-and-link-families) | Outgoing footnote markers, resolving in the `footnotes` pool. |
| `state_metadata` | object | Free-form extension bag for compiler- or consumer-specific state. Not interpreted by the standard. |
| `location` | `NodeLocation` | Physical position in the compiled document (`page`, `span`, `page_span`, `parent_span`, `span_count`). |

All three link families live on nodes and point **outward** — there is no
serialized incoming-edge field of any kind.

## 5. Cross-references and link families

The cross-reference graph is **forward-only**: a manifest serializes only
the edges from a referencing node to its target. There is no bidirectional
invariant and no `refs_from` field — the reverse index is derived by
consumers (the reference SDK provides `CndManifest.incoming(node_id)`,
built lazily from the forward edges).

All three link families share the same skeleton `{id, label, span?}`:

| Field | Type | Description |
|---|---|---|
| `id` | UUID, required | Target identifier. Resolves in `nodes` for `refs`, in `bibliography` for `cites`, in `footnotes` for `footnotes`. The field name is always `id`. |
| `label` | string \| null | Mirror of the target's `label`, denormalized so a consumer can display the link without resolving it. Invariant: `link.label == target.label`. |
| `span` | `[start, end)` array of 2 ints \| null | Optional standoff position of the link's marker (e.g. a `@fig-3` marker) inside the containing node's rendered text. Offsets are **Unicode code points**, not bytes. |

`NodeRef` is exactly this skeleton. The canonical form is the only form
accepted by this standard:

```json
{ "id": "0184480d-3d42-479d-8472-65a5fee07208", "label": "eq-golden" }
```

Bare UUID strings or `[label, id]` tuples are **not** valid CND — a
conformant producer must always emit the canonical object form
(docs/adr/0002). `span` is an additive optional field on that canonical
shape.

`CiteRef` extends the skeleton with citation-specific fields:

| Field | Type | Description |
|---|---|---|
| `form` | `"normal"` \| `"prose"` \| `"full"` \| `"author"` \| `"year"` \| `"none"` \| null | Citation form, as in the source language. |
| `supplement` | string \| null | Supplement text (e.g. `"p. 12"`). |

A `CiteRef`'s `span` must be nullable: a `form: "none"` citation renders no
text, so it has no marker span.

`FootnoteRef` is exactly the shared skeleton.

Example, a paragraph referencing a figure, citing an article, and carrying
a footnote marker:

```json
{
  "type": "paragraph",
  "text": "Selon Smith et al., voir le listing 1.",
  "refs": [
    { "id": "…-d004", "label": "lst-api", "span": [29, 38] }
  ],
  "cites": [
    { "id": "…-d100", "label": "smith2024", "span": [6, 18], "form": "prose", "supplement": "p. 12" }
  ],
  "footnotes": [
    { "id": "…-d200", "label": "fn-rest", "span": null }
  ]
}
```

### 5.1 Bibliography pool

`bibliography` is a top-level list of `BibEntry` objects — the targets of
`cites` edges. Entries live outside the node tree: a bibliography entry is
not a node, has no `location`, and never appears in `nodes`.

| Field | Type | Description |
|---|---|---|
| `id` | UUID, required | Entry identifier (unique manifest-wide). |
| `label` | string, required | The citation key (e.g. the Typst/Hayagriva `@key`). |
| `rendered` | string, required | The reference string as displayed in the compiled document — the faithful capture. |
| `type` | string \| null | Entry type (e.g. `"article"`). |
| `authors` | array of string | Author names. |
| `title` | string \| null | Work title. |
| `year` | int \| null | Publication year. |
| `container` | string \| null | Containing work (journal, book, proceedings…). |
| `doi` | string \| null | DOI. |
| `url` | string \| null | URL. |
| `raw` | object | Lossless passthrough of the full source entry (e.g. the Hayagriva entry) as structured JSON — carries every field the curated subset above doesn't type. |

### 5.2 Footnotes pool

`footnotes` (top-level) is a list of `Footnote` objects — the targets of
per-node `footnotes` edges. Footnote content is flat text in this revision;
block/subtree content inside footnotes is not modeled.

| Field | Type | Description |
|---|---|---|
| `id` | UUID, required | Entry identifier (unique manifest-wide). |
| `label` | string, required | Footnote label/marker key. |
| `text` | string, required | The footnote's text. |

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
| `cells` | array of `TableCell` (`row`, `col`, `rowspan`, `colspan`, `is_header`, `text`) |
| `raw_typst` | string \| null |

`kind: "grid"` distinguishes a layout grid from a semantic table; both share
the same cell model.

A table has **no caption or figure number of its own** — a captioned or
numbered table is a `table` node wrapped in a [`figure`](#67-figure) node,
which carries the caption. A bare table (not in a figure) is simply a
`table` node with no wrapper.

`content_kind` is an optional producer-supplied hint consumed by
`mode="auto"` rendering (§7): `"content"` for a table whose cells read fine
inlined as text (a short comparison table, a parameter list), `"data"` for
one that doesn't (a numeric measurement grid). Unset is treated as
`"data"` — never guessed at by a classifier.

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

A **wrapper** node: the captioned/numbered float, never a content carrier.
The wrapped content lives in `children` and keeps its own node type.

| Field | Type |
|---|---|
| `kind` | string \| null |
| `caption` | string \| null |
| `fig_number` | string \| null |
| `children` | array of node |
| `raw_typst` | string \| null |

`kind` is the figure's counter/label selector — `"image"`, `"table"`, or an
author-custom kind such as `"atom"`. It is an **open string** and is never
a content discriminator: what the figure contains is determined by the node
types in `children`, not by `kind`.

Producer mapping (informative — the producer itself is out of scope, see
docs/adr/0006): `#figure(image)` → `figure` wrapping an `image` node;
`#figure(table)` → `figure` wrapping a `table` node; `#figure(raw)` →
`figure` wrapping a `code` node; a multi-body figure (e.g.
`#figure(grid(img, img))`) → `figure` with several children; an
unconvertible body → `children: []` with `raw_typst` filled.

Nested figures (a `figure` inside another `figure`'s `children`) are
allowed and intended — that is how subfigures are represented.

Children carry their own `location`; nothing is inherited from the wrapper.

### 6.8 `image`

Leaf image content. A bare image (no caption) is an `image` node with no
wrapper; a captioned image is an `image` node inside a `figure`.

| Field | Type |
|---|---|
| `path` | string \| null |
| `alt` | string \| null |

### 6.9 `list`

| Field | Type |
|---|---|
| `ordered` | bool |
| `tight` | bool |
| `items` | array of `ListItem` (`text`, `number`, nested `children`) |

### 6.10 `terms`

A definition list (Typst `/ term: description` items). Items are flat text
pairs — like `ListItem` and `TableCell` they carry no `id` and are not
ref-targetable.

| Field | Type |
|---|---|
| `tight` | bool |
| `items` | array of `TermItem` (`term`, `description`) |

## 7. Rendering (SDK, non-normative)

The CND **format** does not mandate any rendering method: nodes are pure
data, and no node has a `to_text()` contract. How a node becomes text is a
consumer decision.

The reference SDK provides a renderer hierarchy in `cnd.core.render`
(zero-dependency, informative):

- `NodeRenderer` — an abstract base with one rendering method per node type
  and a single concrete `render(node)` dispatch over the node union.
- `MarkdownRenderer` — the concrete content renderer, producing
  CommonMark-ish text. Verbosity for tables and figures is constructor
  configuration (`tables=` / `figures=`, each one of `"placeholder"`,
  `"inline"`, `"auto"`), orthogonal to the output format: `"placeholder"`
  emits a parseable `[[figure:<id> …]]` placeholder, `"inline"` renders the
  cells/children as text, and `"auto"` defers to the table's
  `content_kind` hint (§6.3).

The exact Markdown produced is **not normative** — no consumer may rely on
its precise shape as part of the format. The "raw" representation of a node
is its JSON serialization itself (`model_dump_json()`), not a renderer.

## 8. Traversal and visitors

- `CndManifest.iter()` / `iter_nodes()` walk the node tree depth-first,
  yielding each node paired with a `NodeTraverseContext` (`depth`,
  `heading_path`, `parent`). Traversal descends into every children-bearing
  node — `heading` and `figure` alike; a consumer that wants to treat
  figures as atomic prunes them with a `stop_predicate`.
- `CndManifest.incoming(id)` returns the nodes whose forward edges
  (`refs`, `cites`, `footnotes`) target `id` — the derived reverse index
  (§5), built lazily and cached.
- `BaseVisitor` dispatches to a `visit_<type>` hook per node type, with
  `should_stop_descent()` to prune branches.
- `NodeDisplayVisitor` (requires the `display` extra) renders a colorized
  trace of the tree for terminal inspection, using a `NodeRenderer` for
  text previews.

## 9. Versioning

Manifests declare the format version they conform to via `cnd_version`;
this revision of the specification is `"0.2.0"`. Every change to the node
schema is a PR against this repository (`cnd-sdk`), tagged as a new
release; consumers pin to a tag.

## Out of scope

Chunking strategies, embedding generation, vector storage backends,
and any indexing pipeline built on top of CND manifests are consumer
concerns and are **not** part of this standard.
