---
title: Record architecture decisions as ADRs
status: accepted
date: 2026-07-07
tags: [meta, process]
related: []
superseded-by: null
---

# ADR 0001 — Record architecture decisions as ADRs

## Status
Accepted.

## Context
Design decisions about the CND format and this SDK were being made in
conversation and code review with no durable record of *why*. A contributor
(human or agent) reading the code later has no way to tell whether a given
shape is deliberate or accidental, or whether an alternative was already
considered and rejected.

## Decision
Record every non-trivial architecture or format decision as an ADR in
`docs/adr/`, using the Michael Nygard format (Status / Context / Decision /
Consequences), with YAML front-matter (`title`, `status`, `date`, `tags`,
`related`, `superseded-by`). ADRs are numbered sequentially and are
immutable once `accepted`: changing a decision means writing a new ADR that
supersedes the old one, not editing the old one's substance. The only
fields an accepted ADR may still receive are `status` (flipped to
`superseded`) and `superseded-by`.

## Consequences
- `docs/README.md` must be updated in the same commit as any new ADR.
- A decision with no ADR should be treated as informal/reversible; anything
  load-bearing for the format or the public API gets one.
- This adds a small amount of process overhead per decision, in exchange
  for a record that survives contributor turnover and long context gaps.
