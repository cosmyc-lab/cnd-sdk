---
title: CND's relation to DocLang — coexistence and interoperability, not convergence
status: proposed
date: 2026-07-21
tags: [scope, positioning, interoperability, governance]
related: [0006, 0011, 0012]
superseded-by: null
---

# ADR 0014 — CND's relation to DocLang

## Status
Proposed.

## Context
In June 2026 the LF AI & Data Foundation launched the **DocLang**
specification working group under the Joint Development Foundation's
open-governance model, founded by IBM, NVIDIA and Red Hat with ABBYY and
HumanSignal as contributors. DocLang is an Apache-2.0 open standard for
machine-readable documents, with a specification and a Python reference
toolkit at <https://github.com/doclang-project/doclang>.

Technically it is a constrained XML vocabulary designed around LLM
tokenizers: a small controlled token set, an element head/body split that
avoids attribute overhead, bounding boxes on every element, explicit
reading-order threading across columns and page breaks, layer
classification, and OTSL for compact table structure. It is designed as the
emission format of document-extraction toolchains, and the working group's
founders and contributors are the vendors that build them.

This overlaps CND's stated purpose closely enough that the relationship
has to be decided rather than left implicit: both are open document
representations aimed at machine consumption, and a consumer choosing one
will reasonably ask why the other exists. Three options were on the table:
fold CND into DocLang and retire it; treat DocLang as a competitor to
displace; or define the boundary and interoperate.

The distinction that actually separates them is not "AI" versus something
else — it is **what each format takes as its input, and what it optimises
its output for**.

DocLang's subject is a document whose structure had to be **recovered**.
Its input is a rendered artifact — a PDF, a scan, an image — and layout
analysis reconstructs the semantics. Everything characteristic of the
format follows from that: bounding boxes exist because a region's identity
is geometric before it is semantic; threads exist because reading order is
an inference, not a given; layers and handwriting flags exist because the
pipeline must report what kind of mark it saw. Its output is optimised as
**tokens for a model to read** — the serialisation is the prompt.

CND's subject is a document whose structure is **known at the source**. Its
input is a semantic source that a compiler emits from, so reading order is
a tree invariant rather than an annotation (spec §2), geometry is
deliberately absent beyond the page a node begins on (ADR 0012), and
identity is assigned rather than detected. Its output is optimised not as
one document's tokens but as the raw material for **assembling a context
window out of many documents**: typed forward-only link families with
out-of-tree pools so a consumer can traverse from a retrieved node to what
it references, derived positions and heading paths for locating a fragment
in its document, and — decisively — no mandated text form at all, because
how much of a node's text is worth spending budget on is a decision made at
assembly time, not at serialisation time (ADR 0011, spec §7).

Those are different problems. Neither format is a better version of the
other, and the features each lacks are mostly features it has no input to
populate.

## Decision
CND remains a distinct format and standard. DocLang is treated as a
first-class interoperability target, not as a competitor and not as a base
to converge on. Concretely:

1. **No convergence of representation.** CND does not adopt DocLang's
   serialisation, its element vocabulary, or its extraction-oriented model.
   The two formats have different producers and different consumers.

2. **Interoperability in both directions**, via the converters module
   (proposal 0007): `doclang → cnd` as the supported ingestion path for
   documents that only exist as rendered artifacts, and `cnd → doclang` so
   that a context assembled in CND can be emitted in a form tuned for model
   consumption. Both directions are lossy, asymmetrically, and each
   converter documents what it drops. Neither direction is a round-trip and
   the SDK never claims one.

3. **No pursuit of extraction concerns for their own sake.** CND does not
   adopt geometry, layer classification, confidence scores, formatting
   spans or thread mechanics merely because DocLang has them. Each would
   only be considered on a concrete consumer need, individually, by its own
   ADR. In particular, any future adoption of bounding boxes on
   `NodeLocation` — for instance to support highlighting a passage in a
   source artifact — supersedes ADR 0012 and must preserve that decision's
   other half: positions and reading order stay derived from the tree and
   are never reconstructed from geometry.

4. **What CND protects as its differentiators**, and will not trade away
   for alignment: the typed link families and out-of-tree pools with a
   real citation model; reading order as a normative tree invariant;
   rendering as a consumer decision rather than a property of the
   serialisation.

5. **Scope discipline is unchanged.** ADR 0006 still holds: this repository
   defines the CND representation. Interoperating with another
   standard is an SDK facility and creates no conformance obligation on
   CND producers.

## Consequences
- Consumers gain a supported path from extracted documents into CND
  without this repository owning a layout-analysis pipeline, which it has
  no business owning.
- The SDK takes on tracking a specification it does not control. DocLang
  is pre-1.0, where its own versioning policy treats every increment as
  breaking; converters pin a DocLang version explicitly and a version bump
  is expected work, not a surprise.
- The `cnd → doclang` direction has no target for the citation model,
  which is a permanent, documented loss rather than a gap to be closed. If
  that matters enough, the productive move is contributing the missing
  concepts upstream to the DocLang working group, not distorting CND.
- Positioning is now stated rather than implied: CND applies where a
  document's structure is known at the source and the goal is assembling
  context across documents. A consumer whose corpus is entirely scanned
  artifacts and whose goal is faithful single-document representation is
  better served by DocLang directly, and the project should say so.
- If the balance of real-world input shifts decisively toward artifacts
  that only exist as rendered output, this ADR's premise weakens and the
  positioning should be revisited by a superseding ADR rather than eroded
  feature by feature.
