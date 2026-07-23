# CND Specification

Status: **draft v0.3** (`cnd_version: "0.3.0"`). This document is the
reference specification for the CND (Context Native Document)
format. The JSON Schema at
[`schema/cnd.schema.json`](schema/cnd.schema.json) is
generated from — and must stay in sync with — the Pydantic models in
[`src/cnd/core/`](../src/cnd/core/); that generated schema is the
machine-readable source of truth. This document is the human-readable prose
companion.

## Scope

This specification covers the **CND format**: the JSON structure a
producer emits to describe a built document as a tree of typed nodes,
plus the out-of-tree referenceable pools (bibliography, footnotes) and
the forward-only link families connecting them.

A producer need not be a paginating compiler. A CND may be built from an
unpaginated source — markdown, HTML, a hand-authored declaration — and
the format is designed so that such a producer omits what it cannot know
rather than fabricating it (docs/adr/0019).

It does **not** cover chunking, embedding, storage, or retrieval strategies —
those are consumer concerns, out of scope for the standard itself. Text
rendering is an SDK feature, not part of the format (§7).

## 1. Introduction

A CND is the interchange format between a document producer and any
downstream consumer (search index, RAG pipeline, editor, etc.). It captures:

- Document-level metadata (title, authors, date, language).
- The document body as a tree of typed nodes (headings, paragraphs, tables,
  quotes, code, math, figures, images, lists, definition lists).
- Out-of-tree referenceable entities: a bibliography pool and a footnotes
  pool.
- Forward-only link families from nodes to nodes (`refs`), to bibliography
  entries (`cites`), and to footnotes (`footnotes`), independent of the
  tree structure.

## 2. The CND

Top-level JSON structure (see `Cnd` in `src/cnd/core/cnd.py`):

| Field | Type | Description |
|---|---|---|
| `id` | UUID | CND identifier, generated if absent. |
| `cnd_version` | string | Version of the CND format the CND conforms to (`"0.3.0"` for this revision). |
| `built_at` | datetime | When the CND was built. |
| `source` | [`SourceInfo`](#21-source) \| null | The input artifact this CND was built from. |
| `doc` | [`DocMetadata`](#3-document-metadata) | Metadata of the **work**. |
| `nodes` | array of [node](#6-node-types) | Top-level document body. |
| `bibliography` | array of [`BibEntry`](#51-bibliography-pool) | Bibliography pool. Always a list, defaults to empty — never null. |
| `footnotes` | array of [`Footnote`](#52-footnotes-pool) | Footnotes pool. Always a list, defaults to empty — never null. |

**Global id uniqueness**: every `id` in a CND — node ids and pool-entry
ids alike — is unique across the whole CND. Ids are unique but **not
durable**: a producer is free to mint fresh ones on every build, and a
consumer MUST NOT treat an id as a handle that survives a rebuild
(docs/adr/0015).

**Global label uniqueness**: every `label` in a CND — on nodes and on
pool entries alike — is unique across the whole CND. This is what lets a
link name its target by label alone. A link's resolution domain is
carried by the field it appears in (`refs` → nodes, `cites` →
`bibliography`, `footnotes` → `footnotes`); global uniqueness makes the
label unambiguous, and the family makes the expected *kind* of target
unambiguous. Both are checked — existence alone is not conformance
(§5).

**Derived, not serialized.** Data a consumer can compute from what the
CND necessarily contains is never a field. That rule already governs
reverse edges (§5), reading-order positions (§8) and pagination
(§2.2); it also governs content hashes (§10). A conformant CND carries
no field that merely restates something derivable.

**Reading order (normative)**: the node tree is in document reading order —
a depth-first traversal of `nodes` (each node before its `children`,
siblings in list order) visits nodes exactly in the order they are read in
the compiled document. Producers MUST emit nodes in reading order. No
serialized field encodes position: document order, within-page order, and
within-parent order are all derived from the tree by consumers (the
reference SDK computes them during traversal, §8). Only `page` is
serialized, because page breaks are a layout result that cannot be
reconstructed from the tree.

### 2.1 Source

`source` identifies the **input artifact**, and is deliberately separate
from `doc`, which identifies the **work**. The same work can be built
from a Typst source and later re-imported from another format; the work
is unchanged and the input artifact is not the same thing.

| Field | Type | Description |
|---|---|---|
| `type` | string, required | The input format — `"typst"`, `"markdown"`, `"doclang"`… An **open string**: a new producer must not require a revision of this specification. |
| `hash` | string, required | Self-describing digest of the input, e.g. `"sha256:…"`. |
| `uri` | string \| null | An identifier in the producer's own space. |

**Comparability of `source.hash` (normative).** Two source hashes are
comparable only between CNDs from the **same producer over the same
source**. Equal means the input was unchanged; different means it
changed. Comparing across producers is meaningless — they hash different
byte streams — and a consumer MUST NOT do it. For a producer-independent
answer to "did the content change", use the derived content hash (§10).

`uri` is **never promised resolvable**. It is a producer-local
identifier, not a path a consumer may dereference; an absolute
workstation path would leak a filesystem tree to every downstream reader.

### 2.2 Pagination

`location` is nullable, and pagination is **all-or-nothing**: either
every node in a CND carries a `location`, or none does. A partially
paginated CND is invalid.

This is what removes the "unknown page" versus "not paginated"
ambiguity without adding a field. A markdown, HTML or hand-authored
source has no pages at all, and emitting `page: 1` there would fabricate
data a consumer cannot distinguish from a real page 1.

Whether a CND is paginated is therefore **derived**, not serialized: a
consumer reads it off the presence of `location`. The reference SDK
exposes it as `Cnd.paginated`. On an unpaginated CND the page-derived
traversal positions (§8) are **undefined and absent**, not zero.

## 3. Document metadata

`DocMetadata`:

| Field | Type | Description |
|---|---|---|
| `title` | string | Document title. |
| `authors` | array of string | Author names. Defaults to `[]` and may be omitted. |
| `date` | `DocDate` \| null | Partial or full document date (`year`, optional `month`, `day`). |
| `keywords` | array of string | Free-form keywords. Defaults to `[]` and may be omitted. |
| `description` | string \| null | Optional abstract/summary. |
| `lang` | string \| null | Document language code. |

## 4. Node base

Every node (see `NodeBase` in `src/cnd/core/nodes.py`) shares:

| Field | Type | Description |
|---|---|---|
| `id` | UUID | Node identifier — unique within the CND, **not durable across builds** (§2, docs/adr/0015). |
| `label` | string \| null | Human-assigned label (e.g. a Typst `<label>`). Globally unique when present (§2). The only durable identity a node has, because it lives in the source rather than being minted by the build. A node that nothing references may omit it; a node that something references must carry it, since a label is the only way to name a target. |
| `refs` | array of [`NodeRef`](#5-cross-references-and-link-families) | Outgoing cross-references to other nodes. |
| `cites` | array of [`CiteRef`](#5-cross-references-and-link-families) | Outgoing citations, resolving in the `bibliography` pool. |
| `footnotes` | array of [`FootnoteRef`](#5-cross-references-and-link-families) | Outgoing footnote markers, resolving in the `footnotes` pool. |
| `state_metadata` | object | Free-form extension bag for compiler- or consumer-specific state. Not interpreted by the standard. |
| `location` | `NodeLocation` \| null | Layout facts the consumer cannot derive from the tree. A single field: `page`, the page on which the node **begins** in the built document. Null on an unpaginated CND — see §2.2 for the all-or-nothing rule. |

All three link families live on nodes and point **outward** — there is no
serialized incoming-edge field of any kind.

## 5. Cross-references and link families

The cross-reference graph is **forward-only**: a CND serializes only
the edges from a referencing node to its target. There is no bidirectional
invariant and no `refs_from` field — the reverse index is derived by
consumers (the reference SDK provides `Cnd.incoming(label)`,
built lazily from the forward edges).

An edge names its target **by label, and carries no id**
(docs/adr/0017, superseding docs/adr/0002). All three families share the
skeleton `{label, text_span?}`:

| Field | Type | Description |
|---|---|---|
| `label` | string, required | The target's label. Resolves in `nodes` for `refs`, in `bibliography` for `cites`, in `footnotes` for `footnotes`. |
| `text_span` | `[start, end)` array of 2 ints \| null | Optional standoff position of the link's marker (e.g. a `@fig-3` marker) inside the containing node's rendered text. Offsets are **Unicode code points**, not bytes (docs/adr/0013). |

`NodeRef` is exactly this skeleton:

```json
{ "label": "eq-golden", "text_span": [29, 38] }
```

Edges key on the label rather than the id because an id is not durable
(§2): an edge carrying one would be a reference that expires at the next
build. The label lives in the source, so it survives one.

**Resolution (normative).** A conformant CND satisfies both of:

1. every edge's `label` is carried by something in the CND — an edge
   naming a label nothing carries is invalid;
2. the target sits in the **domain of the family the edge appears in** —
   a `refs` edge resolves to a node, a `cites` edge to a bibliography
   entry, a `footnotes` edge to a footnote.

The second is not implied by the first. Labels are unique across the
whole CND (§2), so a `cites` edge naming a heading resolves to
*something*; the family is what makes it wrong. A consumer may build one
global `label → target` index and check the target's kind, which is what
the reference SDK does (`Cnd.resolve`).

There is **no mirrored label field** on an edge. An earlier revision
denormalized the target's label onto the link and required
`link.label == target.label`; with the label as the key that invariant
is vacuous, and the duplication it created is gone.

`CiteRef` extends the skeleton with citation-specific fields:

| Field | Type | Description |
|---|---|---|
| `form` | `"normal"` \| `"prose"` \| `"full"` \| `"author"` \| `"year"` \| `"none"` \| null | Citation form, as in the source language. |
| `supplement` | string \| null | Supplement text (e.g. `"p. 12"`). |

A `CiteRef`'s `text_span` must be nullable: a `form: "none"` citation
renders no text, so it has no marker span.

`FootnoteRef` is exactly the shared skeleton.

Example, a paragraph referencing a figure, citing an article, and carrying
a footnote marker:

```json
{
  "type": "paragraph",
  "text": "Selon Smith et al., voir le listing 1.",
  "refs": [
    { "label": "lst-api", "text_span": [29, 38] }
  ],
  "cites": [
    { "label": "smith2024", "text_span": [6, 18], "form": "prose", "supplement": "p. 12" }
  ],
  "footnotes": [
    { "label": "fn-rest", "text_span": null }
  ]
}
```

### 5.1 Bibliography pool

`bibliography` is a top-level list of `BibEntry` objects — the targets of
`cites` edges. Entries live outside the node tree: a bibliography entry is
not a node, has no `location`, and never appears in `nodes`.

| Field | Type | Description |
|---|---|---|
| `id` | UUID, required | Entry identifier (unique document-wide). |
| `label` | string, required | The citation key (e.g. the Typst/Hayagriva `@key`). |
| `formatted` | string \| null | The reference string as displayed in the built document — the faithful capture. Nullable: requiring it would presuppose that a citation style engine ran, which a hand author or a markdown producer has no reason to have. |
| `type` | string \| null | Entry type (e.g. `"article"`). |
| `authors` | array of string | Author names. |
| `title` | string \| null | Work title. |
| `year` | int \| null | Publication year. |
| `container` | string \| null | Containing work (journal, book, proceedings…). |
| `doi` | string \| null | DOI. |
| `url` | string \| null | URL. |
| `fields` | object | Lossless passthrough of the full source entry (e.g. the Hayagriva entry) as structured JSON — carries every field the curated subset above doesn't type. Named `fields` rather than `raw` because `raw` means something else on nodes (§6.3). |

**Content floor (normative).** An entry MUST carry `formatted`, at least
one structured field, or both. An entry with neither is one a citation
can reach but nothing can display.

### 5.2 Footnotes pool

`footnotes` (top-level) is a list of `Footnote` objects — the targets of
per-node `footnotes` edges. Footnote content is flat text in this revision;
block/subtree content inside footnotes is not modeled.

| Field | Type | Description |
|---|---|---|
| `id` | UUID, required | Entry identifier (unique document-wide). |
| `label` | string, required | Footnote label/marker key. |
| `text` | string, required | The footnote's text. |

## 6. Node types

All node types inherit the [node base](#4-node-base) fields plus `type`
(a discriminator literal) and their own fields below. See
`src/cnd/core/nodes.py` for the authoritative definitions.

Two fields recur across node types and are defined once here.

**`number`** — carried by `heading`, `math` and `figure`, always
nullable. It is the counter value **as resolved and displayed**:
`"2.1.1"`, `"(1)"`, `"3"`. Never the pattern that produced it, because a
consumer cannot replay a counter engine and so could do nothing with
one. Never the counter-label word either: `"Figure 3"` fuses a locale
into the value, and composing that prefix is a rendering decision. A
document with unnumbered headings leaves it null.

**`counter_label`** — the companion of `number` on the same three node
types, also nullable. It is the word displayed in front of the number
(`"Figure"`, `"Tabelle"`, `"Listing"`), **as resolved in the document's
language**. Kept in its own field rather than fused into `number`: a
consumer wanting locale-free structure reads `kind`, one reproducing the
document composes `counter_label` + `number`.

It is a field rather than something derived because it is not always
derivable. A producer resolves it from the element kind and the document
language, using a localization table no consumer has; and for an
author-defined `kind` there is no such table at all, so the author
supplies the word and nothing else in the CND encodes it
(docs/proposals/0010).

```json
{ "type": "figure", "kind": "atom", "number": "1",
  "counter_label": "Atom", "caption": "A curious atom." }
```

**`raw`** — carried by `table`, `math` and `figure`, always nullable.
The producer's verbatim source for the node, as an object:

```json
{ "format": "typst", "value": "$ e(t) = m(t) - r(t) $" }
```

`format` is an **open string** (`"typst"`, `"latex"`, `"mathml"`…). It
exists because a bare string dropped the one thing a consumer needs in
order to decide whether to attempt a parse: which language the content
is in. `raw` remains the escape hatch for an unconvertible figure body
(`children: []` with `raw` filled).

### 6.1 `heading`

| Field | Type |
|---|---|
| `level` | int |
| `number` | string \| null |
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
| `raw` | `RawSource` \| null |

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
| `raw` | `RawSource` \| null |
| `number` | string \| null |
| `block` | bool |

### 6.7 `figure`

A **wrapper** node: the captioned/numbered float, never a content carrier.
The wrapped content lives in `children` and keeps its own node type.

| Field | Type |
|---|---|
| `kind` | string \| null |
| `caption` | string \| null |
| `number` | string \| null |
| `children` | array of node |
| `raw` | `RawSource` \| null |

`kind` is the figure's counter/label selector — `"image"`, `"table"`, or an
author-custom kind such as `"atom"`. It is an **open string** and is never
a content discriminator: what the figure contains is determined by the node
types in `children`, not by `kind`.

Producer mapping (informative — the producer itself is out of scope, see
docs/adr/0006): `#figure(image)` → `figure` wrapping an `image` node;
`#figure(table)` → `figure` wrapping a `table` node; `#figure(raw)` →
`figure` wrapping a `code` node; a multi-body figure (e.g.
`#figure(grid(img, img))`) → `figure` with several children; an
unconvertible body → `children: []` with `raw` filled.

Nested figures (a `figure` inside another `figure`'s `children`) are
allowed and intended — that is how subfigures are represented.

Children carry their own `location`; nothing is inherited from the
wrapper. On an unpaginated CND neither carries one (§2.2).

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

## 8. Traversal

Traversal is **not shared as code across languages** (docs/adr/0019): a
walk carries state, and state does not cross a language boundary without
becoming monstrous. Every implementation writes its own. That makes the
semantics normative prose rather than an implementation detail — two
implementations that disagree here disagree invisibly, since nothing in
the file records the order they chose.

**Walk order (normative).** Depth-first over `nodes`: each node is
yielded before its `children`, and siblings in list order. Because the
tree is in reading order (§2), the walk order *is* reading order. A
consumer may prune a subtree; pruning does not change the positions of
the nodes still visited, which are document facts rather than walk
artifacts.

**The pools do not enter the walk (normative).** A traversal yields
nodes only. Bibliography entries and footnotes are reached by resolving a
link (§5), never by iterating. They sit outside the tree because they are
referenced from many points rather than read at one, so they have no
position in reading order to occupy — and appending them at the end
would be encoding a *rendering* convention (footnotes at the foot,
bibliography last) into the traversal contract. A consumer that wants
them iterates the pools directly.

**Link families are not ordered against each other (normative).** Within
a node, each family's list preserves the order the producer emitted, and
the families themselves are enumerated `refs`, `cites`, `footnotes`.
That enumeration is a stable convention for reproducible output; it
carries **no** claim about where the markers sit in the text. The only
positional truth about a marker is its `text_span`, and a consumer that
needs markers in text order sorts by it across all three families.

**Derived positions.** Every yielded node is paired with a context
carrying 1-based `index`/`count` pairs: `doc_index`/`doc_count`
(position in the whole document), `sibling_index`/`sibling_count`
(position among the parent's children), and `page_index`/`page_count`
(position among the nodes beginning on the same `location.page`). The
page pair is **absent** on an unpaginated CND (§2.2) — undefined, not
zero.

**Conformance.** The fixture corpus carries `CND → expected id sequence`
vectors (`fixtures/traversal.json`). An implementation proves its walk
order by reproducing them; `cnd inspect` shows the order a CND actually
walks in.

The reference SDK implements this as `Cnd.iter()` / `iter_nodes()`, with
`BaseVisitor` dispatching a `visit_<type>` hook per node type and
`should_stop_descent()` to prune. `Cnd.incoming(label)` is the derived
reverse index (§5) and `Cnd.resolve(label)` the label index (§5), both
built lazily and cached. `NodeDisplayVisitor` (requires the `display`
extra) renders a colorized trace for terminal inspection.

## 9. Validation

Some invariants cannot be stated in JSON Schema — they are relational or
document-wide, and a schema validates one value at a time. A CND is
conformant only if it satisfies all of:

| Invariant | Where |
|---|---|
| Global id uniqueness | §2 |
| Global label uniqueness | §2 |
| Every edge resolves, in its family's domain | §5 |
| Pagination is all-or-nothing | §2.2 |
| Every bibliography entry meets the content floor | §5.1 |

These are enforced in one of two places depending on how the CND was
produced (docs/adr/0019). A producer going through a declaration cannot
bypass the builder that checks them. A producer emitting a CND directly
from its own compiler calls a validator itself — the reference SDK
exposes `validate(cnd)`, which returns every violation rather than the
first, and the same check as `cnd validate` on the command line.

The asymmetry is real and worth naming rather than papering over: a
build cannot be skipped, a validation call can be forgotten. It is the
same line this format draws for hashes — verifiable, not promised.

## 10. Content hashing

A **derived content hash** answers "did this change?" for any consumer,
independent of producer. It is computed from the CND and is **never
serialized** — it is derivable, and derivable data is not a field (§2).

Do not confuse it with `source.hash` (§2.1), which is a producer-supplied
digest of the *input artifact* and is only comparable within one
producer.

**Algorithm (normative).**

1. Take the hashable subset of the value (below).
2. Normalize every string — keys as well as values — to Unicode **NFC**.
3. Serialize with [RFC 8785 JSON Canonicalization Scheme
   (JCS)](https://www.rfc-editor.org/rfc/rfc8785).
4. Hash the resulting bytes with SHA-256; render as `"sha256:<hex>"`.

Both canonicalisations are external references rather than a bespoke
scheme, so an implementation in any language can reproduce the bytes.
JCS is load-bearing beyond key ordering: its ECMAScript number
serialization is where a hand-rolled implementation silently diverges.

**Node hash.** Over a node's own fields, **excluding** `id`, `location`,
`number`, `counter_label` and `children`. The first four are resolved
presentation state
— computed for display, and changing without the authored content
changing. `children` is excluded for a different reason: a heading whose
subsection changed has not itself changed, and treating it as changed
would defeat the very matching pass that recognises a moved-but-unchanged
node (docs/adr/0018).

The excluded `number` is the case that would break silently: inserting a
heading renumbers every node after it, so a hash covering `number` would
report each of them as changed.

**Document hash.** Over the `doc` metadata, every node hash paired with
its depth in reading order, and both pools. Excluded: `built_at`,
`source` and `cnd_version` — the same content built twice, reached from
two input formats, or expressed under two format versions is the same
content.

Depth is paired with each node hash because nesting is structure, not
presentation: re-parenting a section leaves reading order and every
node-local hash untouched. The pools are included because a footnote's
text is authored content; they sit out of the tree for referencing
reasons, not because they are metadata.

**The exclusion list is a principle plus a list**, maintained as the
field set evolves rather than frozen: *exclude resolved presentation
state, hash everything else.*

**Conformance.** The fixture corpus carries `CND → expected hash`
vectors (`fixtures/hashes.json`), and `cnd hash` recomputes them, so an
implementation in another language can diff against the oracle rather
than eyeball it.

A hash is change-detection, not identity: two identical paragraphs in one
document share a hash, and this specification makes no identity claim for
that. Pairing nodes across builds is reconciliation's problem
(docs/adr/0018), not the hash's.

## 11. Versioning

CNDs declare the format version they conform to via `cnd_version`;
this revision of the specification is `"0.3.0"`. Every change to the node
schema is a PR against this repository (`cnd-sdk`), tagged as a new
release; consumers pin to a tag.

A CND is an **immutable build artifact** (docs/adr/0015). It is not
edited in place and carries no version history of its own: versioning a
document is a consumer concern, and relating two builds of the same
document is reconciliation's (docs/adr/0018).

## Out of scope

Chunking strategies, embedding generation, vector storage backends,
and any indexing pipeline built on top of CNDs are consumer
concerns and are **not** part of this standard.
