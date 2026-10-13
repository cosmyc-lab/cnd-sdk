"""cnd -> html: a whole ``Cnd`` as one complete standalone ``.html`` file.

Target 2 of docs/proposals/0007. Unlike the Markdown target there is no
HTML node renderer in the core hierarchy, so this module carries one —
``HtmlNodeRenderer``. It lives here on purpose: spec §7 enumerates the
renderers the core ships, and adding to that list is an ADR 0011 / spec
decision, not something an outbound converter gets to do on its way past.
``HtmlNodeRenderer`` is an implementation detail of this converter, and
is a plain ``NodeRenderer`` any caller may still use directly.
"""

import re
from html import escape

from cnd.core.cnd import Cnd
from cnd.core.inline import render_inline
from cnd.core.nodes import (
    AdmonitionNode,
    Cell,
    CndNode,
    CodeNode,
    FigureNode,
    HeadingNode,
    ImageNode,
    LayoutNode,
    ListItem,
    ListNode,
    MathNode,
    NodeBase,
    ParagraphNode,
    QuoteNode,
    TableNode,
    TermsNode,
)
from cnd.core.render import NodeRenderer, expand_headings, holds_several_blocks
from cnd.core.text import Edge, LinkRef, RichText
from cnd.core.urls import is_safe_image_source, is_safe_url

from cnd.converters.base import (
    CndConverter,
    ConversionResult,
    ResolvedMarker,
    format_date,
    iter_body,
    resolve_markers,
)
from cnd.converters.markdown import format_bib_entry

__all__ = ["HtmlConverter", "HtmlNodeRenderer"]

_STYLE = """\
:root { color-scheme: light dark; }
body { margin: 0 auto; max-width: 46rem; padding: 2rem 1rem;
       font-family: system-ui, sans-serif; line-height: 1.6; }
figure { margin: 1.5rem 0; }
figcaption { font-size: .9em; opacity: .8; }
table { border-collapse: collapse; }
th, td { border: 1px solid currentColor; padding: .25rem .5rem; }
pre { overflow-x: auto; padding: .75rem; }
.cnd-layout { display: grid; gap: 1rem; }
.cnd-admonition { border-left: .25rem solid currentColor; margin: 1rem 0;
                  padding: .25rem 1rem; }
.cnd-admonition-title { font-weight: bold; }
.cnd-code-title { font-family: monospace; font-size: .9em; margin-bottom: 0; }
.cnd-markers { font-size: .85em; opacity: .75; }
.cnd-unresolved { text-decoration: underline wavy; }
.cnd-missing-image { font-style: italic; opacity: .7; }
"""


def _link_wrap(edge: Edge) -> tuple[str, str] | None:
    """The ``<a>`` around the text a ``links`` edge spans; ``None`` for
    the other families, and for an href that is not safe to link to."""
    if not isinstance(edge, LinkRef) or not is_safe_url(edge.href):
        return None
    return f'<a class="cnd-link" href="{escape(edge.href, quote=True)}">', "</a>"


_RESERVED_META = frozenset(
    {"author", "description", "keywords", "date", "status", "version", "viewport"}
)
"""The ``<meta name>`` values the converter writes from the document
itself; a ``doc.extra`` key equal to one (in any case) is skipped."""


def _anchor(node: NodeBase) -> str:
    """``id="<label>"`` for a labelled node, nothing for an unlabelled one."""
    return f' id="{escape(node.label, quote=True)}"' if node.label else ""


def _css_token(value: str) -> str:
    """An open-vocabulary value as one CSS class token."""
    return escape(re.sub(r"\s+", "-", value.strip()), quote=True)


def _numbering(node: HeadingNode | MathNode | FigureNode) -> str:
    numbering = node.numbering
    if numbering is None:
        return ""
    return " ".join(part for part in (numbering.name, numbering.value) if part)


class HtmlNodeRenderer(NodeRenderer):
    """Render one node as an HTML fragment. Text is always escaped.

    A node's ``label`` becomes the element's ``id``, which is what gives
    the HTML converter real in-document cross-reference links where the
    Markdown converter only has bracketed text. Node ``id`` (the UUID),
    ``state_metadata`` and ``location`` are not emitted. A container
    renders its nested nodes itself.

    A ``links`` edge with a ``text_span`` makes the text it spans an
    ``<a class="cnd-link">``, unless its href fails
    ``cnd.core.urls.is_safe_url``: the text then stays plain. ``links=False``
    leaves every text plain, for a caller that renders links elsewhere.
    """

    def __init__(self, *, links: bool = True) -> None:
        self.links = links

    def render_text(self, text: RichText) -> str:
        return render_inline(text, "html", edge_wrap=_link_wrap if self.links else None)

    def _blocks(self, nodes: list[CndNode]) -> str:
        return "".join(self.render(node) for node in expand_headings(nodes))

    def _flow(self, nodes: list[CndNode]) -> str:
        """The content of an item, a cell or a definition. Tight like
        Markdown: unless it holds several blocks
        (``cnd.core.render.holds_several_blocks``), a plain paragraph
        renders as bare text, without ``<p>``."""
        if holds_several_blocks(nodes):
            return "".join(self.render(node) for node in expand_headings(nodes))
        nodes = expand_headings(nodes)
        return "".join(
            self.render_text(node.text)
            if isinstance(node, ParagraphNode) and node.label is None and node.text.lang is None
            else self.render(node)
            for node in nodes
        )

    def render_heading(self, node: HeadingNode) -> str:
        level = min(max(node.level, 1), 6)
        prefix = _numbering(node)
        text = self.render_text(node.text)
        inner = f"{escape(prefix)} {text}" if prefix else text
        return f"<h{level}{_anchor(node)}>{inner}</h{level}>"

    def render_paragraph(self, node: ParagraphNode) -> str:
        lang = node.text.lang
        lang_attr = f' lang="{escape(lang, quote=True)}"' if lang else ""
        return f"<p{_anchor(node)}{lang_attr}>{self.render_text(node.text)}</p>"

    def render_table(self, node: TableNode) -> str:
        rows: dict[int, list[Cell]] = {}
        for cell in node.cells:
            rows.setdefault(cell.row, []).append(cell)
        body = []
        for row in sorted(rows):
            cells = sorted(rows[row], key=lambda cell: cell.col)
            body.append("<tr>" + "".join(self._cell(cell) for cell in cells) + "</tr>")
        kind = f' data-kind="{escape(node.kind, quote=True)}"' if node.kind else ""
        return f"<table{_anchor(node)}{kind}>" + "".join(body) + "</table>"

    def _cell(self, cell: Cell) -> str:
        tag = "th" if cell.is_header else "td"
        attrs = ""
        if cell.rowspan != 1:
            attrs += f' rowspan="{cell.rowspan}"'
        if cell.colspan != 1:
            attrs += f' colspan="{cell.colspan}"'
        return f"<{tag}{attrs}>{self._flow(cell.children)}</{tag}>"

    def render_layout(self, node: LayoutNode) -> str:
        """A CSS grid; each cell keeps its row, column and spans."""
        cols = max((cell.col + max(cell.colspan, 1) for cell in node.cells), default=1)
        cells = "".join(
            f'<div style="grid-row: {cell.row + 1} / span {max(cell.rowspan, 1)}; '
            f'grid-column: {cell.col + 1} / span {max(cell.colspan, 1)}">'
            f"{self._blocks(cell.children)}</div>"
            for cell in sorted(node.cells, key=lambda c: (c.row, c.col))
        )
        return (
            f'<div{_anchor(node)} class="cnd-layout" '
            f'style="grid-template-columns: repeat({cols}, 1fr)">{cells}</div>'
        )

    def render_quote(self, node: QuoteNode) -> str:
        inner = self._blocks(node.children)
        if node.attribution is not None:
            inner += f"<footer>{self.render_text(node.attribution)}</footer>"
        return f"<blockquote{_anchor(node)}>{inner}</blockquote>"

    def render_admonition(self, node: AdmonitionNode) -> str:
        title = self.render_text(node.title) if node.title is not None else escape(node.kind)
        return (
            f'<aside{_anchor(node)} class="cnd-admonition '
            f'cnd-admonition-{_css_token(node.kind)}">'
            f'<p class="cnd-admonition-title">{title}</p>'
            f"{self._blocks(node.children)}</aside>"
        )

    def render_code(self, node: CodeNode) -> str:
        cls = f' class="language-{escape(node.lang, quote=True)}"' if node.lang else ""
        if node.title:
            return (
                f'<div{_anchor(node)} class="cnd-code">'
                f'<p class="cnd-code-title">{escape(node.title)}</p>'
                f"<pre><code{cls}>{escape(node.text)}</code></pre></div>"
            )
        return f"<pre{_anchor(node)}><code{cls}>{escape(node.text)}</code></pre>"

    def render_math(self, node: MathNode) -> str:
        number = _numbering(node)
        inner = f'<code class="cnd-math">{escape(node.text)}</code>'
        if number:
            inner += f'<span class="cnd-number">{escape(number)}</span>'
        return f'<div{_anchor(node)} class="cnd-math-block">{inner}</div>'

    def render_figure(self, node: FigureNode) -> str:
        parts = [self.render(child) for child in expand_headings(node.children)]
        if not node.children and node.raw is not None:
            parts.append(
                f'<pre class="cnd-raw" data-format='
                f'"{escape(node.raw.format, quote=True)}">'
                f"<code>{escape(node.raw.value)}</code></pre>"
            )
        caption = self._caption(node)
        if caption:
            parts.append(f"<figcaption>{caption}</figcaption>")
        kind = f' data-kind="{escape(node.kind, quote=True)}"' if node.kind else ""
        return f"<figure{_anchor(node)}{kind}>" + "".join(parts) + "</figure>"

    def _caption(self, node: FigureNode) -> str:
        """``Figure 3: caption``, then the description as a paragraph."""
        counter = escape(_numbering(node))
        caption = self.render_text(node.caption) if node.caption is not None else ""
        title = ": ".join(part for part in (counter, caption) if part)
        if node.description is not None:
            title += f'<p class="cnd-description">{self.render_text(node.description)}</p>'
        return title

    def render_image(self, node: ImageNode) -> str:
        """``<img>``; a path that is missing or fails
        ``cnd.core.urls.is_safe_image_source`` renders the alt text in a
        ``cnd-missing-image`` span instead."""
        alt = escape(node.alt or "", quote=True)
        if node.path and is_safe_image_source(node.path):
            src = escape(node.path, quote=True)
            return f'<img{_anchor(node)} src="{src}" alt="{alt}">'
        return (
            f'<span{_anchor(node)} class="cnd-missing-image">'
            f"{escape(node.alt or 'image')}</span>"
        )

    def render_list(self, node: ListNode) -> str:
        tag = "ol" if node.ordered else "ul"
        items = "".join(self._item(item) for item in node.items)
        return f"<{tag}{_anchor(node)}>{items}</{tag}>"

    def _item(self, item: ListItem) -> str:
        box = ""
        if item.checked is not None:
            box = f'<input type="checkbox" disabled{" checked" if item.checked else ""}> '
        return f"<li>{box}{self._flow(item.children)}</li>"

    def render_terms(self, node: TermsNode) -> str:
        items = "".join(
            f"<dt>{self.render_text(item.term)}</dt><dd>{self._flow(item.children)}</dd>"
            for item in node.items
        )
        return f"<dl{_anchor(node)}>{items}</dl>"


class HtmlConverter(CndConverter):
    """Convert a whole ``Cnd`` into one standalone HTML document.

    The output is a complete file — doctype, ``<head>`` with charset,
    title and metadata, an inline stylesheet, and a ``<body>`` — never a
    fragment. It is self-contained apart from ``ImageNode.path``, which
    is emitted as ``src`` and is the producer's identifier, not a promise
    that it resolves; a path that is neither a safe URL nor a
    ``data:image/`` URI (``cnd.core.urls``) renders the alt text instead.

    Structure, all of it **non-normative** (spec §7):

    - ``<head>``: ``<title>`` and ``<meta>`` for authors, description,
      keywords, date, status, version and every ``doc.extra`` pair from
      ``cnd.doc``, except an ``extra`` key naming a meta element the
      converter writes itself (skipped, with a warning); ``cnd_version`` and ``built_at`` as ``data-``
      attributes on ``<html>``.
    - ``<article>``: the body, assembled by walking the tree in reading
      order and delegating each block to the injected renderer. A
      container (figure, list, table, quote…) renders once, from the
      container node; only headings are descended into.
    - ``<section class="cnd-footnotes">`` and
      ``<section class="cnd-bibliography">`` from the pools, in pool
      order, each entry anchored on its label so markers link to it. A
      footnote's blocks render like body blocks.
    - Markers appended after each block in a ``<span class=
      "cnd-markers">``, as real ``<a href="#label">`` links, for the
      edges of every text in the block; a marker whose label does not
      resolve degrades to a ``<span class="cnd-unresolved">`` and is
      reported in ``ConversionResult.warnings``.
    - ``links``: a hyperlink with a ``text_span`` is an ``<a
      class="cnd-link">`` around the text it spans (the renderer's
      job, see ``HtmlNodeRenderer``); one without a span goes to the
      marker line as ``<a class="cnd-link" href="…">href</a>``. An
      href that fails ``cnd.core.urls.is_safe_url`` is never emitted as
      a link: the spanned text stays plain, a span-less href is written
      as text.

    **Irreducibly dropped** — the same for every document
    (docs/proposals/0007):

    - ``text_span`` of ``refs``, ``cites`` and ``footnotes`` — their
      markers are appended after the block rather than spliced in at
      their standoff offsets; only their relative order survives.
    - ``CiteRef.form`` and ``supplement`` beyond the ``none`` case: HTML
      has no citation model, so a bracketed link is all there is.
    - ``state_metadata`` and ``NodeLocation.page``: no target in HTML.
    - Node ``id`` (the UUID). Element identity is the ``label``, since
      that is what links resolve by (docs/adr/0017) and a UUID is not
      durable across builds anyway (docs/adr/0015).
    - ``BibEntry.fields`` and ``BibEntry`` structure generally — the
      bibliography is emitted as reference strings, see
      ``format_bib_entry``.
    - ``RawSource`` survives only on a childless figure, as a ``<pre>``;
      ``math.raw`` is dropped in favour of the structured content.

    This conversion does **not** round-trip.
    """

    extension = "html"
    media_type = "text/html"

    def __init__(
        self,
        renderer: NodeRenderer | None = None,
        *,
        footnotes_title: str = "Footnotes",
        bibliography_title: str = "Bibliography",
    ) -> None:
        super().__init__(renderer)
        self.footnotes_title = footnotes_title
        self.bibliography_title = bibliography_title

    @classmethod
    def default_renderer(cls) -> NodeRenderer:
        return HtmlNodeRenderer()

    def convert(self, cnd: Cnd) -> ConversionResult:
        warnings: list[str] = []
        lang = f' lang="{escape(cnd.doc.lang, quote=True)}"' if cnd.doc.lang else ""
        lines = [
            "<!DOCTYPE html>",
            f'<html{lang} data-cnd-version="{escape(cnd.cnd_version, quote=True)}"'
            f' data-built-at="{escape(cnd.built_at.isoformat(), quote=True)}">',
            "<head>",
            '<meta charset="utf-8">',
            '<meta name="viewport" content="width=device-width, initial-scale=1">',
            f"<title>{escape(cnd.doc.title)}</title>",
        ]
        lines.extend(self._head_meta(cnd, warnings))
        lines.append(f"<style>\n{_STYLE}</style>")
        lines.append("</head>")
        lines.append("<body>")
        lines.append("<article>")
        lines.extend(self._body(cnd, warnings))
        lines.append("</article>")
        lines.extend(self._footnotes_section(cnd, warnings))
        lines.extend(self._bibliography_section(cnd, warnings))
        lines.append("</body>")
        lines.append("</html>")
        return ConversionResult(text="\n".join(lines) + "\n", warnings=tuple(warnings))

    # -- head -----------------------------------------------------------

    def _head_meta(self, cnd: Cnd, warnings: list[str]) -> list[str]:
        doc = cnd.doc
        out = []
        for author in doc.authors:
            out.append(f'<meta name="author" content="{escape(author, quote=True)}">')
        if doc.description:
            out.append(
                f'<meta name="description" '
                f'content="{escape(doc.description, quote=True)}">'
            )
        if doc.keywords:
            joined = escape(", ".join(doc.keywords), quote=True)
            out.append(f'<meta name="keywords" content="{joined}">')
        if doc.date is not None:
            out.append(
                f'<meta name="date" content="{format_date(doc.date)}">'
            )
        pairs = [("status", doc.status), ("version", doc.version)]
        for name, value in doc.extra.items():
            if name.strip().lower() in _RESERVED_META:
                warnings.append(
                    f"doc.extra key {name!r} names a meta element the converter "
                    f"writes itself; skipped"
                )
            else:
                pairs.append((name, value))
        for name, value in pairs:
            if value:
                out.append(
                    f'<meta name="{escape(name, quote=True)}" '
                    f'content="{escape(value, quote=True)}">'
                )
        return out

    # -- body -----------------------------------------------------------

    def _body(self, cnd: Cnd, warnings: list[str]) -> list[str]:
        blocks = [self._block(cnd, visit.node, warnings) for visit in iter_body(cnd)]
        return [block for block in blocks if block]

    def _block(self, cnd: Cnd, node: CndNode, warnings: list[str]) -> str:
        rendered = self.renderer.render(node)
        markers = self._markers(cnd, node, warnings)
        if markers:
            rendered = f"{rendered}\n{markers}"
        return rendered

    def _markers(self, cnd: Cnd, node: CndNode, warnings: list[str]) -> str:
        rendered = [
            self._marker(marker)
            for marker in resolve_markers(cnd, node, warnings)
        ]
        parts = [part for part in rendered if part]
        if not parts:
            return ""
        return '<span class="cnd-markers">' + " ".join(parts) + "</span>"

    @staticmethod
    def _marker(marker: ResolvedMarker) -> str:
        if marker.family == "links":
            href = marker.link.href
            if marker.link.text_span:
                return ""  # the renderer links the spanned text itself
            if not is_safe_url(href):
                return escape(href)
            return f'<a class="cnd-link" href="{escape(href, quote=True)}">{escape(href)}</a>'
        label = escape(marker.label)
        href = escape(marker.label, quote=True)
        if marker.family == "cites" and getattr(marker.link, "form", None) == "none":
            return ""
        if marker.target is None:
            return f'<span class="cnd-unresolved">[{label}]</span>'
        if marker.family == "footnotes":
            return f'<sup class="cnd-footnote"><a href="#{href}">{label}</a></sup>'
        text = label
        supplement = getattr(marker.link, "supplement", None)
        if supplement:
            text = f"{label}, {escape(supplement)}"
        css = "cnd-cite" if marker.family == "cites" else "cnd-ref"
        return f'<a class="{css}" href="#{href}">[{text}]</a>'

    # -- pools ----------------------------------------------------------

    def _footnotes_section(self, cnd: Cnd, warnings: list[str]) -> list[str]:
        if not cnd.footnotes:
            return []
        out = ['<section class="cnd-footnotes">', f"<h2>{escape(self.footnotes_title)}</h2>", "<ol>"]
        for note in cnd.footnotes:
            anchor = escape(note.label, quote=True)
            body = "".join(
                self._block(cnd, child, warnings) for child in expand_headings(note.children)
            )
            out.append(f'<li id="{anchor}">{body}</li>')
        out.extend(["</ol>", "</section>"])
        return out

    def _bibliography_section(self, cnd: Cnd, warnings: list[str]) -> list[str]:
        if not cnd.bibliography:
            return []
        out = [
            '<section class="cnd-bibliography">',
            f"<h2>{escape(self.bibliography_title)}</h2>",
            "<ul>",
        ]
        for entry in cnd.bibliography:
            reference, warning = format_bib_entry(entry)
            if warning:
                warnings.append(warning)
            anchor = escape(entry.label, quote=True)
            out.append(f'<li id="{anchor}">{self.renderer.render_text(reference)}</li>')
        out.extend(["</ul>", "</section>"])
        return out
