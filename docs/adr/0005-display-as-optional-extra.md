---
title: Keep rich-based display as an optional extra, not a hard dependency
status: accepted
date: 2026-07-07
tags: [dependencies, packaging]
related: []
superseded-by: null
---

# ADR 0005 — Display as an optional extra

## Status
Accepted.

## Context
The SDK's core job is parsing and representing CND manifests — something
every consumer needs. A subset of consumers also want a human-readable
terminal rendering of a manifest (tree view, panels), which pulls in
`rich` and `typing-extensions`. Forcing every consumer of the core parsing
API to install a terminal-rendering library is unnecessary dependency
weight, especially for library/service consumers that never print to a
terminal.

## Decision
The base `cnd` package has exactly one hard dependency: `pydantic`. Display
functionality (`NodeDisplayVisitor` and its theme) ships behind the
`cnd-sdk[display]` extra (`rich`, `typing-extensions`). `cnd.visitors.__init__`
exports only `BaseVisitor` — it does not import `rich` at all.
`NodeDisplayVisitor` must be imported explicitly from
`cnd.visitors.node_display_visitor`, and that import fails with a clear
error if `rich` isn't installed, rather than failing opaquely at package
import time.

## Consequences
- `import cnd` never requires `rich` to be installed.
- Consumers who want display functionality must both install the extra and
  import the display module explicitly — slightly more friction than a
  single flat namespace, in exchange for a minimal core dependency footprint.
- Any future optional feature with its own heavy dependency should follow
  the same pattern: its own extra, its own explicit import path, no import
  from the package's top-level `__init__`.
