---
title: Markdown writes a hyperlink where its words are, and a caller may allow its own schemes
status: accepted
date: 2026-11-05
tags: [converters, markdown, html, hyperlinks, urls]
related: [0024, 0025, 0027]
superseded-by: null
---

# ADR 0031 — Markdown writes a hyperlink where its words are, and a caller may allow its own schemes

## Status
accepted

## Context

A `links` edge carries an `href` and, most of the time, a `text_span` over
the words it links (ADR 0024, ADR 0025). The HTML converter already turns
those words into an anchor and keeps the marker line for the links it
cannot place. The Markdown converter did not: every link went to the
marker line under its block, as `[href](href)`. The words stayed in the
sentence and the address landed a line below, so with two links in one
paragraph nothing said which address belonged to which words. A language
model reading the output has to guess the pairing. A human reading the
file sees a link that is not where it should be.

The converter's own docstring gave two reasons for appending: splicing
would make marker position renderer-specific, and it would rewrite every
golden document. The first no longer holds, since HTML already places
links inline. The second is a compatibility cost, which does not decide a
design before 1.0 (ADR 0027).

The URL rule (spec §8) links only `http`, `https`, `mailto` and
scheme-less hrefs. It keeps a reader from following `javascript:` or
`data:`. It also turns every application scheme into plain text. A consumer
that resolves such a scheme itself had no way to say so, so its links
never became links in either Markdown or HTML.

## Decision

1. `MarkdownRenderer` gains `links` (off by default). When on, a `links`
   edge with a usable `text_span` is written as `[text](href)` over the
   text it spans, through the same inline layer and the same rules as the
   HTML anchor (`cnd.core.inline`, `edge_wrap`):
   - links never nest; of two overlapping links the outer or first wins;
   - a link inside a `code` or `math` atom is left out;
   - a refused href leaves the words plain.

   `links` needs `escape`, because unescaped prose could close the link
   or open another. It stays off by default for the same reason `escape`
   does: chunk text and embeddings must not change.
2. `MarkdownConverter`'s default renderer turns `links` on. The marker
   line keeps every link the renderer did not write. The renderer records
   the links each top-level `render` call wrote (`written_links`), and
   the converter leaves exactly those out, once per write. This record
   covers what the renderer writes in other ways:
   - a placeholder holds a text without rendering it;
   - a figure caption is recomposed with its counter;
   - a table whose cells hold blocks is an HTML block.

   Their links go to the marker line, so no link is lost and none is
   written twice.
3. `cnd.core.urls.allowed_link_schemes` checks a set of extra schemes a
   caller allows: lower-cased, RFC 3986 scheme syntax, and never
   `javascript`, `vbscript` or `data` (`NEVER_LINKED_SCHEMES`), which
   `is_safe_url` refuses even when passed. `MarkdownRenderer`,
   `HtmlNodeRenderer`, `MarkdownConverter.default_renderer` and
   `MarkdownConverter` take `link_schemes`. The marker line of both
   converters applies the renderer's schemes.
4. The other three families (`refs`, `cites`, `footnotes`) keep their
   appended markers. Their marker is not a link to an outside address,
   and Markdown has no element identity to link a label to.

## Consequences

- The default Markdown conversion changes for every document with a
  spanned link. The conversion is not normative (spec §8), and the CND
  format, schema and hashes do not change. This is an SDK minor release.
- Markdown now matches HTML for links. A link without a span, or one the
  renderer cannot place, still reaches the marker line.
- A renderer that writes texts outside `render_text` must not report them
  in `written_links`. The tests pin every placement of a link: exactly
  once, inline or on the marker line.
- Allowing a scheme is the caller's responsibility: the SDK refuses only
  the schemes that run code or embed a document.
