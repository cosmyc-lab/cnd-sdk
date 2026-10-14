# CND Specification

Status: **draft v0.5** (`cnd_version: "0.5.0"`). This document is the
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

- Document-level metadata (title, authors, date, language, the status and
  version the author declares).
- The document body as a tree of typed nodes (headings, paragraphs, quotes,
  code, math, figures, images, admonitions, lists, definition lists,
  tables, layout grids). Containers hold their nested nodes in `children`,
  including inside list items, term items and cells.
- Prose as rich text (§4.1): a string with standoff inline marks (bold,
  superscript, inline code, inline math…) and its own link families.
- Out-of-tree referenceable entities: a bibliography pool and a footnotes
  pool, whose footnotes hold block nodes.
- Forward-only link families carried by each text, to nodes (`refs`), to
  bibliography entries (`cites`), to footnotes (`footnotes`), and to
  hyperlinks outside the CND (`links`), independent of the tree structure.

## 2. The CND

Top-level JSON structure (see `Cnd` in `src/cnd/core/cnd.py`):

| Field | Type | Description |
|---|---|---|
| `id` | UUID | CND identifier, generated if absent. |
| `cnd_version` | string | Version of the CND format the CND conforms to (`"0.5.0"` for this revision). |
| `built_at` | datetime | When the CND was built. |
| `source` | [`SourceInfo`](#21-source) \| null | The input artifact this CND was built from. |
| `doc` | [`DocMetadata`](#3-document-metadata) | Metadata of the **work**. |
| `nodes` | array of [node](#6-node-types) | Top-level document body. |
| `bibliography` | array of [`BibEntry`](#51-bibliography-pool) | Bibliography pool. Always a list, defaults to empty — never null. |
| `footnotes` | array of [`Footnote`](#52-footnotes-pool) | Footnotes pool. Each entry holds block nodes in its `children`. Always a list, defaults to empty — never null. |

**Global id uniqueness**: every `id` in a CND is unique across the whole
CND — the ids of body nodes, of footnote content nodes (§5.2), and of the
entries of both pools alike. Ids are unique but **not durable**: a
producer is free to mint fresh ones on every build, and a consumer MUST
NOT treat an id as a handle that survives a rebuild (docs/adr/0015).

**Global label uniqueness**: every `label` in a CND — on body nodes, on
footnote content nodes, and on pool entries alike — is unique across the
whole CND. This is what lets a link name its target by label alone. A
link's resolution domain is carried by the field it appears in (`refs` →
nodes, `cites` → `bibliography`, `footnotes` → `footnotes`); global
uniqueness makes the label unambiguous, and the family makes the
expected *kind* of target unambiguous. Both are checked — existence
alone is not conformance (§5).

**Derived, not serialized.** Data a consumer can compute from what the
CND necessarily contains is never a field. That rule already governs
reverse edges (§5), reading-order positions (§8) and pagination
(§2.2); it also governs content hashes (§10). A conformant CND carries
no field that merely restates something derivable.

**Reading order (normative)**: the node tree is in document reading order —
a depth-first traversal of `nodes` (each node before its nested nodes,
siblings in list order, and the entries of a node's `items` or `cells`
in list order, §8) visits nodes exactly in the order they are read in
the compiled document. Producers MUST emit nodes in reading order, and
MUST emit the `cells` of a table or a layout in reading order too: the
walk, the node path (§8) and the document hash (§10) follow list order,
not the `row` and `col` coordinates. No serialized field encodes
position: document order, within-page order, and within-parent order are
all derived from the tree by consumers (the reference SDK computes them
during traversal, §8). Only `page` is serialized, because page breaks are
a layout result that cannot be reconstructed from the tree.

**Decorative content (normative)**: content the source marks as
decorative — present for presentation only, carrying no meaning — is not
part of the document. A producer MUST NOT emit it: it yields no node, no
text inside another text, no pool entry, and no link edge.
Everything nested inside decorative content is decorative, whatever its
kind. A label inside it does not exist in the CND, so a reference to it
from kept content yields no edge (the text the reference displays, if
any, stays in the `value` of the kept text). A footnote declared inside it gets no pool
entry, and no marker — its own or a re-reference — yields an edge to it;
a kept footnote keeps the label the built document shows, even when a
decorative one consumed a number before it. A marker written inside
decorative content — a reference, a citation, a footnote re-reference —
yields no edge, whatever it points at. The bibliography pool is the
built document's bibliography: an entry the document lists stays, even
if only decorative content cites it. Only an explicit marker counts; a
producer never infers decoration. What the marker is depends on the
source format — Typst `pdf.artifact`, tagged-PDF artifacts, HTML
`aria-hidden="true"` (docs/proposals/0011).

### 2.1 Source

`source` identifies the **input artifact**, and is deliberately separate
from `doc`, which identifies the **work**. The same work can be built
from a Typst source and later re-imported from another format; the work
is unchanged and the input artifact is not the same thing.

| Field | Type | Description |
|---|---|---|
| `type` | string, required | The input format — `"typst"`, `"markdown"`, `"doclang"`… An **open vocabulary** (§6.0): a new producer must not require a revision of this specification. |
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
every node in a CND carries a `location`, or none does. "Every node"
includes footnote content nodes (§5.2): on a paginated CND they carry the
page where the note is printed. A partially paginated CND is invalid.

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
| `lang` | string \| null | Document language code. The end of the inheritance chain of `RichText.lang` (§4.1). |
| `status` | string \| null | The document status **as the author declares it**, e.g. `"Approved"`. Free-form. |
| `version` | string \| null | The document version **as the author declares it**, e.g. `"1.2"`. Free-form. |
| `extra` | object of string → string | Any other title-page metadata, as string pairs. Defaults to `{}` and may be omitted. |

```json
"doc": { "title": "Deployment guide", "status": "Approved", "version": "1.2",
         "extra": { "client": "ACME", "reference": "PRJ-042" } }
```

`status` and `version` record what the author printed on the document,
such as a title page reading "Status: Approved, Version 1.2". They have
no relation to `cnd_version`, and they do not give a CND a version
history of its own (§11): they are authored values, not a build lineage.

The keys of `extra` are an open vocabulary (§6.0) of which this
specification defines none; a consumer may use or ignore them. **An
`extra` key MUST NOT repeat the name of a `DocMetadata` field** — `extra`
included — or the document would carry two contradictory values for one
fact. A key in wide use becomes a named field in a minor version.

## 4. Node base

Every node (see `NodeBase` in `src/cnd/core/nodes.py`) shares:

| Field | Type | Description |
|---|---|---|
| `id` | UUID | Node identifier — unique within the CND, **not durable across builds** (§2, docs/adr/0015). |
| `label` | string \| null | Human-assigned label (e.g. a Typst `<label>`). Globally unique when present (§2). The only durable identity a node has, because it lives in the source rather than being minted by the build. A node that nothing references may omit it; a node that something references must carry it, since a label is the only way to name a target. |
| `state_metadata` | object | Free-form extension bag for compiler- or consumer-specific state. Not interpreted by the standard. |
| `location` | `NodeLocation` \| null | Layout facts the consumer cannot derive from the tree. A single field: `page`, the page on which the node **begins** in the built document. Null on an unpaginated CND — see §2.2 for the all-or-nothing rule. |

The node base carries no link family. The four families live on the
node's texts (§4.1) and point **outward** — there is no serialized
incoming-edge field of any kind.

### 4.1 Rich text

Every slot that holds prose is a `RichText` object (§6, principle 1).

| Field | Type | Description |
|---|---|---|
| `value` | string, required | The text. Every span in this object indexes it. |
| `lang` | string \| null | Language of this text. |
| `marks` | array of [`Mark`](#marks) | Inline formatting, as standoff spans. |
| `refs` | array of [`NodeRef`](#5-cross-references-and-link-families) | Outgoing cross-references to nodes. |
| `cites` | array of [`CiteRef`](#5-cross-references-and-link-families) | Outgoing citations, resolving in the `bibliography` pool. |
| `footnotes` | array of [`FootnoteRef`](#5-cross-references-and-link-families) | Outgoing footnote markers, resolving in the `footnotes` pool. |
| `links` | array of [`LinkRef`](#5-cross-references-and-link-families) | Outgoing hyperlinks, resolving nowhere in the CND. |

```json
{ "id": "…", "type": "paragraph",
  "text": { "value": "See Figure 2: the rate rose 103 times.",
            "marks": [ { "start": 30, "end": 31, "kind": "sup" } ],
            "refs":  [ { "label": "fig-rate", "text_span": [4, 12] } ] } }
```

- **`value` is passed through unaltered** by every producer and by the
  builder (§12): the spans index it, so any whitespace collapse or
  re-normalization silently shifts them.
- **Edges belong to texts.** An edge belongs to **the text in which its
  marker opens**. Its owning node is the nearest node holding that text;
  an edge in a bibliography entry's `formatted` text (§5.1) is owned by
  that entry, not by a node.
- **`lang`.** `null` inherits: from the enclosing text, then from the
  enclosing node chain, then from `doc.lang`. In this revision no text
  encloses another and no node carries a natural-language `lang` of its
  own, so in practice the chain resolves to `doc.lang`. (`code.lang`
  names a programming language, §6.5, and plays no part in this rule.)
  `lang` covers a whole text; a foreign phrase
  inside a sentence is not modeled.
- **Empty lists may be omitted.** Every list field defaults to empty, so
  a plain paragraph is `{"id": "…", "type": "paragraph", "text": {"value": "…"}}`.
  Omitting an empty list and writing it out are the same content and
  hash the same (§10).

#### Marks

A `Mark` is a standoff span of inline formatting inside `value`:

| Field | Type | Description |
|---|---|---|
| `start` | int, required | Start offset, inclusive, in Unicode code points (docs/adr/0013). |
| `end` | int, required | End offset, exclusive. |
| `kind` | string, required | What the span is. An open vocabulary (§6.0). |
| `raw` | `RawSource` \| null | The source of the covered text. Only `math` uses it in this revision. |

The known kinds:

| `kind` | Meaning |
|---|---|
| `strong` | strong importance, usually bold |
| `emph` | emphasis, usually italic |
| `code` | inline code |
| `strike` | struck-through text |
| `sup` | superscript |
| `sub` | subscript |
| `underline` | underline |
| `highlight` | highlighted text |
| `math` | inline math: `value` holds a readable linear form of the formula, `raw` its source |

```json
{ "value": "The speed v = d/t is constant",
  "marks": [ { "start": 10, "end": 17, "kind": "math",
               "raw": { "format": "typst", "value": "v = d/t" } } ] }
```

**Fallback for an unknown kind: the covered text is rendered
unchanged.** Because `value` always holds the plain text, ignoring a mark
never loses a word.

**Rules (normative, checked by validation, §9).**

1. **Bounds.** `0 ≤ start < end ≤ len(value)`, in code points. An empty
   mark is invalid.
2. **Free overlap.** Marks of different kinds may overlap without
   nesting: a `strong` mark over "abc" and an `emph` mark over "cd" are
   valid together.
3. **Canonical form.** Two marks of the same kind never overlap and never
   touch (`[0, 3)` and `[3, 5)` touch); a producer merges them. Marks are
   sorted by `(start, end, kind)`, `kind` compared by code point. One rich
   text therefore has one serialization, and one hash.
4. **Atomic verbatim.** A `code` or `math` mark is verbatim: no other
   mark and no edge `text_span` reaches inside it. Another mark or span
   is either disjoint from it or covers it whole (a link over an entire
   inline formula is valid); a mark or span that overlaps it partially,
   or sits inside it, is invalid.
5. **Edges are independent of marks.** A link may be bold, and a bold
   span may cover half a link.

Renderers must produce well-nested output: where two marks cross, a
renderer splits one of them at the crossing point (§7).

## 5. Cross-references and link families

The cross-reference graph is **forward-only**: a CND serializes only
the edges from a referencing text to its target. There is no
bidirectional invariant and no `refs_from` field — the reverse index is
derived by consumers (the reference SDK provides `Cnd.incoming(label)`,
built lazily from the forward edges of every node's texts, body and
footnote content alike).

Every edge lives in a `RichText` (§4.1). An edge names its target **by
label, and carries no id** (docs/adr/0017, superseding docs/adr/0002).
All three label-keyed families share the skeleton `{label, text_span?}`:

| Field | Type | Description |
|---|---|---|
| `label` | string, required | The target's label. Resolves in the nodes (body and footnote content) for `refs`, in `bibliography` for `cites`, in `footnotes` for `footnotes`. |
| `text_span` | `[start, end)` array of 2 ints \| null | Optional standoff position of the link's marker (e.g. a `@fig-3` marker) inside the `value` of the `RichText` that holds the edge. Offsets are **Unicode code points**, not bytes (docs/adr/0013). |

A `text_span` satisfies `0 ≤ start ≤ end ≤ len(value)`; unlike a mark it
may be empty. It is null for a marker that renders no text, or one that
does not close inside the text where it opens.

`NodeRef` is exactly this skeleton:

```json
{ "label": "eq-golden", "text_span": [29, 38] }
```

Edges key on the label rather than the id because an id is not durable
(§2): an edge carrying one would be a reference that expires at the next
build. The label lives in the source, so it survives one.

A fourth family, `links`, carries a forward hyperlink rather than a
cross-reference: it is keyed by `href`, not by `label`, and shares only
`text_span` with the other three (docs/adr/0024):

| Field | Type | Description |
|---|---|---|
| `href` | string, required | The link target — any URI the producer captured (`https:`, `doi:`, an application scheme). The format does not parse or validate it; the scheme is a consumer's business. |
| `text_span` | `[start, end)` array of 2 ints \| null | Same meaning as above. |

`LinkRef` is exactly `{href, text_span?}`:

```json
{ "href": "https://example.com/spec", "text_span": [4, 17] }
```

Unlike the three label-keyed families, a `links` edge names a target
**outside** the CND by construction — a URL, not something the document
carries — so it has no resolution domain and no dangling state: a URL is
a URL whether or not anything ever fetches it.

**Resolution (normative).** This rule applies to the three label-keyed
families (`refs`, `cites`, `footnotes`), wherever their text sits — in a
body node, in a footnote content node, or in a bibliography entry's
`formatted`. `links` carries no label and is outside it: a `links` edge
is never invalid for naming something the CND does not carry. A
conformant CND satisfies both of:

1. every edge's `label` is carried by something in the CND — an edge
   naming a label nothing carries is invalid;
2. the target sits in the **domain of the family the edge appears in** —
   a `refs` edge resolves to a node (a footnote content node included,
   e.g. an equation inside a note), a `cites` edge to a bibliography
   entry, a `footnotes` edge to a footnote.

The second is not implied by the first. Labels are unique across the
whole CND (§2), so a `cites` edge naming a heading resolves to
*something*; the family is what makes it wrong. A consumer may build one
global `label → target` index and check the target's kind, which is what
the reference SDK does (`Cnd.resolve`).

A node with several texts — a figure's caption and description, a term
list's terms — carries the edges of each text in that text. The
reference SDK flattens them per node with `edges_of(node)` (over
`texts_of(node)`, the node's own texts in document order, never a nested
node's), so resolution and validation code reads one list per node.

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

Example, a paragraph referencing a listing, citing an article, and
carrying a footnote marker:

```json
{
  "type": "paragraph",
  "text": {
    "value": "Selon Smith et al., voir le listing 1.",
    "refs": [
      { "label": "lst-api", "text_span": [28, 37] }
    ],
    "cites": [
      { "label": "smith2024", "text_span": [6, 18], "form": "prose", "supplement": "p. 12" }
    ],
    "footnotes": [
      { "label": "fn-rest", "text_span": null }
    ]
  }
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
| `formatted` | `RichText` \| null | The reference as displayed in the built document — the faithful capture. Rich text, because a formatted reference carries italics (a journal title) and sometimes links. Nullable: requiring it would presuppose that a citation style engine ran, which a hand author or a markdown producer has no reason to have. |
| `type` | string \| null | Entry type (e.g. `"article"`). |
| `authors` | array of string | Author names. |
| `title` | string \| null | Work title. |
| `year` | int \| null | Publication year. |
| `container` | string \| null | Containing work (journal, book, proceedings…). |
| `doi` | string \| null | DOI. |
| `url` | string \| null | URL. |
| `fields` | object | Lossless passthrough of the full source entry (e.g. the Hayagriva entry) as structured JSON — carries every field the curated subset above doesn't type. Named `fields` rather than `raw` because `raw` means something else on nodes (§6). |

**Content floor (normative).** An entry MUST carry `formatted`, at least
one structured field, or both. An entry with neither is one a citation
can reach but nothing can display.

### 5.2 Footnotes pool

`footnotes` (top-level) is a list of `Footnote` objects — the targets of
`footnotes` edges. A footnote holds **block nodes** in its `children`,
so a note may contain several paragraphs or a list.

| Field | Type | Description |
|---|---|---|
| `id` | UUID, required | Entry identifier (unique document-wide). |
| `label` | string, required | Footnote label/marker key. |
| `children` | array of node | The footnote's content. |

Footnote content nodes are **nodes in every respect**:

- their ids join global id uniqueness, and their labels join global label
  uniqueness (§2); a `refs` edge may target one;
- `location` follows the all-or-nothing rule of §2.2: on a paginated CND
  they carry the page where the note is printed;
- validation (§9) and hashing (§10) cover them like any other node.

They stay **out of the body tree**. Walking `nodes` does not visit them,
so a consumer splitting the body into passages never mixes notes into
running text; the full traversal (§8) walks them after the body.

## 6. Node types

All node types inherit the [node base](#4-node-base) fields plus `type`
(a discriminator literal) and their own fields below. See
`src/cnd/core/nodes.py` for the authoritative definitions.

Two principles shape every node type.

**Principle 1 — prose is rich text; verbatim is a string.** Every slot
that holds **prose** is a [`RichText`](#41-rich-text). Every slot that
holds **verbatim** content (code, math source, `raw`) or **metadata**
(`image.alt`, `code.title`, `heading_path`, `doc.title`) is a plain
string. The test: can an author make part of it bold or put a
cross-reference in it? If so, it is prose.

**Principle 2 — nested nodes always live in `children`.** An object that
contains block nodes holds them in a field named `children`, without
exception: the nodes `heading`, `quote`, `figure` and `admonition`, and
the value objects that are not nodes — `ListItem`, `TermItem`, `Cell`
and `Footnote`. A generic walker follows one field name. Short **labels**
attached to a node (a heading's text, a caption, a title, a term, an
attribution) are `RichText`; **bodies** are `children`. No slot accepts
both forms: a union such as `RichText | Node[]` would let the same
content be written two ways, which breaks canonical hashing and makes
every consumer handle both shapes.

**Defaults.** Every field not marked required below has a default, and
`schema/cnd.schema.json` states it with `default`; §10 drops a field
holding its default before hashing, so the defaults are normative.
The rule is uniform:

- **Empty list `[]`:** every `children`, `items` and `cells`; the
  `RichText` families `marks`, `refs`, `cites`, `footnotes` and `links`;
  `doc.authors` and `doc.keywords`; `BibEntry.authors`; the CND's
  `bibliography` and `footnotes`.
- **Empty object `{}`:** `state_metadata` on every node, `doc.extra`
  and `BibEntry.fields`.
- **`false`:** `list.ordered` and `Cell.is_header`.
- **`1`:** `Cell.rowspan` and `Cell.colspan`.
- **`null`:** every other optional field (`label`, `location`,
  `numbering`, `raw`, `kind`, `lang`, `text_span`, `source`,
  `doc.date` and the rest of the optional metadata, and so on).

The one default that is not a constant is the CND's own `id`, which is
generated when absent; it is not part of the hashable value (§10).

Two fields recur across node types and are defined once here.

**`numbering`** — carried by `heading`, `math` and `figure`, always
nullable. A `Numbering` object:

| Field | Type | Description |
|---|---|---|
| `value` | string, required | The counter value **as resolved and displayed**: `"2.1.1"`, `"(1)"`, `"iv"`. |
| `name` | string \| null | The counter word displayed in front of the value (`"Figure"`, `"Tabelle"`, `"Listing"`), **as resolved in the document's language**. Null when the document shows no word. |

```json
{ "type": "figure", "kind": "atom",
  "numbering": { "value": "1", "name": "Atom" },
  "caption": { "value": "A curious atom." } }
```

`value` is never the pattern that produced it, because a consumer cannot
replay a counter engine and so could do nothing with one. It is never
the counter word either: `"Figure 3"` fuses a locale into the value, and
composing that prefix is a rendering decision. A consumer wanting
locale-free structure reads `kind`; one reproducing the document composes
`name` and `value`.

`name` is a field rather than something derived because it is not always
derivable. A producer resolves it from the element kind and the document
language, using a localization table no consumer has; and for an
author-defined `kind` there is no such table at all, so the author
supplies the word and nothing else in the CND encodes it
(docs/proposals/0010).

`numbering` is null when the element is unnumbered. A word without a
value cannot be written. The names are deliberately not `count` (the
value is a displayed string, not a quantity) and not `label` (a node's
`label` is its cross-reference identity).

**`raw`** — carried by `math` and `figure`, always nullable.
The producer's verbatim source for the node, as a `RawSource` object:

```json
{ "format": "typst", "value": "$ e(t) = m(t) - r(t) $" }
```

`format` is an open vocabulary (§6.0) (`"typst"`, `"latex"`,
`"mathml"`…). It exists because a bare string dropped the one thing a
consumer needs in order to decide whether to attempt a parse: which
language the content is in. On a figure, `raw` is the escape hatch for
content the model cannot express (§6.7).

### 6.0 Open vocabularies

Several fields take a value from a list this specification defines, but
must also accept values an author or producer invents: a figure kind
such as `"theorem"`, a callout such as `"example"`. These are **open
vocabularies**, and they share one contract (docs/adr/0026):

- **Known values** have a definition in this specification. A producer
  uses a known value whenever one fits; it does not mint `"warn"` when
  `"warning"` exists.
- **Free values** are any other string. They carry no prefix (no `x-`):
  a prefixed value would have to be renamed everywhere on the day it
  becomes standard.
- **Consumers never fail on an unknown value.** Each open field defines
  its fallback.
- **Promotion.** A free value in wide use becomes a known value in a
  minor version.

The open vocabularies of this revision:

| Field | Known values | Fallback for an unknown value |
|---|---|---|
| `figure.kind` | none defined (`"image"`, `"table"`, `"theorem"`…, §6.7) | Treat the figure generically: its content is its `children`. |
| `admonition.kind` | `note`, `tip`, `important`, `warning`, `caution` (§6.11) | Render a generic callout headed by the title, or by the kind when there is no title. |
| `Mark.kind` | the table of §4.1 | Render the covered text unchanged. |
| `table.kind` | `data`, `content` (§6.3) | Treat as `null`: the author did not say. |
| `code.lang` | none defined (`"python"`, `"rust"`…) | Treat the code as text in an unstated language. |
| `raw.format` | none defined (`"typst"`, `"latex"`, `"mathml"`…) | Do not attempt a parse; keep `value` opaque. |
| `source.type` | none defined (`"typst"`, `"markdown"`, `"doclang"`…) | Treat as an opaque producer identifier. |
| keys of `doc.extra` | none defined (§3) | Use or ignore the pair. |

Closed enumerations stay closed where a consumer must understand the
value exactly to process the data. The node `type` discriminator is one:
an unknown node type cannot be read.

### 6.1 `heading`

| Field | Type |
|---|---|
| `level` | int |
| `numbering` | `Numbering` \| null |
| `text` | `RichText` |
| `heading_path` | array of string |
| `children` | array of node |

A section heading. The section's content is in `children`.

### 6.2 `paragraph`

| Field | Type |
|---|---|
| `text` | `RichText` |

The leaf that carries prose. Text inside a list item, a cell, a quote or
a footnote is a paragraph.

### 6.3 `table`

| Field | Type |
|---|---|
| `kind` | string \| null |
| `cells` | array of `Cell` |

A `Cell`:

| Field | Type | Description |
|---|---|---|
| `row` | int | Row coordinate. |
| `col` | int | Column coordinate. |
| `rowspan` | int | Rows covered, at least 1. Defaults to 1. |
| `colspan` | int | Columns covered, at least 1. Defaults to 1. |
| `is_header` | bool | Header cell. Defaults to `false`. |
| `children` | array of node | The cell's content: a text cell holds one paragraph; a cell may also hold an image, a list or several paragraphs. |

A `table` is a grid whose **rows and columns carry meaning**: the cell
at row "Pro", column "Price" is the price of the Pro plan. A grid used
for arrangement only is a [`layout`](#612-layout), never a table, so a
consumer that processes tables never reads a layout as data. `cells` is
in reading order (§2).

`kind` says what the table is, as a fact about the document. It is an
open vocabulary (§6.0):

| `kind` | Meaning |
|---|---|
| `"data"` | A dataset: each row is a record of values, such as instrument readings. |
| `"content"` | The cells are content to read: a feature comparison, a catalogue with an image beside its description. |
| `null` | The author did not say. A consumer applies its own default and may infer one. |

Producers never guess `kind`: the value comes from the author. A
classifier, if anyone writes one, belongs to the consumer.

A table has **no caption or figure number of its own** — a captioned or
numbered table is a `table` node wrapped in a [`figure`](#67-figure) node,
which carries the caption. A bare table (not in a figure) is simply a
`table` node with no wrapper. A table that cannot be converted is wrapped
in a figure that carries `raw`.

### 6.4 `quote`

| Field | Type |
|---|---|
| `attribution` | `RichText` \| null |
| `children` | array of node |

A block quotation; a multi-paragraph quote keeps its paragraphs. An
inline quotation is not a node: it stays text in the enclosing
paragraph, quotation marks included.

### 6.5 `code`

| Field | Type |
|---|---|
| `text` | string |
| `lang` | string \| null |
| `title` | string \| null |

A code block, verbatim. Inline code is a `code` mark (§4.1). `lang` is
the programming language, an open vocabulary (§6.0). `title` is the
label an author attaches to a listing, typically a file name
(`"main.py"`) — a plain string, because it is metadata, not prose.

### 6.6 `math`

| Field | Type |
|---|---|
| `text` | string |
| `raw` | `RawSource` \| null |
| `numbering` | `Numbering` \| null |

A block equation: `text` is a readable linear form, `raw` the source.
Inline math is a `math` mark that carries its source (§4.1), so a
paragraph that contains a formula stays one paragraph and reads as
continuous text.

### 6.7 `figure`

A **wrapper** node: the captioned/numbered float, never a content carrier.
The wrapped content lives in `children` and keeps its own node type.

| Field | Type |
|---|---|
| `kind` | string \| null |
| `caption` | `RichText` \| null |
| `description` | `RichText` \| null |
| `numbering` | `Numbering` \| null |
| `children` | array of node |
| `raw` | `RawSource` \| null |

`kind` is the figure's **category, independent of language**, an open
vocabulary (§6.0). It is never a content discriminator: what the figure
contains is determined by the node types in `children`, not by `kind`.
Its main use is the author-defined categories that `children` cannot
reveal — theorems, definitions, examples, algorithms. All of those
contain paragraphs, and only `kind` tells them apart; `numbering.name`
is localized and absent when the figure is unnumbered.

`description` is the **text equivalent of the figure's visual content**.
For a chart, it states the values ("Bars: A 38 %, B 27 %…"); for a
diagram, it states the structure ("The pipeline forks after deployment
into staging and production"). The caption is the short title shown on
the page; the description is what a reader who cannot see the visual —
a language model, a screen reader — needs instead.

`raw` is the escape hatch for content the model cannot express yet.

Producer mapping (informative — the producer itself is out of scope, see
docs/adr/0006): `#figure(image)` → `figure` wrapping an `image` node;
`#figure(table)` → `figure` wrapping a `table` node; `#figure(raw)` →
`figure` wrapping a `code` node; a multi-body figure → `figure` with
several children; an unconvertible body → `children: []` with `raw`
filled. A figure whose body is a **drawing** (a diagram, a plotted
chart, a canvas) is emitted with `raw` filled and no scattered
`children`, rather than as stray text labels lifted out of the drawing;
a dataset beside a chart is a second child of the same figure (a `table`
with `kind: "data"`).

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
| `ordered` | bool (defaults to `false`) |
| `items` | array of `ListItem` |

A `ListItem`:

| Field | Type | Description |
|---|---|---|
| `number` | int \| null | The item's ordinal as displayed. A list ordinal, not a document counter. |
| `checked` | bool \| null | `true` or `false` marks a task-list item; `null` means the item is not a checkbox. |
| `children` | array of node | The item's content. Its text is a paragraph. |

A nested list is a `list` node inside an item's `children`, with its own
`ordered`: a bullet list under a numbered item stays a bullet list.

A list records no spacing: whether it is "tight" carries no meaning for
a reader, and the one output where it matters, Markdown, derives it — a
list is tight unless an item holds several blocks.

### 6.10 `terms`

A definition list (Typst `/ term: description` items).

| Field | Type |
|---|---|
| `items` | array of `TermItem` (`term`, `children`) |

`term` is a `RichText`; the definition is the block nodes in
`children`, since a definition often spans several paragraphs or holds
a list. Like `ListItem` and `Cell`, a `TermItem` carries no `id` and is
not ref-targetable.

### 6.11 `admonition`

A callout, such as "Note" or "Warning".

| Field | Type |
|---|---|
| `kind` | string |
| `title` | `RichText` \| null |
| `children` | array of node |

```json
{ "type": "admonition", "kind": "warning", "title": { "value": "Careful" },
  "children": [ … ] }
```

`kind` is an open vocabulary (§6.0). The known values are those of the
widely used Markdown alert syntax: `note`, `tip`, `important`,
`warning`, `caution`. `title` is the title as displayed, in the
document's language, or null. **Fallback for an unknown kind:** a
generic callout — a quote block headed by the title, or by the kind
when there is no title.

### 6.12 `layout`

| Field | Type |
|---|---|
| `cells` | array of `Cell` |

A grid used **for arrangement only**, such as two images side by side or
a block of cards: position carries no relation between cells. It shares
the `Cell` model of [`table`](#63-table), and `cells` is in reading order
(§2). `layout` covers grids only; other layout primitives (stacks,
columns, absolute placement) stay flattened by producers.

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
  emits a parseable `[[figure:<id> …]]` placeholder carrying what the node
  holds except a table's body cells (kind, counter word, number, caption,
  description, table kind, header row, size, row labels, child summary;
  docs/proposals/0012), `"inline"` renders the cells/children as text,
  and `"auto"` defers to the table's `kind` (§6.3): inline for `"content"`,
  a placeholder for `"data"`, an unset kind or an unknown one.
  `text_only=True` selects the text-only output described below;
  `MarkdownConverter` takes the same option.

**Policy for marks and new elements.** Every renderer and converter
renders what it supports and leaves the text of anything else unchanged.

- **Markdown.** `strong`, `emph`, `code` and `strike` render as `**…**`,
  `*…*`, `` `…` `` and `~~…~~`; `math` as `$…$`. The four marks without
  CommonMark or GFM syntax — `sup`, `sub`, `underline`, `highlight` —
  render as inline HTML (`<sup>`, `<sub>`, `<u>`, `<mark>`) by default.
  A text-only option writes no HTML: `sup` becomes `^x` over one
  character and `^(text)` over several, `sub` likewise `_x` and
  `_(text)` (with the `_` escaped where free text is escaped, so it
  never opens emphasis), and `underline` and `highlight` drop to plain
  text. A mark Markdown cannot
  delimit where it sits (a closing `**` between punctuation and a letter,
  say) renders as its HTML tag, or as plain text under the text-only
  option. Where two marks cross, one
  is split at the crossing point so the output nests. An `admonition`
  with a known kind renders as a GFM alert (`> [!WARNING]`), an unknown
  kind as a quote whose first line is the title in bold. A checked or
  unchecked item renders as `- [x]` or `- [ ]`. A `code.title` renders as
  a line directly before the fence. A `figure.description` renders as a
  paragraph after the caption. A `table` renders as a GFM table when
  every cell holds inline-renderable content (one paragraph, or an
  image), otherwise as an HTML table, or as linearized rows under the
  text-only option. A `layout` is flattened: cell contents in reading
  order, row by row. A `math` block renders as a fenced block with the
  info string `math`, holding its source when that source is LaTeX and
  its `text` otherwise. `doc.status`, `doc.version` and `doc.extra`
  render wherever the other document metadata does. A `links` edge
  renders as a marker after its block, `[href](href)`, its text and
  destination escaped so that the destination parses back to the href;
  an href that fails the URL rule below is written as escaped plain
  text, never as a link.
- **HTML.** Marks map to `<strong>`, `<em>`, `<code>`, `<s>`, `<sup>`,
  `<sub>`, `<u>`, `<mark>`; a `math` mark keeps its source in a
  `<code class="math">` element. An `admonition` maps to an `<aside>`
  with a kind class, and a `layout` to a CSS grid. A `links` edge with a
  `text_span` makes the text it spans an `<a class="cnd-link">` anchor;
  anchors never nest, so of two links whose spans overlap the outer or
  first one wins. Every link that does not render inline — no span, a
  span that is empty or lies inside a `code` or `math` atom, a link
  that loses to an overlapping one — goes to the marker line after its
  block, as `<a class="cnd-link" href="…">href</a>`, so no link is
  lost. An image `src` follows the same URL rule, a `data:image/` URI
  aside.
- **URL rule.** A renderer links to an href only when its scheme is
  `http`, `https` or `mailto` (in any case), or when it has no scheme
  (a relative path, a fragment). The scheme is read as leniently as any
  reader of the output reads it: leading controls and leading Unicode
  whitespace ignored (a browser strips the first, a Markdown parser the
  second), tabs and newlines removed anywhere. Anything else
  stays plain text: the spanned text without an anchor, the href as
  text in the marker line.
- **Plain text** drops all marks; a `math` mark renders its `value`.

The exact Markdown produced is **not normative** — no consumer may rely on
its precise shape as part of the format. The "raw" representation of a node
is its JSON serialization itself (`model_dump_json()`), not a renderer.

**Converters** sit one layer above, and are equally non-normative. Where a
renderer maps one node to a fragment, a converter maps a whole CND to one
complete standalone artifact: document front matter, sections assembled by
walking the tree in reading order, and the out-of-tree pools (§5) emitted
as footnote and bibliography sections with their markers resolved by label.
The reference SDK ships `cnd.converters.MarkdownConverter` and
`cnd.converters.HtmlConverter` (docs/proposals/0007). Conversion is
one-way and lossy by construction — a converter projects a CND onto a
foreign format and documents what it drops. **No converter output round-
trips back into a CND**, and no converter output shape is ever a
conformance requirement.

## 8. Traversal

Traversal is **not shared as code across languages** (docs/adr/0019): a
walk carries state, and state does not cross a language boundary without
becoming monstrous. Every implementation writes its own. That makes the
semantics normative prose rather than an implementation detail — two
implementations that disagree here disagree invisibly, since nothing in
the file records the order they chose.

**Containers.** A node's nested nodes sit in its **slots**: the
`children` of a `heading`, `quote`, `figure` or `admonition`; the
`children` of each entry of the `items` of a `list` or `terms`; the
`children` of each entry of the `cells` of a `table` or `layout`. Items
and cells are not nodes: a walk never yields them, and they add no depth
level — a paragraph in a cell sits one level below the table, and its
parent is the table.

**Walk order (normative).** Depth-first over `nodes`: each node is
yielded before its nested nodes; a node's items or cells are entered in
list order, each entry's `children` in list order. Because the tree is in
reading order (§2), the walk order *is* reading order. A consumer may
prune a subtree; pruning does not change the positions of the nodes
still visited, which are document facts rather than walk artifacts.

**Slot and path (normative).** Every yielded node is paired with where it
sits:

- `slot` — the kind of list the node is in: `"children"`, `"items"`,
  `"cells"` or `"footnotes"` (the top-level content of a footnote), or
  null at the top level of the body;
- `slot_index` — the index of the item, the cell, or the footnote in its
  pool; null for `"children"` and at the top level of the body;
- `path` — the node's full position, the sequence of field names and
  list indexes from the root of the CND to the node, written with `/`:
  `nodes/0/children/4/cells/2/children/0` is the first node of the third
  cell of a table that is the fifth child of the first top-level node.
  Footnote content is under `footnotes/<i>/children/<j>`.

A consumer uses the slot to treat a list or a table as one unit — when
splitting a document into passages, for example — instead of emitting
one passage per cell paragraph. The path feeds the document hash (§10).

**The body walk and the full walk (normative).** The **body walk** visits
`nodes` only, and is reading order. The **full walk** is the body walk,
then the content of each footnote, in pool order, each walked by the
same rules. Footnote content has no place in the body's reading order:
where notes appear is a rendering convention (at the foot, at the end).
So positions inside a footnote count **within that footnote** — its
top-level nodes have depth 0 and no parent, and their `doc_*`,
`sibling_*` and `page_*` positions are counted over that footnote's
content alone. Document-wide checks (§9) and the document hash (§10) use
the full walk, so footnote content is never skipped by either.

**Pool entries never enter a walk (normative).** A traversal yields
nodes only. Bibliography entries and footnote entries are reached by
resolving a link (§5), never by iterating; the full walk visits a
footnote's content nodes, not the entry that holds them. A consumer that
wants the entries iterates the pools directly.

**Link families are not ordered against each other (normative).** Within
a text, each family's list preserves the order the producer emitted, and
the four families are enumerated `refs`, `cites`, `footnotes`, `links`
for ordering and reproducible output. That enumeration is a stable
convention only — it carries **no** claim about where the markers sit
in the text, and no claim about resolution: `links` keeps the narrower
scope §5 gives it there (it is href-keyed, not label-keyed, and the
normative resolution rule does not reach it). The only positional truth
about any marker, in any of the four families, is its `text_span`; a
consumer that needs markers in text order sorts by it across all four.

**Derived positions.** Every yielded node is paired with a context
carrying 1-based `index`/`count` pairs: `doc_index`/`doc_count`
(position in the walk — the body, or one footnote's content),
`sibling_index`/`sibling_count` (position among the nodes of the same
slot list: one `children` list of a node, an item or a cell), and
`page_index`/`page_count` (position among the nodes beginning on the
same `location.page`). The page pair is **absent** on an unpaginated CND
(§2.2) — undefined, not zero.

**Granularity.** This model yields more nodes than a model where a list
item or a cell is one string: every list item and every non-empty cell
holds at least one paragraph node. The walk counters count them, and
reconciliation (docs/adr/0018) gets finer — an edited list item is
matched and reported on its own, where a whole list used to be marked
changed.

**Conformance.** The fixture corpus carries `CND → expected walk`
vectors (`fixtures/traversal.json`): for every fixture, the full walk as
a sequence of `id`, `type`, `depth` and `path`. An implementation proves
its walk order by reproducing them. `cnd inspect` shows the body walk
only, not the footnotes' content; `cnd hash --nodes` lists every node
hash in full-walk order.

The reference SDK implements the body walk as `Cnd.iter()` /
`iter_nodes()` and the full walk as `Cnd.iter_all()`, with
`child_slots(node)` listing a node's slots, `BaseVisitor` dispatching a
`visit_<type>` hook per node type over the body walk, or over the full walk
with `visit(cnd, full=True)`, and `should_stop_descent()` to prune.
`Cnd.incoming(label)` is the derived reverse index (§5) and
`Cnd.resolve(label)` the label index (§5), both built over the full walk,
lazily, and cached. `NodeDisplayVisitor` (requires the `display` extra)
renders a colorized trace for terminal inspection.

## 9. Validation

Some invariants cannot be stated in JSON Schema — they are relational or
document-wide, and a schema validates one value at a time. A CND is
conformant only if it satisfies all of the following. Each is checked
over the full walk (§8), so footnote content nodes are covered like body
nodes, and the text checks also read every bibliography entry's
`formatted`. The rule is the stable identifier the reference validator
reports.

| Invariant | Rule | Where |
|---|---|---|
| `cnd_version` is the version the validator implements (`"0.5.0"` for this revision) | `cnd-version-unsupported` | §11 |
| Global id uniqueness: body nodes, footnote content nodes, bibliography and footnote entries | `id-not-unique` | §2 |
| Global label uniqueness, footnote content nodes included | `label-not-unique` | §2 |
| Every label-keyed edge resolves (`links` is out of scope) | `link-unresolved` | §5 |
| Every label-keyed edge resolves in its family's domain | `link-wrong-domain` | §5 |
| Every `text_span` has two offsets and lies inside its text's `value` | `text-span-out-of-bounds` | §5 |
| Every mark lies inside its text's `value` and is non-empty | `mark-out-of-bounds` | §4.1, Marks |
| Marks are sorted by `(start, end, kind)` | `mark-not-canonical` | §4.1, Marks |
| Two marks of the same kind neither overlap nor touch | `mark-same-kind-overlap` | §4.1, Marks |
| `code` and `math` marks are atomic: no mark or edge span reaches inside one | `mark-atomic-crossed` | §4.1, Marks |
| Pagination is all-or-nothing, footnote content nodes included | `pagination-partial` | §2.2 |
| Every bibliography entry meets the content floor | `bib-entry-empty` | §5.1 |
| No `doc.extra` key repeats a `DocMetadata` field name | `doc-extra-shadows-field` | §3 |

These are enforced in one of two places depending on how the CND was
produced (docs/adr/0019). A producer going through a declaration cannot
bypass the builder that checks them. A producer emitting a CND directly
from its own compiler calls a validator itself — the reference SDK
exposes `validate(cnd)`, which returns every violation rather than the
first, and the same check as `cnd validate` on the command line.

A file stamped with another `cnd_version` is refused by that rule
before its shape is checked: the reference CLI reads the version first,
so a 0.4 CND is reported as a 0.4 CND, not as the schema errors its
older shape raises. Before 1.0.0 a minor version may change what a field
means (§11), so a CND whose shape happens to parse under another version
is still not conformant to this one.

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

**Algorithm (normative)** (docs/adr/0028).

1. Take the hashable value (below).
2. Drop every default-valued field (below).
3. Normalize every string — keys as well as values — to Unicode **NFC**.
4. Serialize with [RFC 8785 JSON Canonicalization Scheme
   (JCS)](https://www.rfc-editor.org/rfc/rfc8785).
5. Hash the resulting bytes with SHA-256; render as `"sha256:<hex>"`.

Both canonicalisations are external references rather than a bespoke
scheme, so an implementation in any language can reproduce the bytes.
JCS is load-bearing beyond key ordering: its ECMAScript number
serialization is where a hand-rolled implementation silently diverges.

**Defaults are dropped.** A field that the schema declares with a
default and that holds exactly that default is removed from the hashable
value: `null`, `[]` and `{}` where those are the defaults, `false` for
`ordered` and `is_header`, `1` for `rowspan` and `colspan` (the full
list is in §6, *Defaults*, and every one is a `default` in the schema). The rule
applies at every level the schema models — inside a `RichText`, a
`Mark`, a `Cell`, a `ListItem`, a `DocDate` — but not inside a free-form
object (`state_metadata`, `BibEntry.fields`), whose contents are hashed
as written. A required field is never dropped, even when empty
(`heading_path: []`). Omitting an empty list and writing it out
therefore hash the same, and a future version that adds an optional
field does not move an existing hash.

**Node hash.** Over a node's own fields, **excluding** `id`, `location`,
`numbering` and every nested node. `id`, `location` and `numbering` are
resolved presentation state — computed for display, and changing without
the authored content changing. The excluded `numbering` is the case
that would break silently: inserting a heading renumbers every node
after it, so a hash covering `numbering` would report each of them as
changed.

Nested nodes are excluded wherever they sit: the node's own `children`,
and the `children` of each entry of its `items` (list and term items)
and its `cells`. The entries themselves stay in the hash — a list item's
`number` and `checked`, a term's `term`, a cell's coordinates, spans and
header flag — so adding an item or a cell changes the container's hash,
while editing the paragraph inside an item changes only the paragraph's.
A heading whose subsection changed has not itself changed, and treating
it as changed would defeat the matching pass that recognises a
moved-but-unchanged node (docs/adr/0018). Only these structural
`children` keys are removed: a key named `children` inside
`state_metadata` is content.

**Pool entry hash.** A bibliography entry is hashed over its fields
except `id`. A footnote entry is hashed over its fields except `id` and
`children` — its content nodes are hashed as nodes, in the document hash.

**Document hash.** Over a JSON object with exactly four keys:

| Key | Value |
|---|---|
| `doc` | The `doc` metadata, defaults dropped. |
| `nodes` | An array of `[path, node_hash]` pairs, one per node of the full walk (§8), in walk order; `path` is the `/`-joined path string. |
| `bibliography` | An array of the bibliography entry hashes, in pool order. |
| `footnotes` | An array of the footnote entry hashes, in pool order. |

The three arrays are always present, empty or not. Excluded: the CND's
`id`, `built_at`, `source` and `cnd_version` — the same content built
twice, reached from two input formats, or expressed under two format
versions is the same content.

The full path is paired with each node hash, not only its depth, because
nesting and placement are structure, not presentation: re-parenting a
section, or moving a paragraph from one cell to the next, leaves reading
order, depth and every node-local hash untouched, and the document hash
must still see it. The pools are included because footnote content and
bibliography entries are authored content; they sit out of the tree for
referencing reasons, not because they are metadata.

**The exclusion list is a principle plus a list**, maintained as the
field set evolves rather than frozen: *exclude resolved presentation
state and nested nodes, hash everything else.*

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
this revision of the specification is `"0.5.0"`. Every change to the node
schema is a PR against this repository (`cnd-sdk`), tagged as a new
release; consumers pin to a tag.

**No compatibility guarantee before 1.0.0** (docs/adr/0027). The format
is not stable yet. Until `cnd_version` 1.0.0, a minor version may break
anything — field names, node shapes, hashes — and design choices are
made on merit, not on how much they preserve. Pinning a release tag is
what keeps a consumer safe in the meantime. No upgrader is promised
between pre-1.0 versions.

**0.5.0** redesigns the node model (docs/proposals/0013): prose becomes
`RichText` with standoff marks (§4.1), the four link families move from
the node base into the texts (docs/adr/0025), every body lives in
`children` (list items, term items, cells and footnotes included),
`numbering` replaces `number` and `counter_label`, `admonition` and
`layout` are new, and `doc` gains `status`, `version` and `extra`. A
`"0.4.0"` CND does not parse as `"0.5.0"`. Every node's and every
document's content hash changes at this bump, under the new hashing
rules (§10, docs/adr/0028). No 0.4 → 0.5 upgrader is shipped: a 0.4 CND
holds none of the new information — no marks, no admonitions, no
checkboxes — so an upgrade would only reshape it. Producers move to 0.5
by emitting it; consumers move by pinning the new tag once their
producer does.

**0.4.0** (history) added the `links` family (§5): a fourth, href-keyed
forward family, additive with an empty default (`links: []`) on every
node. A `"0.3.0"` CND with no `links` field parsed and validated
unchanged under `0.4.0` — nothing existing moved or gained a new required
field. This did not extend to content hashing: `links` was not excluded
from the hashable field set, so `links: []` entered the hash preimage of
every node, and every node's and every document's content hash changed
at that bump — a persisted `"0.3.0"`-era hash, or another
implementation's vectors calibrated against a pre-0.4.0
`fixtures/hashes.json`, is not comparable to one computed under
`0.4.0`. In-process reconciliation (docs/adr/0018) is unaffected by such
changes: it hashes both sides of a comparison with the same running
library, never a persisted value.

A CND is an **immutable build artifact** (docs/adr/0015). It is not
edited in place and carries no version history of its own: versioning a
document is a consumer concern, and relating two builds of the same
document is reconciliation's (docs/adr/0018).

## 12. The declaration (non-normative)

A **declaration** is a source form the builder compiles into a CND
(docs/adr/0019, the declarative door). It serves producers with neither
ids nor pagination to offer — a hand author, a language model, or a
foreign-format producer whose source is unpaginated — while a producer
that holds real pages emits the CND directly (§9's validation is that
door's check).

The declaration is **not part of this standard**. Like rendering (§7) it
is an SDK surface, recorded here so the two are not confused, and it stays
non-normative until it has proven itself; any promotion is a separate ADR.
Its schema is `schema/cnd-declaration.schema.json`, generated from the
same models as the CND schema (docs/adr/0004), and it carries its own
`declaration_version`, versioned independently of `cnd_version`.

A declaration is **the CND minus everything the builder derives**, the
same derived-not-serialized rule (§2) applied to the production side: a
declaration node carries no `id` (the builder mints it; ids are not
durable anyway, docs/adr/0015), no `location` (an unpaginated source has
no page), no `numbering.value` (the resolved running counter value), and
no `heading_path` (derivable from tree position). What it keeps is
authored content — the `label` as the durable identity, the label-keyed
link families of its texts, and every content field. It keeps
`numbering.name` too: unlike the value, that word has an authored half
the builder cannot derive — a heading or equation has no `kind` to derive
one from, and a custom-`kind` figure carries a word only the author
knows. A list item likewise keeps `number`, but as an authored *override*
of the sequential ordinal, not the resolved value. What the declarative
door guarantees is well-formedness, not truth: the builder cannot emit a
malformed CND from a declaration, but a producer can still write an
unbuildable one (a label nothing carries) or a buildable-but-false one,
and that wrong layer is hand-correctable in the declaration before
building.

**Shorthand.** Wherever a `RichText` is expected, a declaration accepts
a plain string, which builds `{"value": "<string>"}` with no marks and
no edges. The full object form stays available to a producer that
computes offsets. An inline markup syntax — a string such as
`See @fig-rate, it is **important**` parsed into value, marks and edges —
would be the practical answer for hand authors and language models; it
is **out of scope** here, and needs a design of its own (syntax,
escaping, link notation).

Because the declaration is authored by hand, an **unknown field is
rejected rather than dropped** — a `capton` typed for `caption` raises
instead of vanishing, so the mistake surfaces exactly where it is meant
to be corrected. (This strictness reaches the declaration's own models:
nodes, list items, term items, cells, footnotes, `numbering` and the top
level. A stray key inside a value object it shares with the CND — a
`RichText`, a mark, a link edge, the document metadata — is not caught.)

**Hyperlinks.** The full object form of a text is the CND's own
`RichText`, so a declaration carries `links` exactly as it carries
`refs`, `cites` and `footnotes`. The gap docs/adr/0024 recorded — the
declarative door had no way to express a hyperlink — is closed by rich
text.

**Numbering.** A counter-bearing node (`heading`, `math`, `figure`) may
author `numbering: {name: "Listing"}`, the word without its value. The
builder's counter engine, when it runs, numbers every heading, figure
and equation in full-walk order (§8) and pairs each value with the
authored word, if any. When the engine does not run, an authored
`numbering` cannot be built — a CND cannot hold a word without a value —
and the builder reports it rather than dropping it. A list item's
`number` stays an authored override of the sequential ordinal.

One constraint the builder inherits from carrying spans: a mark or an
edge's `text_span` indexes into the `value` of its `RichText` (§4.1),
so **the builder must pass every `RichText.value` through unaltered** —
no whitespace collapse, no re-normalization — or every span silently
shifts against the text it points into.

## Out of scope

Chunking strategies, embedding generation, vector storage backends,
and any indexing pipeline built on top of CNDs are consumer
concerns and are **not** part of this standard.
