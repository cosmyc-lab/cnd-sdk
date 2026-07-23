---
name: docs
description: Create or update this repo's documentation using its ADR / proposal conventions. Use when asked to write an ADR, record an architecture decision, propose a spec change or RFC for the CND format, or when a PR introduces a decision that must be documented. Enforces numbering, YAML front-matter, and ADR immutability.
---

# cnd-sdk documentation (ADR / proposal)

Authoritative index: `docs/README.md` — update it in the SAME commit as any
doc you create or change. All docs in English.

## Common rules
1. Every file starts with YAML front-matter: `title`, `status`, `date`
   (YYYY-MM-DD, today), `tags` (list), `related` (list of ADR numbers, may
   be empty), `superseded-by` (`null` unless set).
2. Keep files small and targeted; link to code (path + symbol) rather than
   pasting code bodies into docs.
3. After writing, add or update the one-line entry in `docs/README.md`.

## ADR — `docs/adr/NNNN-kebab-title.md`
Before writing:
- Determine the next number: list `docs/adr/`, take `max(NNNN) + 1`,
  zero-padded to 4 digits. Never reuse a number or leave a gap.
- Check no existing ADR already covers the decision (grep title keywords
  across `docs/adr/`).

Template: copy `templates/adr.md`. Sections: Status / Context / Decision /
Consequences (Nygard format). `status` ∈ `proposed | accepted | deprecated
| superseded`.

**Immutability**: an `accepted` ADR is never edited except for exactly two
fields — flipping `status` to `deprecated`/`superseded` and filling
`superseded-by: NNNN`. To change a decision, write a NEW ADR whose Context
section cites the old one by number, then update the old ADR's two fields
and `docs/README.md`. If asked to edit an accepted ADR's substance, refuse
and propose a superseding ADR instead.

## Proposal — `docs/proposals/kebab-slug.md`
A proposal is an RFC for a change to the CND format itself (schema, node
types, semantics). `status` ∈ `draft | approved | implemented`. When a
proposal is implemented, the same PR must:
- update `spec/cnd-spec.md`,
- regenerate `schema/cnd.schema.json` from the models,
- flip the proposal's `status` to `implemented`,
so that `tests/test_schema.py` keeps passing and the spec, schema, and code
never drift apart.

Template: copy `templates/proposal.md`.

## Validation checklist before finishing
- [ ] Front-matter parses (valid YAML, all required keys present).
- [ ] ADR number is sequential; filename matches the title's slug.
- [ ] `docs/README.md` updated.
- [ ] No duplication of content already in `spec/cnd-spec.md` or in code
      docstrings — link to it instead.
