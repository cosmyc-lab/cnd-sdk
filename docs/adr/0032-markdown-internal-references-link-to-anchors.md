---
title: Markdown output keeps internal references navigable — references link to anchors
status: accepted
date: 2026-11-21
tags: [converters, markdown, cross-references, anchors]
related: [0017, 0031]
superseded-by: null
---

# ADR 0032 — Markdown output keeps internal references navigable

## Status
accepted

## Context

A `refs` edge names its target by label (ADR 0017) and, most of the time,
carries a `text_span` over the words that mark it ("Section 2"). The
Markdown converter wrote every reference as `[label]` on the marker line
under its block. ADR 0031 decision 4 kept it that way: Markdown has no
element identity, so there was nothing to link a label to.

The result is a file whose readers cannot follow an internal reference.
A person sees "see Section 2" and then a bracketed label a line below, which
does not link anywhere. A language model reading the file has to guess
which words the label belongs to, then search for the section by hand.
The HTML converter already shows that a reference can sit where its words
are.

Markdown has no syntax for an element id that every reader accepts.
Heading attributes (`## Method {#method}`) work in Pandoc but print as text
on GitHub and in many previews. Generated heading slugs differ between
renderers, and nothing generates one for a figure or a table. An empty
inline `<a id>` element is the common way Markdown authors mark a target
by hand, and the readers this targets (GitHub, VS Code's preview, Pandoc)
are expected to keep it; GitHub prefixes the id with `user-content-` and
resolves the fragment itself. The SDK's tests check the Markdown side with
a CommonMark parser (every link's destination equals one anchor's id);
the behaviour of each reader is expected, not tested. A reader that
decodes the fragment before matching could miss an anchor whose label
needed percent-encoding (anything outside `[A-Za-z0-9._:-]`); a plain
label is unaffected.

## Decision

1. `MarkdownRenderer` gains `ref_links` (off by default) and `ref_targets`.
   When on, a `refs` edge with a usable `text_span` whose label is a
   target is written `[text](#anchor)` over the text it spans. It goes
   through the same inline layer and the same rules as a `links` edge
   (ADR 0031): links never nest, none sits inside a `code` or `math` atom
   or over words a Markdown link cannot hold. The renderer notes it in the
   written-links record, which now holds `refs` edges as well as `links`
   edges, so the converter leaves it off the marker line. `ref_links`
   needs `escape`, as `links` does. It refuses `text_only`, because the
   anchor it links to is an HTML element.
2. The anchor is `cnd.core.render.markdown_anchor(label)`. ASCII letters,
   digits and `._:-` stay as they are; every other character is
   percent-encoded as UTF-8, `%` included. The same string goes in the id
   and, after `#`, in the link. It needs no escaping in an HTML attribute,
   in a URL fragment or in a Markdown link destination. A browser matches
   the fragment to the id as written before it tries a decoded form. The
   mapping is injective, so two labels never share an anchor.
3. `MarkdownConverter(ref_links=True)` (and `default_renderer(ref_links=True)`)
   turns it on. Each conversion computes its targets once: the labels a
   `refs` edge of the document names that resolve to a node (not a pool
   entry). That set decides both sides, so every link has exactly one
   anchor and every anchor is linked to:
   - every target carries `<a id="anchor"></a>`. In a heading it sits on
     the heading line after the `#`s. In a paragraph it opens the line.
     Before any other block it stands on a line of its own, since a table,
     a list or a fence must start its line. A target nested in a container
     (a list item, a table cell, a figure) is anchored at the block of the
     container that renders it. A target inside a footnote is anchored in
     its definition;
   - a reference the renderer could not place (no span, inside an atom,
     losing to an overlapping link) is `[label](#anchor)` on the marker
     line;
   - a reference whose label resolves to nothing keeps its `[label]` and
     its warning.
4. The converter hands the targets to its renderer through a context
   variable (`cnd.core.render.providing_ref_targets`) for the duration of
   one conversion. It does not set them on the renderer. A renderer
   injected with `ref_links=True`, a subclass included, gets them as the
   default one does. A renderer shared between threads, or used by a
   conversion nested in another, never sees another conversion's
   targets. Used on its own, the renderer links the `ref_targets` it was
   built with, and writing their anchors is the caller's job.
5. `cites` and `footnotes` keep their markers, and the default conversion
   is unchanged.

## Consequences

- The option is off by default for the same reason `escape` is: chunk
  text and embeddings must not change, and inline HTML is not what a
  plain-text consumer wants. A consumer that produces a file for people
  or agents to read turns it on.
- A labelled node that nothing references gets no anchor. Its label stays
  dropped from the output, as before.
- The anchor lands on the block that renders a nested target, not always
  on the target itself. The link still lands next to it, and no link is
  left without an anchor.
- The written-links record carries `NodeRef`s as well as `LinkRef`s. A
  converter reading it matches edges by identity per family, so the HTML
  converter, which reads only `links`, is unaffected.
- This is an SDK minor release. The CND format, schema and hashes do not
  change.
