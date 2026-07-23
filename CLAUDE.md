# cnd-sdk

Reference Python implementation and specification of CND (Context Native
Document): a format for representing a compiled document as a tree
of typed nodes, with stable cross-references between nodes.

## Layout
| Path | What |
|---|---|
| spec/cnd-spec.md | THE format specification (prose) |
| schema/cnd.schema.json | JSON Schema, generated from the Pydantic models |
| src/cnd/ | the `cnd` package: the CND model, node types, NodeRef, renderers, outbound converters, base visitor, optional Rich display |
| fixtures/ | canonical example CNDs used by the test suite |
| tests/ | pytest suite, includes a schema-regression test |

## Documentation — source of truth
- docs/README.md — index of all active ADRs and proposals (read this first)
- docs/adr/ — architecture decisions. IMMUTABLE once accepted: to change a
  decision, write a new ADR that supersedes the old one; never edit an
  accepted ADR's substance.
- docs/proposals/ — RFCs for spec changes (`status: draft|approved|implemented`).
  An implemented proposal is matched by a diff to spec/cnd-spec.md, the
  schema, and the models in the same PR.
- Use the `docs` skill to create any ADR or proposal — it handles numbering,
  front-matter, and the immutability rule.

## Invariants
- The JSON Schema is generated from `Cnd.model_json_schema()` and
  committed as source of truth; `tests/test_schema.py` fails the build if it
  diverges from the models — regenerate it, never hand-edit the schema file.
- `NodeRef` has exactly one canonical shape: `{"id": <uuid>, "label": <string|null>}`.
  No legacy shims (bare UUID, tuple form) — see docs/adr/0002.
- Hard dependency: `pydantic` only. `rich` is an optional `cnd-sdk[display]` extra;
  `cnd.visitors.__init__` must not import it — `NodeDisplayVisitor` is
  imported explicitly from `cnd.visitors.node_display_visitor` and fails
  cleanly if `rich` isn't installed.

## Commands
```
uv sync
uv run pytest -q
```
