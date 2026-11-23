---
title: Matching v3 — footnotes matched on their content, moved for real moves only
status: accepted
date: 2026-11-23
tags: [identity, reconciliation, diff, sdk, non-normative]
related: [0015, 0018, 0028, 0029]
superseded-by: null
---

# ADR 0032 — Matching v3

## Status
Accepted. Extends ADR 0018, whose decision stands: reconciliation is a
versioned reference algorithm, not part of the format. This ADR
supersedes three clauses:

- in ADR 0018, "Pool entries match on their required label, so pools are
  always exact";
- in ADR 0018, `moved` defined as "matched, hash equal, path differs";
- in ADR 0029, "Footnote content is keyed by its note's label".

Everything else in ADR 0029 carries over unchanged: the walk, the
structural paths of body nodes, the container digest, the five node
passes and their order. The SDK implements this version in
`cnd.reconcile` (`MATCHER_VERSION = "v3"`).

## Context
Two failures were reproduced on matching v2.

**Footnotes paired by label.** Many producers label a footnote with its
display number (`"1"`, `"2"`, …). Inserting a note at the top renumbers
every note after it. With label matching:

- each note was paired with the note that now holds its old number, so
  `reconcile` gave each note its neighbour's id;
- the pool diff still said `unchanged`, because a footnote entry's hash
  covers its fields except `id` and `children` (spec §10, ADR 0028),
  which leaves only the label;
- every note's content was reported as moved, since a content path names
  its note by label.

A footnote label is a key a producer may compute, not a key an author
chose. A citation key, by contrast, is authored.

**`moved` fired for every shifted node.** The structural path contains
the sibling index. Inserting a paragraph at the top changed the path of
every node after it, so each was reported `moved` although nothing about
its place relative to its neighbours changed. A consumer could not tell
the one node that really moved from the hundreds that were pushed down.

## Decision

**Hashing does not change.** The node hash, the pool entry hash and the
document hash stay as spec §10 and ADR 0028 define them. The footnote key
below is a matching key only, like ADR 0029's container digest: never
serialised, never a content hash.

**A footnote's matching key is its content.** The key is a digest of:

- the note's own fields except `id` and `label`;
- then, for each content node in order, its node hash and the digest of
  its descendants' hashes.

A bibliography entry's key stays its pool entry hash.

**The footnote pool is matched first, in three passes.** Each pass sees
only what the previous ones left:

1. `content` with the same label: the note is untouched;
2. `content` alone, earliest in pool order first: the note was
   renumbered, relabelled, or moved in the pool;
3. `label` alone: the note's content was edited.

The label is the tie-breaker among notes with the same content. It works
through the split between passes 1 and 2: a note keeps the identical note
that had its label before any other note can take it. Ties left after
that break by pool order, so the result is deterministic. A pair reports
which pool pass made it (`matched_by: "content"` or `"label"`).

The bibliography keeps label matching: a citation key is authored.

**Footnote content is placed by the pool matching.** The node passes run
after the pool is matched. On the new side, the content path of a matched
note names the old note it was paired with:
`("footnotes", <old label>, "children", 0)`. A renumbered note's content
therefore sits in the same slot as before, and pairs `hash+path` when it
did not change. The content of a new note that matched nothing goes
under `("new-footnotes", <label>, …)`. No old node occupies that slot, so
the new note's content never pairs by slot with the content of the old
note that happened to have its label.

**Pool status.** A matched entry is `unchanged` when its matching key is
equal, and `changed` otherwise. A renumbered note with the same content
is unchanged: a display number is presentation state, like `numbering`.
A note whose content was edited is changed, and its edited node is
reported changed too.

**`moved`, defined.** A matched pair whose node hash differs is
`changed`, as before. A pair whose hash is equal is `moved` when one of
the following holds, and `unchanged` otherwise.

- **Re-parented.** A node's parent is the node whose slot holds it, the
  body for a top-level node, or its note for footnote content. The node
  is re-parented when its new parent is not the counterpart of its old
  parent. An unmatched parent is nobody's counterpart. The counterpart of
  a note is the note the pool matching paired it with. A node that
  changed item or cell is also re-parented when its parent's own hash is
  equal: that parent kept its items or cells, so they line up one to one.
  When the parent's hash differs, its items or cells were added or
  removed and their indices do not line up. Order alone then decides.
- **Reordered.** Take the matched siblings that share a parent on both
  sides, in new order. Their old positions are the item or cell index,
  then the child index. Keep a longest subsequence whose old positions
  increase; every sibling outside it is reordered. When several longest
  subsequences exist, the one that keeps the earliest siblings in new
  order wins. So when two siblings swap, the later one in new order is
  reported moved. The SDK computes this in O(n log n) per parent.

A node only shifted by an insertion or a removal before it is neither
re-parented nor reordered, so it is `unchanged`.

**Id inheritance.** With `only_exact=True`, `reconcile` inherits a pool
entry's id only when its label agrees. Pairing identical notes on content
is a heuristic, and the label is the only exact key. Without the flag,
every pool pair is inherited.

**Vectors.** `fixtures/matching.json` carries `"matcher_version": "v3"`.
Cases 01 to 11 are emitted again under v3 by the repository script. Their
input documents do not change; some statuses move from `moved` to
`unchanged`, and the pool vectors of 07 and 10 now record a `changed`
note. The footnote vectors also record `old_label` and `matched_by`. Five
cases are added:

- 12: a note inserted at the top;
- 13: two numbered notes swapped;
- 14: two identical notes;
- 15: insertions are not moves;
- 16: real moves, a re-parented node and a swap.

No v2 vector file is kept. The format is pre-1.0 (ADR 0027), and this ADR
records the change. As under ADR 0018, reproducing the vectors proves an
implementation runs v3; it is not a conformance requirement on the
format.

## Consequences
- **Renumbering is harmless.** A producer that numbers its notes gets id
  continuity for every note whose content survived, and a diff that
  reports only the inserted note.
- **`moved` is actionable.** It names the nodes whose place changed, not
  every node after an insertion. A consumer that needs the old definition can
  still compare `old.path` and `new.path` on any matched pair.
- **The pool diff says more.** A footnote whose content was edited is
  `changed` in the pool diff, where v2 reported the entry `unchanged` and
  only its paragraph `changed`.
- **Known limits.**
  - A note both renumbered and edited misses the content passes and pairs
    on its label, which may now name another note. This is ADR 0018's
    combined case, for footnotes.
  - Among identical notes whose labels all changed, pool order decides,
    which can swap their ids. Their content is identical, so nothing a
    reader sees differs.
  - When a list or table gained or lost items or cells, moving a node to
    a neighbouring item or cell without changing its order among its
    siblings is not reported as moved.
- **Breaking SDK surface (pre-1.0).** `PoolMatching.matches` holds
  `PoolMatch(old, new, matched_by)` objects instead of pairs. `PoolEntry`
  gains `content` and `PoolChange` gains `matched_by`. On the new side,
  the path of a footnote's content names the matched old note.
- **Versioning.** Any later change to the walk, the keys, the passes or
  the `moved` rule is matching v4: a new `MATCHER_VERSION`, new vectors
  and a new ADR.
