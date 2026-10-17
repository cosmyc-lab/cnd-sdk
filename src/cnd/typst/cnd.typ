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
// with the table's kind in the cnd.metadata state: "data" (a dataset of
// records) or "content" (cells to read). Any other string passes through:
// the kind is an open vocabulary. The author writes `kind:`; the state
// carries it under the dedicated key `table-kind`, which an emitter reads
// and the CND writes as `table.kind` (spec §6.3). A dedicated key never
// collides with the author's own metadata, such as a document-level `kind`,
// so the hint is set before the table and removed after it, with nothing
// to read back or restore. Pass the content in — don't let this function
// build it: the source snippet emitters record for a table comes from the
// table's own span, which must stay at the document's call site (ADR 0023).
#let table(body, kind: none) = {
  if kind == none {
    return body
  }
  metadata.update(it => it + ("table-kind": kind))
  body
  metadata.update(it => {
    let d = it
    let _ = d.remove("table-kind", default: none)
    d
  })
}

// Marks content as purely decorative — an ornament, a logo, an icon, a
// background — so CND emitters never emit it: no node, no text, no
// footnote (spec §2, "Decorative content"; docs/proposals/0011). It is
// Typst's own `pdf.artifact`, so the PDF's accessibility tree skips it too.
// Never wrap content that carries meaning: a chart or a diagram goes in a
// `figure` with a caption that says what it shows.
#let decorative(body) = pdf.artifact(body)


// Declares the document-level metadata a title page prints, as the author
// wrote it: `status` ("Approved") and `version` ("1.2"), plus any other
// title-page pair in `extra`. The marker is a labelled `metadata` element,
// found with `query(<cnd-document>)`; it renders nothing. The title,
// authors, date, keywords, description and language come from Typst's own
// `set document(..)` and `set text(lang: ..)`, so `extra` may not repeat
// one of them, nor `status`, `version` or `extra` (spec §3). Every `extra`
// value is a string. (ADR 0030.)
#let document(status: none, version: none, extra: (:)) = {
  let reserved = (
    "title", "authors", "date", "keywords", "description", "lang",
    "status", "version", "extra",
  )
  for (key, value) in extra {
    assert(type(value) == str, message: "cnd.document: extra." + key + " must be a string")
    assert(
      key not in reserved,
      message: "cnd.document: extra may not use the reserved key `" + key + "`",
    )
  }
  [#std.metadata((status: status, version: version, extra: extra)) <cnd-document>]
}

// A callout, such as a note or a warning. `kind` is an open vocabulary; the
// known values are `note`, `tip`, `important`, `warning` and `caution`
// (spec §6.11). Two labelled markers bracket the body, `<cnd-admonition>`
// before (carrying `kind` and `title`) and `<cnd-admonition-end>` after, so
// an emitter reads the content between them as the admonition's children.
// The title, when given, is the block's first child under
// `<cnd-admonition-title>`. (ADR 0030.)
#let admonition(body, kind: "note", title: none) = {
  [#std.metadata((kind: kind, title: title)) <cnd-admonition>]
  block(
    width: 100%,
    inset: (left: 1em, y: 0.6em),
    stroke: (left: 2pt + luma(150)),
    {
      if title != none {
        [#block(strong(title)) <cnd-admonition-title>]
      }
      body
    },
  )
  [#std.metadata(none) <cnd-admonition-end>]
}

// Wraps already-built content (typically a `raw(..)` block) and brackets it
// with the listing's title in the cnd.metadata state under the dedicated
// key `code-title`, which an emitter writes as `code.title` (spec §6.5).
// Same pattern as `table`: set before the content, removed after, and the
// content is passed in so its span stays at the document's call site
// (ADR 0023). (ADR 0030.)
#let code(body, title: none) = {
  if title == none {
    return body
  }
  metadata.update(it => it + ("code-title": title))
  body
  metadata.update(it => {
    let d = it
    let _ = d.remove("code-title", default: none)
    d
  })
}
