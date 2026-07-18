# Documentation index

One line per active document. Update this file in the same commit as any
new or superseded ADR/proposal. See `CLAUDE.md` for the documentation
conventions.

## ADRs (docs/adr/)

| # | Title | Status |
|---|---|---|
| [0001](adr/0001-record-architecture-decisions.md) | Record architecture decisions as ADRs | accepted |
| [0002](adr/0002-canonical-noderef-only.md) | Canonical NodeRef `{id, label}` form only | accepted |
| [0003](adr/0003-apache-2-license.md) | Apache-2.0 license | accepted |
| [0004](adr/0004-schema-generated-from-models.md) | JSON Schema generated from the models | accepted |
| [0005](adr/0005-display-as-optional-extra.md) | Display as an optional extra | accepted |
| [0006](adr/0006-scope-manifest-only.md) | Scope: manifest representation only | accepted |
| [0007](adr/0007-publish-to-pypi.md) | Publish `cnd-sdk` to PyPI | proposed |
| [0008](adr/0008-forward-only-cross-reference-edges.md) | Forward-only cross-reference edges | proposed |
| [0009](adr/0009-out-of-tree-referenceable-entities.md) | Out-of-tree referenceable entities; pools and typed link families | proposed |
| [0010](adr/0010-figure-as-wrapper-node.md) | Figure is a wrapper node; content keeps its own node type | proposed |
| [0011](adr/0011-rendering-as-sdk-renderer-hierarchy.md) | Rendering is an SDK renderer hierarchy; nodes are pure data | proposed |

## Proposals (docs/proposals/)

| # | Title | Status |
|---|---|---|
| [0001](proposals/0001-configurable-table-figure-rendering.md) | Configurable table/figure rendering in `to_text()` | implemented, superseded by 0006 |
| [0002](proposals/0002-table-content-kind-auto-classification.md) | Automatic classification for `TableNode.content_kind` | draft |
| [0003](proposals/0003-cross-document-references.md) | Cross-document references | draft |
| [0004](proposals/0004-terms-footnote-citation-bibliography-nodes.md) | Terms nodes; footnote and bibliography pools; typed citation edges | implemented |
| [0005](proposals/0005-figure-wrapper-image-node.md) | Figure as a wrapper node; new `ImageNode`; `TableNode` loses its caption | implemented |
| [0006](proposals/0006-multi-format-rendering.md) | Multi-format rendering via renderer classes; remove `to_text()` | implemented |
| [0007](proposals/0007-manifest-converters.md) | Manifest-level converters to complete document artifacts | draft |
