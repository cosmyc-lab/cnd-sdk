# cnd-sdk

Reference Python implementation of **CND** (Context Native Document) — a
manifest format for representing compiled documents as a tree of typed,
cross-referenceable nodes, designed for retrieval and LLM-context pipelines.

This package is the standard itself: the manifest schema, node types, and a
base display/visitor layer. It does not include any indexing, chunking, or
storage logic — those are consumer concerns built on top of this contract.

## Install

```bash
pip install cnd-sdk
# with the optional Rich-based display helpers:
pip install cnd-sdk[display]
```

## Usage

```python
from cnd import CndManifest

manifest = CndManifest.model_validate_json(open("manifest.json").read())

for traverse in manifest.iter():
    print(traverse.ctx.depth, traverse.node.type, traverse.node.to_text())
```

Pretty-printing a manifest tree (requires `cnd-sdk[display]`):

```python
from cnd.visitors.node_display_visitor import NodeDisplayVisitor

NodeDisplayVisitor().visit(manifest)
```

## Spec

The full CND specification lives in [`spec/cnd-spec.md`](spec/cnd-spec.md),
with the JSON Schema at
[`spec/schema/cnd-manifest.schema.json`](spec/schema/cnd-manifest.schema.json)
and shared test fixtures in [`fixtures/`](fixtures/).

## License

Apache-2.0 — see [LICENSE](LICENSE).
