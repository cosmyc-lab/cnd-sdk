---
title: License the SDK and spec under Apache-2.0
status: accepted
date: 2026-07-07
tags: [license, governance]
related: []
superseded-by: null
---

# ADR 0003 — Apache-2.0 license

## Status
Accepted.

## Context
CND is meant to function as an open, adoptable standard, not just an
open-source library. Adopters need confidence that using the format and
implementing it in their own tools won't expose them to a later patent
claim from a contributor to this project. Permissive licenses commonly
considered were MIT (simpler, no explicit patent terms) and Apache-2.0
(explicit patent grant and termination clause).

## Decision
License this repository (spec, schema, SDK code) under Apache-2.0.

## Consequences
- Contributors implicitly grant a patent license for their contributions,
  which protects downstream adopters implementing the format independently
  of this SDK.
- Slightly more verbose license text than MIT; no practical restriction on
  usage, modification, or redistribution.
- Any future contribution that can't be offered under these terms cannot be
  merged as-is.
