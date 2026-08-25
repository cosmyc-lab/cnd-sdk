// CND authoring helpers — the official pure-Typst package for tagging
// documents with CND metadata. Works on any stock Typst toolchain: the only
// contract is the "cnd.metadata" state key, which CND emitters read
// (see spec/cnd-spec.md and ADR 0023).

#let _metadata = state("cnd.metadata", (:))

// Wraps already-built content (typically a `table(..)` call) and brackets it
// with a `content_kind` hint ("data" | "content") in the cnd.metadata state.
// Pass the content in — don't let this function build it: the source snippet
// emitters record for a table comes from the table's own span, which must
// stay at the document's call site (ADR 0023).
#let _table(body, content_kind: none) = {
  if content_kind == none {
    return body
  }
  _metadata.update(it => it + (content_kind: content_kind))
  body
  _metadata.update(it => {
    let d = it
    let _ = d.remove("content_kind", default: none)
    d
  })
}

#let cnd = (
  metadata: _metadata,
  table: _table,
)
