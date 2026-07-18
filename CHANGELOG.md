# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html)
(semver-zero discipline: while on `0.y.z`, breaking changes and additions bump
the minor version, fixes bump the patch version).

## [0.3.0] - 2026-07-18

SDK release 0.3.0 implements CND **format 0.2.0** (`cnd_version: "0.2.0"`).

### Changed (breaking)

- **Forward-only cross-references** (docs/adr/0008): `refs_from` is removed
  from every node; `refs_to` is renamed to `refs`. The reverse index is now
  derived, never serialized — use the new `CndManifest.incoming(node_id)`,
  built lazily and cached on the instance.
- **`to_text()` removed from every node**, along with
  `cnd.core.node_text.render_node_text()`. Nodes are pure data; rendering
  moved to a renderer hierarchy in `cnd.core.render`: the `NodeRenderer`
  ABC (one method per node type plus a concrete `render()` dispatch) and
  `MarkdownRenderer`, whose table/figure verbosity is constructor
  configuration (`tables=` / `figures=`: `"placeholder"` | `"inline"` |
  `"auto"`). "Raw" is not a renderer — it is Pydantic's own
  `repr()`/`model_dump_json()`.
- **`FigureNode` is now a wrapper node**: it gains `children` and loses
  `path` and `alt` (moved to the new `ImageNode`). `kind` remains an open
  string counter/label selector, never a content discriminator. Nested
  figures (subfigures) are allowed.
- **`TableNode` loses `caption` and `fig_number`** — they live on the
  wrapping `FigureNode`. A bare table is a `TableNode` with no wrapper; no
  deprecated fields are left behind.
- **Traversal descends into every children-bearing node** (`heading` and
  now `figure`); prune with a `stop_predicate` to treat figures as atomic.
- `cnd.core.node_text` is now internal plumbing for renderers:
  `figure_node_placeholder` removed, `table_node_placeholder` and
  `render_table_markdown` no longer emit caption/number (the wrapper owns
  them), `_header_row_text` renamed to `header_row_text`.
- `NodeDisplayVisitor` consumes a `NodeRenderer` for text previews
  (`renderer=` parameter), displays `refs`/`cites`/`footnotes` (with spans)
  instead of `refs_to`/`refs_from`, and handles the new node types.

### Added

- **Link families on every node**: `refs: list[NodeRef]`,
  `cites: list[CiteRef]` (resolving in the bibliography pool, with `form`
  and `supplement`), `footnotes: list[FootnoteRef]` (resolving in the
  footnotes pool). All share the `{id, label, span?}` skeleton; `span` is
  an optional `[start, end)` pair of Unicode code-point offsets into the
  containing node's rendered text (additive to the canonical `NodeRef`
  shape — docs/adr/0002 intact).
- **Top-level pools on the manifest**: `bibliography: list[BibEntry]`
  (rendered string + curated typed subset + lossless `raw` JSON
  passthrough) and `footnotes: list[Footnote]` (flat text). Ids are
  globally unique across nodes and pool entries.
- **New node types**: `TermsNode` (`type: "terms"`, definition list of
  `TermItem` pairs) and `ImageNode` (`type: "image"`, leaf image with
  `path`/`alt`).
- New fixture `fixtures/rich_content_manifest.json` exercising terms,
  figure-wrapping-code, images, citations + bibliography, and footnotes.

### Format

- `cnd_version` bumped `0.1.0` → `0.2.0`; spec §5 rewritten (forward-only
  edges, link families, standoff spans, global id uniqueness), new
  out-of-tree entities section, node-type updates (figure wrapper, image,
  terms, table without caption), rendering documented as SDK non-normative.

## [0.2.0] - 2026-07-16

- Previous release: manifest models, `to_text()` rendering,
  `content_kind`-aware table rendering, display visitor, JSON Schema
  generation and fixtures.
