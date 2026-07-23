# cnd-sdk

Reference Python implementation of **CND** (Context Native Document) — a
format for representing compiled documents as a tree of typed,
cross-referenceable nodes, designed for retrieval and LLM-context pipelines.

This package is the standard itself: the CND schema, node types, and a
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
from cnd import Cnd, MarkdownRenderer

cnd = Cnd.model_validate_json(open("doc.cnd").read())
renderer = MarkdownRenderer()

for traverse in cnd.iter():
    print(traverse.ctx.depth, traverse.node.type, renderer.render(traverse.node))
```

Pretty-printing a CND tree (requires `cnd-sdk[display]`):

```python
from cnd.visitors.node_display_visitor import NodeDisplayVisitor

NodeDisplayVisitor().visit(cnd)
```

## Conformance CLI

The `cnd` command is the executable oracle of the fixture corpus — the tool
to reach for when implementing CND in another language and asking "does my
implementation agree?".

```bash
cnd validate doc.cnd          # the invariants JSON Schema cannot express
cnd hash doc.cnd --nodes      # the reference content hashes
cnd inspect doc.cnd           # readable tree trace (needs [display])
```

Exit code `0` means conformant, `1` means it is not (or the file did not
parse). `--json` on `validate`/`hash` gives machine-readable output, since
comparing two implementations is a diff rather than a read.

**This is three of the five conformance verbs**
[`docs/adr/0020`](docs/adr/0020-repository-as-conformance-hub.md) specifies.
`build` (from a declaration) and `reconcile`/`diff` are conformance verbs
too, and are still missing from the CLI: `build` because the declaration
does not exist yet, `diff` because the algorithm
([`docs/adr/0018`](docs/adr/0018-reconciliation-reference-algorithm.md))
only just landed as a library — see `cnd.reconcile` below — and id
inheritance is not implemented at all. Agreeing with the three above is
necessary for conformance, not yet sufficient — and the corpus matches,
carrying two of the four vector kinds the same ADR requires.

## Reconciliation

A CND is an immutable build artifact and its node ids are not durable, so
"is this the same node as last build?" is answered after the fact, by
matching two CNDs
([`docs/adr/0018`](docs/adr/0018-reconciliation-reference-algorithm.md)):

```python
from cnd.reconcile import diff

report = diff(previous, current)
[change.new.node.text for change in report.changed]
```

The matching is a **versioned reference algorithm, not part of the
format** — exact for labelled nodes, best-effort for the rest.

Turning a foreign format into a CND (`cnd declare`) is a different kind of
absence: it belongs with the producers permanently, since bundling it would
make the hub depend on a satellite.

## Spec

The full CND specification lives in [`spec/cnd-spec.md`](spec/cnd-spec.md),
with the JSON Schema at
[`schema/cnd.schema.json`](schema/cnd.schema.json)
and shared test fixtures in [`fixtures/`](fixtures/).

## License

Apache-2.0 — see [LICENSE](LICENSE).
