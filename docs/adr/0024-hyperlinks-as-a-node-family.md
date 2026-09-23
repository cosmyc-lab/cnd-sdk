---
title: Hyperlinks are a fourth forward family, href-keyed and outside label resolution
status: accepted
date: 2026-09-20
tags: [schema, refs, labels, hyperlinks]
related: [0008, 0013, 0017]
superseded-by: null
---

# ADR 0024 — Hyperlinks are a fourth forward family, href-keyed and outside label resolution

## Status
Accepted.

## Context
A document can carry a hyperlink: a marker in a paragraph's text whose
target is a URL rather than another node, a bibliography entry, or a
footnote. Today's three link families (`refs`, `cites`, `footnotes`,
spec §5) have nowhere to put this. Forcing it into one of them would
break the guarantee each of those families exists to make.

`refs`, `cites`, and `footnotes` are **resolved-pointer contracts**: an
edge names a target by `label`, and a conformant CND guarantees that
label is carried by something in the CND, in the family's own domain
(docs/adr/0017, spec §5 "Resolution (normative)"). A hyperlink cannot
satisfy that. Its target is a URL — `https:`, `doi:`, an application
scheme — which is outside the CND by definition. There is no label to
resolve, and no domain inside the document for the target to sit in.

The idea of widening `refs` to reach outside a single document was
already on record as an open question, unrelated to hyperlinks:
docs/proposals/0003 sketches a `refs_external`-shaped edge that would
carry a target document identifier alongside a label, be emitted
**unresolved**, and wait for a separate corpus-level pass to promote it
to a real pointer or leave it dangling. That proposal stays open and
undecided — it is about resolving a label across a corpus of documents,
a different and harder problem than carrying a URL. But its shape is
useful here as the alternative this decision explicitly rejects: any
family whose edges are allowed to resolve to nothing is not the
`refs`/`cites`/`footnotes` contract restated, it is a new and weaker one
wearing the same name.

## Decision
Add a fourth family, `links`, keyed by `href` instead of `label`:
`LinkRef { href: string, text_span?: [start, end) }`. It lives beside
the other three on every node (`NodeBase.links`, default `[]`), shares
the `text_span` standoff-position contract (docs/adr/0013), and nothing
else.

`links` is deliberately **not** a fourth label-keyed family and is not
folded into the existing three:

1. **It carries no label and resolves nowhere in the CND.** The
   normative resolution rule (spec §5) is scoped to the three
   label-keyed families; `links` sits outside it by name, not by a
   silent exception. A `links` edge naming a URL the CND knows nothing
   about is not a violation — it is the only case there is, since the
   CND was never going to know about it.
2. **`href` admits any scheme.** The format does not parse or validate
   it. A consumer that wants to fetch, classify, or resolve the target
   is free to; the format's job stops at carrying the string faithfully.
3. **No dangling state.** Because `links` never claims to resolve, it
   cannot fail to resolve either. A URL is a URL whether or not anything
   ever dereferences it — there is no "resolved" vs. "unresolved" `links`
   edge the way there is a resolved vs. dangling `refs` edge.

## Alternatives considered
**Widen `refs` with an external/document qualifier.** Add an optional
field to `NodeRef` (a target document id, a URL, or both) so one family
covers in-document and out-of-document targets alike. Rejected: this is
exactly the shape docs/proposals/0003 already sketches for cross-document
label resolution, and adopting it here would import that proposal's open
problem — an edge that may or may not resolve, depending on facts outside
the single CND — into a family whose entire contract, today, is that
every edge resolves. `refs` readers that trust "every ref resolves"
would silently lose that guarantee the day a hyperlink or an
unresolved cross-document pointer rode in on the same field. A hyperlink
and a possibly-dangling cross-document reference may end up looking
similar in a future revision, but neither is today's `refs`, and neither
should be introduced by weakening it.

**Model a hyperlink as a zero-argument citation or footnote.** `cites`
and `footnotes` already resolve into a pool the CND owns
(`bibliography`, `footnotes`). Reusing either would mean inventing a
pool entry for something that is not bibliographic and is not a footnote
— a URL — purely to keep the label-keyed shape. Rejected as a worse fit
than a fourth, differently-keyed family: the pool entry would exist only
to be pointed at once, by exactly one edge, which is not what a pool is
for.

**Leave hyperlinks unmodeled (prose only).** Consistent with keeping the
format minimal, but a hyperlink is exactly the kind of forward edge the
other three families exist to make traversable rather than left as
unstructured text — a consumer that wants "every outbound link in this
paragraph" should not have to regex the rendered text for one family
while reading a typed list for the other three.

## Consequences
- **Additive, not breaking.** `links` defaults to `[]`; a CND with no
  `links` field parses and validates unchanged. This lands as `cnd_version`
  `0.4.0` (spec §11), a minor bump under the format's semver-zero
  discipline.
- **The resolution rule keeps its strength for the three families it
  already covers.** Scoping it explicitly to `refs`/`cites`/`footnotes`
  in the same edit that introduces `links` means the normative rule now
  says in words what was previously true only by the absence of a fourth
  family: it does not, and must not, reach a family that cannot satisfy
  it.
- **`_check_link_domains` needed no new exclusion logic.** It already
  enumerates the three families it checks by name rather than walking
  every edge field on a node generically, so `links` was never in its
  path. The validator's shape already matched the rule this ADR makes
  explicit in prose.
- **Content hashing includes `links` by the same rule as the other three.**
  A hyperlink is authored content, not resolved presentation state
  (docs/adr/0016's exclusion list is unchanged), so it is not added to
  the hash exclusion set.
- **The declaration schema is untouched.** A hand-authored or
  model-authored declaration cannot yet express a hyperlink; the
  declarative door only carries the label-keyed families today
  (spec §12). That gap is real and is left as a follow-up, not resolved
  here.
- **docs/proposals/0003 is unchanged by this decision.** It still records
  an open, harder problem — resolving a label across a corpus of
  documents — that `links` does not attempt and does not close.
