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

// The table hint's restore stack (one entry per open `table`). Internal: a
// separate state, so nothing but the hint itself lands in "cnd.metadata".
#let _cnd-table-restore = state("cnd.table-restore", ())

// Wraps already-built content (typically a `table(..)` call) and brackets it
// with the table's `kind` in the cnd.metadata state: "data" (a dataset of
// records) or "content" (cells to read), the CND's `table.kind`
// (spec §6.3). Any other string passes through: `kind` is an open
// vocabulary. Pass the content in — don't let this function build it: the
// source snippet emitters record for a table comes from the table's own
// span, which must stay at the document's call site (ADR 0023).
//
// After the table, `kind` goes back to what it was before: a document-level
// `kind` the author set is restored, and the key is removed only when it was
// absent. The previous value is read in a `context` that holds the state
// updates only; `body` stays outside it, at the call site.
#let table(body, kind: none) = {
  if kind == none {
    return body
  }
  // The previous value is read once, before this table's own update, and
  // carried into the restore below: nested hints unwind in order.
  context {
    let before = metadata.get()
    let had = "kind" in before
    let previous = before.at("kind", default: none)
    metadata.update(it => it + (kind: kind))
    _cnd-table-restore.update(stack => stack + ((had: had, kind: previous),))
  }
  body
  context {
    let saved = _cnd-table-restore.get().last()
    metadata.update(it => {
      let d = it
      if saved.had {
        d.insert("kind", saved.kind)
      } else {
        let _ = d.remove("kind", default: none)
      }
      d
    })
    _cnd-table-restore.update(stack => stack.slice(0, -1))
  }
}

// Marks content as purely decorative — an ornament, a logo, an icon, a
// background — so CND emitters never emit it: no node, no text, no
// footnote (spec §2, "Decorative content"; docs/proposals/0011). It is
// Typst's own `pdf.artifact`, so the PDF's accessibility tree skips it too.
// Never wrap content that carries meaning: a chart or a diagram goes in a
// `figure` with a caption that says what it shows.
#let decorative(body) = pdf.artifact(body)
