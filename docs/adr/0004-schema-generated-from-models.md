---
title: Generate the JSON Schema from the Pydantic models, guard against divergence
status: accepted
date: 2026-07-07
tags: [schema, testing, source-of-truth]
related: [0001]
superseded-by: null
---

# ADR 0004 — JSON Schema generated from the models

## Status
Accepted.

## Context
A format standard needs a schema consumers can validate against
independently of any particular language implementation. Hand-maintaining
a JSON Schema alongside the Pydantic models that define the same shapes in
Python risks silent divergence: a model change that isn't mirrored in the
schema produces a standard document that lies about what the reference
implementation actually accepts.

## Decision
`spec/schema/cnd-manifest.schema.json` is generated from
`CndManifest.model_json_schema()` and committed as the source of truth for
non-Python consumers. A regression test
(`tests/test_schema.py::test_schema_matches_generated_model`) regenerates
the schema from the current models and fails the build if the committed
file differs.

## Consequences
- The schema can never silently drift from the reference implementation —
  any model change that affects the public shape must regenerate and
  re-commit the schema in the same PR, or CI fails.
- Contributors must run the generation step locally instead of hand-editing
  the schema file.
- Schema comments/descriptions are whatever `model_json_schema()` produces
  from field docstrings — schema readability is bounded by model
  docstring quality.
