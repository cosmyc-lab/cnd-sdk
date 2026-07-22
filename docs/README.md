# Documentation index

One line per active document. Update this file in the same commit as any
new or superseded ADR/proposal. See `CLAUDE.md` for the documentation
conventions.

## ADRs (docs/adr/)

| # | Title | Status |
|---|---|---|
| [0001](adr/0001-record-architecture-decisions.md) | Record architecture decisions as ADRs | accepted |
| [0002](adr/0002-canonical-noderef-only.md) | Canonical NodeRef `{id, label}` form only | superseded by 0017 |
| [0003](adr/0003-apache-2-license.md) | Apache-2.0 license | accepted |
| [0004](adr/0004-schema-generated-from-models.md) | JSON Schema generated from the models | accepted |
| [0005](adr/0005-display-as-optional-extra.md) | Display as an optional extra | accepted |
| [0006](adr/0006-scope-manifest-only.md) | Scope: manifest representation only | accepted |
| [0007](adr/0007-publish-to-pypi.md) | Publish `cnd-sdk` to PyPI | proposed |
| [0008](adr/0008-forward-only-cross-reference-edges.md) | Forward-only cross-reference edges | accepted |
| [0009](adr/0009-out-of-tree-referenceable-entities.md) | Out-of-tree referenceable entities; pools and typed link families | proposed |
| [0010](adr/0010-figure-as-wrapper-node.md) | Figure is a wrapper node; content keeps its own node type | proposed |
| [0011](adr/0011-rendering-as-sdk-renderer-hierarchy.md) | Rendering is an SDK renderer hierarchy; nodes are pure data | proposed |
| [0012](adr/0012-location-is-page-only-positions-derived.md) | NodeLocation carries layout facts only (page); positions are SDK-derived | accepted |
| [0013](adr/0013-rename-link-span-to-text-span.md) | Rename the link-family `span` field to `text_span` | accepted |
| [0014](adr/0014-relation-to-doclang.md) | CND's relation to DocLang — coexistence and interoperability, not convergence | proposed |
| [0015](adr/0015-manifests-immutable-ids-not-durable.md) | Manifests are immutable build artifacts; node ids are not durable | proposed |
| [0016](adr/0016-content-hashing.md) | Derived content hashing — canonical serialisation and excluded presentation state | proposed |
| [0017](adr/0017-cross-references-resolve-by-label.md) | Cross-references resolve by target label; drop the id from link families | proposed |
| [0018](adr/0018-reconciliation-reference-algorithm.md) | Reconciliation (diff, id inheritance) is a versioned reference algorithm, not a format guarantee | proposed |

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
| [0008](proposals/0008-cnd-0.3.0-format-changes.md) | CND 0.3.0 format changes — field audit, provenance, and label-keyed links | draft |
