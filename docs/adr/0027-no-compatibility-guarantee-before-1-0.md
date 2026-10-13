---
title: No compatibility guarantee before format 1.0.0
status: accepted
date: 2026-10-13
tags: [versioning, compatibility, policy]
related: [0015, 0022]
superseded-by: null
---

# ADR 0027 — No compatibility guarantee before 1.0.0

## Status
Accepted.

## Context
The format has moved in minor versions so far: 0.3.0 reworked fields and
made the link families label-keyed, 0.4.0 added a family. Each change
was weighed partly on what it would break, and 0.4.0 was kept additive.
That habit was never written down as a policy, so it read as an implied
promise.

Format 0.5.0 (docs/proposals/0013) redesigns the node model: prose
becomes rich text, the link families move into texts, and containers
hold block nodes. An additive version — keep the plain `text` strings,
add marks beside them — was considered and is cheaper to migrate, but
it leaves the underlying problems standing and needs a locator for
every multi-text node. Choosing it to preserve compatibility would trade
the format's design for continuity with a model that is not yet right.

The format is young. ADR 0022 already treats it as not frozen: Python
stays the reference until the format freezes. Consumers already pin to
a release tag (spec §11), and a CND is an immutable build artifact
(ADR 0015) that a producer rebuilds rather than edits.

## Decision
**Until `cnd_version` 1.0.0, a minor version may break anything** — field
names, node shapes, validation rules, content hashes. Design choices are
made on merit, not on how much they preserve. Consumers pin release
tags, and move to a new version by pinning its tag once their producer
emits it.

The policy is stated in the specification (spec §11) so that it is
explicit, not inferred.

## Consequences
- **No upgrader is promised** between pre-1.0 versions. One may be
  written when it would carry information across; format 0.5.0 ships
  none, because a 0.4 CND holds none of the new information and an
  upgrade would only reshape it.
- Every breaking minor version states what it breaks in spec §11, as
  0.5.0 does.
- Content hashes are not comparable across pre-1.0 versions. In-process
  reconciliation (ADR 0018) is unaffected: it hashes both sides with the
  same library.
- The guarantee a consumer can rely on before 1.0.0 is the pinned tag:
  a given release always reads and writes the same format.
- Reaching 1.0.0 is a separate decision, with its own ADR, and is when a
  compatibility policy for minor versions is written.
