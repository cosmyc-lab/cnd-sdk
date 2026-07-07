---
title: Scope the standard to the manifest representation only
status: accepted
date: 2026-07-07
tags: [scope, governance]
related: [0002]
superseded-by: null
---

# ADR 0006 — Scope: manifest representation only

## Status
Accepted.

## Context
A document-processing pipeline built around CND typically also needs
chunking, embedding, and storage/retrieval of those chunks. It would be
possible to fold opinions about how to chunk a manifest, which embedding
model to use, or how to index the result into this standard. Doing so
would tie the standard's evolution to implementation choices that are
legitimately different across consumers, and would make CND harder to
adopt by anyone whose downstream pipeline looks different.

## Decision
CND defines only the manifest representation: the node tree, node types,
`NodeRef` cross-references, and `to_text()` / visitor mechanisms for
walking and rendering that tree. Chunking strategy, embedding, storage, and
retrieval are explicitly out of scope — they are consumer concerns, built
on top of the manifest, not part of the format.

## Consequences
- The SDK's dependency footprint stays small (see ADR 0005) because it
  never needs an embedding or vector-store client.
- Consumers are free to implement radically different downstream pipelines
  on the same manifest without any of those choices becoming a
  compatibility question for the standard itself.
- Any future proposal that would require the SDK to depend on a specific
  chunking or storage technology should be rejected or redirected to a
  consumer-side library instead of this one.
