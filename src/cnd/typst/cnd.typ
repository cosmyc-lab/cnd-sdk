// CND authoring helpers — the official pure-Typst package for tagging
// documents with CND metadata. Works on any stock Typst toolchain: the only
// contract is the "cnd.metadata" state key, which CND emitters read
// (see spec/cnd-spec.md and ADR 0023).
//
// Usage: `#import "/cnd.typ"` — a whole-file import binds this file as a
// module named `cnd` (by file stem), and module members are callable
// directly: `#cnd.table(..)`, `#cnd.metadata.update(..)`. Do NOT export
// these as a dict (e.g. `#let cnd = (table: ..., metadata: ...)`): in
// stock Typst, a function stored in a dictionary field cannot be called
// directly as `#cnd.table(..)` — the compiler requires the awkward
// `#(cnd.table)(..)` — which breaks call-syntax parity with the
// compiler-injected module this package replaces.

// The CND metadata state. Import the whole file (see header) rather than
// destructuring individual names — `#import "/cnd.typ": table` would shadow
// Typst's own built-in `table`.
#let metadata = state("cnd.metadata", (:))

// Wraps already-built content (typically a `table(..)` call) and brackets it
// with a `content_kind` hint ("data" | "content") in the cnd.metadata state.
// Pass the content in — don't let this function build it: the source snippet
// emitters record for a table comes from the table's own span, which must
// stay at the document's call site (ADR 0023).
#let table(body, content_kind: none) = {
  if content_kind == none {
    return body
  }
  metadata.update(it => it + (content_kind: content_kind))
  body
  metadata.update(it => {
    let d = it
    let _ = d.remove("content_kind", default: none)
    d
  })
}
