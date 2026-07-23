"""cnd -> html: a whole ``Cnd`` as one complete standalone ``.html`` file.

Target 2 of docs/proposals/0007. Unlike the Markdown target there is no
HTML node renderer in the core hierarchy, so this module carries one —
``HtmlNodeRenderer``. It lives here on purpose: spec §7 enumerates the
renderers the core ships, and adding to that list is an ADR 0011 / spec
decision, not something an outbound converter gets to do on its way past.
``HtmlNodeRenderer`` is an implementation detail of this converter, and
is a plain ``NodeRenderer`` any caller may still use directly.
"""

from html import escape

from cnd.core.cnd import Cnd
from cnd.core.nodes import (
    CndNode,
    CodeNode,
    FigureNode,
    HeadingNode,
    ImageNode,
    ListItem,
    ListNode,
    MathNode,
    NodeBase,
    ParagraphNode,
    QuoteNode,
    TableCell,
    TableNode,
    TermsNode,
)
from cnd.core.render import NodeRenderer

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
.cnd-markers { font-size: .85em; opacity: .75; }
.cnd-unresolved { text-decoration: underline wavy; }
.cnd-missing-image { font-style: italic; opacity: .7; }
"""


def _anchor(node: NodeBase) -> str:
    """``id="<label>"`` for a labelled node, nothing for an unlabelled one."""
    return f' id="{escape(node.label, quote=True)}"' if node.label else ""


class HtmlNodeRenderer(NodeRenderer):
    """Render one node as an HTML fragment. Text is always escaped.

    A node's ``label`` becomes the element's ``id``, which is what gives
    the HTML converter real in-document cross-reference links where the
    Markdown converter only has bracketed text. Node ``id`` (the UUID),
    ``state_metadata`` and ``location`` are not emitted.
    """

    def render_heading(self, node: HeadingNode) -> str:
        level = min(max(node.level, 1), 6)
        prefix = " ".join(
            part for part in (node.counter_label, node.number) if part
        )
        text = escape(node.text)
        inner = f"{escape(prefix)} {text}" if prefix else text
        return f"<h{level}{_anchor(node)}>{inner}</h{level}>"

    def render_paragraph(self, node: ParagraphNode) -> str:
        lang = f' lang="{escape(node.lang, quote=True)}"' if node.lang else ""
        return f"<p{_anchor(node)}{lang}>{escape(node.text)}</p>"

    def render_table(self, node: TableNode) -> str:
        rows: dict[int, list[TableCell]] = {}
        for cell in node.cells:
            rows.setdefault(cell.row, []).append(cell)
        body = []
        for row in sorted(rows):
            cells = sorted(rows[row], key=lambda cell: cell.col)
            body.append("<tr>" + "".join(_cell_html(cell) for cell in cells) + "</tr>")
        role = ' role="presentation"' if node.kind == "grid" else ""
        return f"<table{_anchor(node)}{role}>" + "".join(body) + "</table>"

    def render_quote(self, node: QuoteNode) -> str:
        lang = f' lang="{escape(node.lang, quote=True)}"' if node.lang else ""
        inner = f"<p>{escape(node.text)}</p>"
        if node.attribution:
            inner += f"<footer>{escape(node.attribution)}</footer>"
        return f"<blockquote{_anchor(node)}{lang}>{inner}</blockquote>"

    def render_code(self, node: CodeNode) -> str:
        cls = f' class="language-{escape(node.lang, quote=True)}"' if node.lang else ""
        return (
            f"<pre{_anchor(node)}><code{cls}>{escape(node.text)}</code></pre>"
        )

    def render_math(self, node: MathNode) -> str:
        number = " ".join(part for part in (node.counter_label, node.number) if part)
        tag = "div" if node.block else "span"
        inner = f'<code class="cnd-math">{escape(node.text)}</code>'
        if number:
            inner += f'<span class="cnd-number">{escape(number)}</span>'
        return f'<{tag}{_anchor(node)} class="cnd-math-block">{inner}</{tag}>'

    def render_figure(self, node: FigureNode) -> str:
        parts = [self.render(child) for child in node.children]
        if not node.children and node.raw is not None:
            parts.append(
                f'<pre class="cnd-raw" data-format='
                f'"{escape(node.raw.format, quote=True)}">'
                f"<code>{escape(node.raw.value)}</code></pre>"
            )
        caption = _caption_text(node)
        if caption:
            parts.append(f"<figcaption>{escape(caption)}</figcaption>")
        kind = f' data-kind="{escape(node.kind, quote=True)}"' if node.kind else ""
        return f"<figure{_anchor(node)}{kind}>" + "".join(parts) + "</figure>"

    def render_image(self, node: ImageNode) -> str:
        alt = escape(node.alt or "", quote=True)
        if node.path:
            src = escape(node.path, quote=True)
            return f'<img{_anchor(node)} src="{src}" alt="{alt}">'
        return (
            f'<span{_anchor(node)} class="cnd-missing-image">'
            f"{escape(node.alt or 'image')}</span>"
        )

    def render_list(self, node: ListNode) -> str:
        tag = "ol" if node.ordered else "ul"
        return f"<{tag}{_anchor(node)}>{_list_items(node.items)}</{tag}>"

    def render_terms(self, node: TermsNode) -> str:
        items = "".join(
            f"<dt>{escape(item.term)}</dt><dd>{escape(item.description)}</dd>"
            for item in node.items
        )
        return f"<dl{_anchor(node)}>{items}</dl>"


def _cell_html(cell: TableCell) -> str:
    tag = "th" if cell.is_header else "td"
    attrs = ""
    if cell.rowspan != 1:
        attrs += f' rowspan="{cell.rowspan}"'
    if cell.colspan != 1:
        attrs += f' colspan="{cell.colspan}"'
    return f"<{tag}{attrs}>{escape(cell.text)}</{tag}>"


def _list_items(items: list[ListItem]) -> str:
    out = []
    for item in items:
        inner = escape(item.text)
        if item.children:
            inner += f"<ul>{_list_items(item.children)}</ul>"
        out.append(f"<li>{inner}</li>")
    return "".join(out)


def _caption_text(node: FigureNode) -> str | None:
    counter = " ".join(part for part in (node.counter_label, node.number) if part)
    return ": ".join(part for part in (counter, node.caption) if part) or None


class HtmlConverter(CndConverter):
    """Convert a whole ``Cnd`` into one standalone HTML document.

    The output is a complete file — doctype, ``<head>`` with charset,
    title and metadata, an inline stylesheet, and a ``<body>`` — never a
    fragment. It is self-contained apart from ``ImageNode.path``, which
    is emitted verbatim as ``src`` and is the producer's identifier, not
    a promise that it resolves.

    Structure, all of it **non-normative** (spec §7):

    - ``<head>``: ``<title>`` and ``<meta>`` for authors, description,
      keywords and date from ``cnd.doc``; ``cnd_version`` and
      ``built_at`` as ``data-`` attributes on ``<html>``.
    - ``<article>``: the body, assembled by walking the tree in reading
      order and delegating each node to the injected renderer. Figures
      render once, from the wrapper node.
    - ``<section class="cnd-footnotes">`` and
      ``<section class="cnd-bibliography">`` from the pools, in pool
      order, each entry anchored on its label so markers link to it.
    - Markers appended after each block in a ``<span class=
      "cnd-markers">``, as real ``<a href="#label">`` links; a marker
      whose label does not resolve degrades to a
      ``<span class="cnd-unresolved">`` and is reported in
      ``ConversionResult.warnings``.

    **Irreducibly dropped** — the same for every document
    (docs/proposals/0007):

    - ``text_span`` — markers are appended after the block rather than
      spliced in at their standoff offsets; only their relative order
      survives.
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
      ``table.raw`` and ``math.raw`` are dropped in favour of the
      structured content.

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
        lines.extend(self._head_meta(cnd))
        lines.append(f"<style>\n{_STYLE}</style>")
        lines.append("</head>")
        lines.append("<body>")
        lines.append("<article>")
        lines.extend(self._body(cnd, warnings))
        lines.append("</article>")
        lines.extend(self._footnotes_section(cnd))
        lines.extend(self._bibliography_section(cnd, warnings))
        lines.append("</body>")
        lines.append("</html>")
        return ConversionResult(text="\n".join(lines) + "\n", warnings=tuple(warnings))

    # -- head -----------------------------------------------------------

    def _head_meta(self, cnd: Cnd) -> list[str]:
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
        return out

    # -- body -----------------------------------------------------------

    def _body(self, cnd: Cnd, warnings: list[str]) -> list[str]:
        blocks: list[str] = []
        for visit in iter_body(cnd):
            rendered = self.renderer.render(visit.node)
            markers = self._markers(cnd, visit.node, warnings)
            if markers:
                rendered = f"{rendered}\n{markers}"
            if rendered:
                blocks.append(rendered)
        return blocks

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

    def _footnotes_section(self, cnd: Cnd) -> list[str]:
        if not cnd.footnotes:
            return []
        out = ['<section class="cnd-footnotes">', f"<h2>{escape(self.footnotes_title)}</h2>", "<ol>"]
        for note in cnd.footnotes:
            anchor = escape(note.label, quote=True)
            out.append(f'<li id="{anchor}">{escape(note.text)}</li>')
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
            out.append(f'<li id="{anchor}">{escape(reference)}</li>')
        out.extend(["</ul>", "</section>"])
        return out

