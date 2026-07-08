---
title: Publish cnd-sdk to PyPI
status: proposed
date: 2026-07-08
tags: [packaging, distribution]
related: []
superseded-by: null
---

# ADR 0007 — Publish `cnd-sdk` to PyPI

## Status
Proposed. Not decided, not scheduled — recorded so the idea isn't lost.
`cnd-sdk` is currently consumed only as a git dependency pinned by tag,
which both `uv` and `pip` resolve without any package index involved —
sufficient for its only current consumer.

## Context
`cnd-sdk` is public (Apache-2.0, see ADR 0003) and its only real-world
consumer so far pins it via a git+tag dependency rather than a package
index. A PyPI release isn't needed for anything that exists today.

It would start to matter if `cnd-sdk` gets external consumers outside this
project: `pip install cnd-sdk` is the expected onramp for a public Python
package, and a git+tag dependency is an unusual ask of a third party who
just wants the library. It also unlocks discoverability (PyPI search,
`pip index`) that a GitHub-only repo doesn't have.

## Decision
Not made. If/when `cnd-sdk` gets a second consumer, or the project wants
passive discoverability, revisit this and decide:
- Release process: manual `uv build && uv publish` per tag, or a GitHub
  Actions workflow triggered on tag push (would need a CI pipeline, which
  `cnd-sdk` doesn't have yet — see the repo's own open items).
- Versioning: whether `v0.1.0`'s git tag convention carries over directly
  to PyPI version numbers, or whether PyPI releases start their own
  cadence independent of git tags.
- Package name availability on PyPI (`cnd-sdk` — not checked yet).

## Consequences
- Deferred: no work required now, no risk to the current consumer, which
  doesn't need this to keep working.
- If/when done: one more release artifact to keep in sync with the git tag
  (a PyPI release and a git tag drifting apart is its own failure mode —
  e.g. a git tag moved after a PyPI release was already cut, as already
  happened once with `v0.1.0` locally before it was pushed).
- Makes `cnd-sdk` easier to adopt for anyone outside this project, which is
  only a benefit if that's actually a goal — it isn't yet.
