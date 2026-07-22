---
title: Artifact naming and file identity — the CND and the declaration
status: accepted
date: 2026-07-22
tags: [naming, vocabulary, file-format, scope]
related: [0002, 0004, 0006]
superseded-by: null
---

# ADR 0021 — Artifact naming and file identity — the CND and the declaration

## Status
Accepted.

## Context
The standard has, since its earliest drafts, called its terminal artifact
the "manifest" — `CndManifest`, `spec/schema/cnd-manifest.schema.json`,
`validate(manifest)`. ADR 0019's two-door topology and the declarative
source form now in progress (`docs/proposals/`, non-normative by ADR 0006's
scope) introduce a second, distinct artifact upstream of it: a human- or
plugin-authored source document that the builder consumes to produce the
terminal artifact. Both artifacts need names, and the obvious move — keep
"manifest" for the terminal artifact and give the new upstream form some
other word, or the reverse, repoint "manifest" onto the upstream form since
that is the thing an author actually writes — needs to be decided
deliberately, because the word "manifest" carries connotations from other
ecosystems that do not match what either artifact in this format actually
is.

Separately, the terminal artifact's file extension has been `.cnd.json`
by convention, without a considered decision on whether the `.json` suffix
is required or merely inherited from "it's JSON, so name it that way."
JSON has no magic number, so an extension decision here is also a decision
about how content-sniffing and tooling identify the format.

## Decision

### Vocabulary: "manifest" is retired, not repointed
The word "manifest" is retired from the standard's vocabulary entirely. It
is not reused for the new upstream form. The terminal artifact is named
after the format itself — one says "a CND" the way one says "a PDF." The
upstream source form is named **the declaration**.

| Before | After |
|---|---|
| declarative source form | **the declaration**, `.decl.yaml` |
| manifest | **the CND**, `.cnd` |
| `CndManifest` | `Cnd` |
| `src/cnd/core/manifest.py` | `src/cnd/core/cnd.py` |
| `tests/test_manifest.py` | `tests/test_cnd.py` |
| `spec/schema/cnd-manifest.schema.json` | `schema/cnd.schema.json` |
| — (new) | `schema/cnd-declaration.schema.json` |
| `*_manifest.json` (fixtures) | `*.cnd` |
| `validate(manifest)` | `validate(cnd)` |

Pipeline: `cnd declare doc.md` produces `doc.decl.yaml` (the declaration);
`cnd build` consumes it and produces `doc.cnd` (the CND).

Three independent reasons rule out the alternative of repointing "manifest"
at the declaration instead of retiring it:

1. **"Manifest" is a prestige word already spoken for.** In `Cargo.toml`,
   `package.json`, and Kubernetes manifests, "manifest" means *the
   canonical entry point a human writes, that the tool trusts as the
   authority*. The declaration is the opposite of that by construction: it
   is explicitly non-normative (ADR 0006's scope excludes it from the
   standard proper), it never carries `location` or `number` — fields only
   a paginating compiler can resolve — and it is bypassed entirely by
   producers that use the direct door (ADR 0019) to emit a CND straight
   from their own compiler. Naming the declaration "manifest" would hand
   it, by vocabulary alone, a centrality the architecture deliberately
   denies it. A reader who knows what "manifest" means everywhere else
   would draw exactly the wrong conclusion about which artifact is
   authoritative.
2. **Changing what a term refers to is worse than retiring it.** If
   "manifest" kept its name but started meaning the declaration, every
   prior spec passage, ADR, and comment that says "manifest" would silently
   mean something different depending on when it was written — the entire
   existing corpus becomes a reading trap, indistinguishable from current
   text without checking a date. Retiring the word instead leaves old
   material dated but internally coherent: a reader who hits "manifest" in
   an old doc knows unambiguously it means the terminal artifact, because
   that is the only thing the word has ever meant here.
3. **The word already carries the wrong intuition for the declaration
   specifically.** In the OCI/container ecosystem, a "manifest" is a
   *generated* index describing a build's output — the far end of a build
   pipeline, not the input to one. Applying that word to the input
   (the declaration) inverts the one cross-ecosystem intuition "manifest"
   reliably carries.

`docs/adr/0006-scope-manifest-only.md` is the constraint that validates
this choice rather than being broken by it. ADR 0006 is `accepted`, hence
immutable, and its title will say "manifest" forever. That is harmless
specifically *because* retirement, not repointing, is what happened: the
word in ADR 0006's title still means exactly what it meant when written —
the terminal artifact — so no future reader is misled by an old title using
retired vocabulary for its original referent. A repointing decision would
have made ADR 0006's own title actively wrong.

### Extension: bare `.cnd`, not `.cnd.json`
`cnd build` emits `doc.cnd`, not `doc.cnd.json`. Precedent: `.ipynb` is
pure JSON under its own extension, and no editor or tool treats that as a
problem to solve — it is a solved problem via editor association, not
generic JSON handling.

The asymmetry with the declaration's `.decl.yaml` extension is deliberate,
not an oversight to reconcile later. The declaration is written by hand in
general-purpose editors, where the free YAML tooling ecosystem (syntax
highlighting, folding, generic linters) matters most, because that is where
a human is doing the authoring. The CND is produced and consumed by
machines — `cnd build` writes it, `cnd validate`/consumers read it — so its
identity as a distinct artifact matters more than editor ergonomics on a
file a human rarely opens directly. The CND carries the format's name; the
declaration stays humble.

Content identification: JSON has no magic number, so byte-sniffing cannot
identify a `.cnd` file the way a zip signature identifies a `.docx`. The
existing `cnd_version` field at the head of every CND serves as the
signature instead — it already exists for versioning purposes, so this
costs nothing new.

Media type: `application/vnd.cnd+json`. The `+json` structured-syntax
suffix (RFC 6839) tells any intermediary that does not recognize
`vnd.cnd+json` specifically to fall back to treating the payload as
ordinary JSON, rather than failing closed. Noted as a horizon, not a
blocker: `vnd.` is the vendor tree, appropriate for a format without formal
standardization; a standards-tree `application/cnd+json` would require an
IETF registration process, worth pursuing only if and when CND gains real
external adoption.

**`.cnd` is JSON, forever.** This is an explicit commitment, not an
implementation detail that happens to be true today. The predictable
temptation is to make `.cnd` a zip container later, to embed assets
(figures, images) the way `.docx` and `.epub` wrap a zip around their
payload. If that need ever materializes, it gets a **different** extension
(`.cndz` or equivalent) — the byte format behind a published extension
never changes out from under existing consumers.

The CLI tolerates `.cnd.json` as an input filename, as a courtesy to users
or tooling that appended `.json` out of habit; output is always the
canonical bare `.cnd`.

Extension-squatting check: `.cnd` is presently used by two legacy, niche
formats outside this domain (a "condensed embroidery" design format and a
diagramming tool's project files), neither of which has any activity in the
document/knowledge-format space this standard occupies. The file-extension
namespace is unregulated in any case, so this is a courtesy check, not a
compliance requirement.

## Consequences

- **The rename is a real refactor, not a find-replace.** Measured blast
  radius as of this writing: 441 occurrences of "manifest" across the
  repository (tests 250, docs 120, src 44, spec 24, fixtures 3), plus
  `CndManifest` as an identifier × 51, the schema filename, the module
  `src/cnd/core/manifest.py`, the test file `tests/test_manifest.py`, and 5
  fixture files. This is undertaken now, rather than deferred, because
  nothing is published yet (ADR 0007, PyPI distribution, is still
  `proposed`) and it rides a format wave that is already breaking for
  other reasons — the cost of doing it later, against real consumers, is
  materially higher.
- **The bare extension is an ongoing obligation, not a one-time cost.**
  `.ipynb` succeeded as a bare-JSON extension because Jupyter dragged an
  enormous existing ecosystem behind it; a young format is granted nothing
  for free by comparison. Getting `.cnd` recognized requires, as real and
  separate work: editor association (a `files.associations` entry paired
  with a `json.schemas` mapping, which is actually *better* than generic
  JSON association because the editor then validates the open file against
  the CND schema rather than just highlighting it), a GitHub Linguist
  entry, and eventual IANA media type registration. Until each of these is
  done, anyone who opens a `.cnd` file in a generic editor sees
  unhighlighted, unvalidated text — a real, visible cost that the choice
  of bare extension explicitly accepts in exchange for identity.
- ADR 0004 (JSON Schema generated from the models) is unaffected in
  substance: the generation mechanism and its guarantee against drift are
  unchanged. Only the schema's filename and location move, from
  `spec/schema/cnd-manifest.schema.json` to `schema/cnd.schema.json`, with
  a new sibling `schema/cnd-declaration.schema.json` for the declaration's
  own shape.
- The vocabulary change touches prose everywhere the standard is described
  — spec, docs, code comments, error messages — and must be swept
  consistently in the same pass as the code rename, or the two drift and
  produce exactly the reading-trap this ADR's vocabulary argument was meant
  to avoid.
