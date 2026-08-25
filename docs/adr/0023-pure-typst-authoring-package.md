---
title: Pure-Typst authoring package for CND metadata
status: accepted
date: 2026-08-25
tags: [typst, authoring, packaging, toolchain]
related: []
superseded-by: null
---

# ADR 0023 — Pure-Typst authoring package for CND metadata

## Status
Accepted.

## Context
Authoring a Typst document that carries CND metadata previously required a
custom compiler build: a fork that injects a `cnd` module into the global
scope before compilation. That couples authoring to one toolchain build —
an author cannot open the document in a stock Typst install, typst.app,
tinymist, or any other unmodified compiler and get working `cnd.*` calls;
the fork is a hard prerequisite just to write the tags.

Nothing about the mechanism actually requires compiler-level injection.
State identity in Typst is key-only: `state("cnd.metadata", (:))` is
matched by its string key wherever it's declared, and a reader that also
selects `"cnd.metadata"` sees the same updates regardless of which file
defined the `state(..)` call that produced them. A state declared in a
plain `.typ` file consumed via `#import` is therefore indistinguishable, to
a reader, from one injected by a modified compiler.

One constraint does follow from how emitters record source snippets for
tables: an emitter that captures a table's snippet by following
`table.span()` to the file the span points into needs that span to remain
at the document's own call site. If a wrapper function received the raw
table arguments and called `std.table(..)` internally, the resulting
content's span would point into the wrapper's own file — the package's
source — rather than into the author's document, and the emitter would
record the wrong snippet. `cnd.table` must therefore take already-built
content and only annotate it, never construct the table itself.

## Decision
Ship an official pure-Typst authoring package: `src/cnd/typst/cnd.typ`,
readable from the installed wheel via
`importlib.resources.files("cnd") / "typst" / "cnd.typ"`. No `pyproject.toml`
change is needed — hatchling's `packages = ["src/cnd"]` already sweeps
non-Python files under the package directory.

The package exports its names as top-level module members, not as a
dictionary. A whole-file import — `#import "/cnd.typ"` — binds the file as a
module named `cnd` (by file stem), and members of a module are directly
callable: `#cnd.table(..)`, `#cnd.metadata.update(..)`, exactly like a
function reached through the compiler-injected module this package
replaces.

A dict export (`#let cnd = (metadata: ..., table: ...)`) was tried first and
rejected: in stock Typst, a function value stored in a dictionary field
cannot be called directly through field access — `#cnd.table(..)` raises
"cannot directly call dictionary keys as functions," forcing the caller to
write the parenthesized form `#(cnd.table)(..)` instead. That breaks
call-syntax parity with the injected module `cnd.table(..)` was meant to be
a drop-in replacement for, so the dict shape does not satisfy this ADR's own
goal. The module export has no such restriction — a module's function
members are ordinary bindings, callable exactly like top-level functions.

The two exported names:

- `cnd.metadata` — a `state("cnd.metadata", (:))`, the same state key CND
  emitters already read.
- `cnd.table(body, content_kind: none)` — wraps already-built content and
  brackets it with a `content_kind` hint (`"data"` | `"content"`) in the
  `cnd.metadata` state, then removes the hint again once past the wrapped
  content.

Because it takes content rather than constructing it, the authoring
convention is `#cnd.table(table(columns: 2, [A], [B]), content_kind:
"data")` — the author still calls `table(..)` themselves, and passes the
result in — rather than `#cnd.table(content_kind: "data", columns: 2, ..)`.
This keeps the table's span at the document's own call site, which is what
the emitter's snippet-capture logic depends on. (This is also why the
package's own top-level function is itself named `table` — it shadows
Typst's built-in `table` only inside a scope that imports it by name, which
is exactly why consumers are told to import the whole file rather than
destructure individual members.)

Consumers map or copy the file into a project (e.g. as a root file
`/cnd.typ`) and opt in per document with `#import "/cnd.typ"` (the whole
file, not `#import "/cnd.typ": table, metadata` — destructuring `table`
would shadow Typst's own built-in `table` in the importing scope). This
works on any stock Typst toolchain — the CLI, typst.app, tinymist, or any
other compiler — because the only contract is the `cnd.metadata` state key
itself, not a modified compiler binary. Compiler-side injection of a `cnd`
module is deprecated in favor of this package: it remains a valid *shortcut*
implementation for a toolchain that wants one, but it is no longer the way
a document declares its CND metadata contract.

## Consequences
- Authoring a CND-tagged Typst document no longer requires a custom
  compiler build; a stock Typst toolchain, a plain `#import`, and this file
  are sufficient.
- The authoring convention for tables changes: `content_kind` moves from an
  argument alongside the table's own arguments to a wrapper call around
  already-built content. Any existing documents or examples that used the
  fork module's `#cnd.table(content_kind: .., ..)` shape need updating to
  `#cnd.table(table(..), content_kind: ..)`.
- The package has exactly one distribution path (the wheel's
  `src/cnd/typst/cnd.typ`) and no publishing step of its own; a project
  brings it in by copying or mapping the file, not by installing a Typst
  package from a registry. A registry package is a possible future
  evolution, not part of this decision.
- The `cnd.metadata` state key is now documented as a public contract that
  any pure-Typst code can declare, not just the fork module — future
  changes to the key's shape are a compatibility concern for every producer
  that reads it, not just the fork.
- The package's exported names are module-level bindings, not dict entries;
  a future contributor adding a new export must add it as a top-level
  `#let` in `cnd.typ`, not by extending a dict — the dict shape is rejected
  by this ADR precisely because it breaks direct call syntax.
