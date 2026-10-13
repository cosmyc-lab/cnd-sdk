"""cnd -> markdown: a whole ``Cnd`` as one complete ``.md`` document.

Target 1 of docs/proposals/0007, built directly on
``cnd.core.render.MarkdownRenderer``.
"""

from cnd.core.cnd import BibEntry, Cnd, DocMetadata, Footnote
from cnd.core.markdown_escape import escape_destination, escape_inline
from cnd.core.nodes import CndNode, HeadingNode, ParagraphNode
from cnd.core.render import MarkdownRenderer, NodeRenderer, expand_headings
from cnd.core.text import RichText
from cnd.core.urls import is_safe_url

from cnd.converters.base import (
    CndConverter,
    ConversionResult,
    ResolvedMarker,
    format_date,
    iter_body,
    resolve_markers,
)

__all__ = ["MarkdownConverter", "format_bib_entry"]


def format_bib_entry(entry: BibEntry) -> tuple[RichText, str | None]:
    """The reference text for ``entry``, plus a warning when composed.

    The caller renders the returned ``RichText`` in its own dialect
    (``NodeRenderer.render_text``), which is how a journal title set in
    italics stays italic.

    **This is not a citation-style implementation.** ``formatted`` — the
    reference as it was displayed in the built document, produced by
    whatever style engine the producer ran — is preferred whenever it is
    present, and is returned verbatim, marks included.

    Since CND 0.3.0 ``formatted`` is nullable: a hand author or a
    markdown producer has no style engine and emits structured fields
    only. For that case this composes a deliberately minimal string from
    the lifted fields (``authors``, ``year``, ``title``, ``container``,
    ``doi``, ``url``) joined with ``". "``. It follows **no** citation
    style — not APA, not Chicago, not CSL — it makes no attempt to, and
    the ``fields`` blob (a full Hayagriva-style entry, say) is not read
    at all. Turning structured fields into a styled reference is a style
    engine's job and is out of scope for the SDK (docs/proposals/0007).
    Callers who need real styling must run one and set ``formatted``.
    """
    if entry.formatted is not None and entry.formatted.value:
        return entry.formatted, None
    parts: list[str] = []
    if entry.authors:
        parts.append(", ".join(entry.authors))
    if entry.year is not None:
        parts.append(f"({entry.year})")
    if entry.title:
        parts.append(entry.title)
    if entry.container:
        parts.append(entry.container)
    if entry.doi:
        parts.append(f"doi:{entry.doi}")
    if entry.url:
        parts.append(entry.url)
    warning = (
        f"bibliography entry {entry.label!r} has no 'formatted' string; "
        f"composed a minimal unstyled reference from the lifted fields"
    )
    if not parts:
        return RichText(value=entry.label), warning
    return RichText(value=". ".join(parts)), warning


class MarkdownConverter(CndConverter):
    """Convert a whole ``Cnd`` into one standalone Markdown document.

    Output shape, all of it **non-normative** (spec §7):

    - YAML front matter from ``cnd.doc`` (title, authors, date, keywords,
      description, lang, status, version, and ``extra`` as a mapping)
      plus ``cnd_version`` and ``built_at``.
    - The body, assembled by walking the tree in reading order and
      delegating each block to the injected ``NodeRenderer``. A container
      (figure, list, table, quote…) renders once, from the container
      node; only headings are descended into.
    - A footnotes section (``[^label]: …``, further blocks indented four
      spaces) and a bibliography section, both emitted from the pools in
      pool order — pools are out of tree and out of reading order
      (spec §8). Footnote blocks and references go through the renderer,
      like the body.
    - Per-block markers appended on their own line under each block, for
      the edges of every text in the block: ``[label]`` for ``refs``,
      pandoc-style ``[@label]`` / ``@label`` for ``cites``, ``[^label]``
      for ``footnotes``, and ``[href](href)`` for ``links`` — the href is
      the only text a ``LinkRef`` carries, so it stands in for the display
      text a Markdown link normally has. An href whose scheme is not
      ``http``, ``https`` or ``mailto`` (``cnd.core.urls.is_safe_url``)
      is written as plain text, never as a link. Markers are ordered text by text,
      then by ``text_span`` where one exists, then by family (spec §8). A
      ``links`` marker is **appended**, like the other three families,
      never spliced into the text at its span: splicing would make marker
      position renderer-specific again and would rewrite every existing
      golden document for a change that only one family needs.

    The default renderer is ``MarkdownRenderer(tables="inline",
    figures="inline", escape=True, heading_numbers=True)``: a standalone
    document wants its content, not the ``[[figure:…]]`` placeholders
    that serve chunking pipelines. It escapes free text so that a
    Markdown parser reads the structure the CND has and not structure
    the prose happens to spell; code and math are emitted verbatim. It
    keeps heading numbering as a prefix on the heading line.
    ``text_only=True`` makes it a Markdown output with no HTML at all
    (see ``MarkdownRenderer``). Inject another renderer to change any of
    that; ``text_only`` then belongs to the renderer you inject.

    **Irreducibly dropped** — properties of Markdown as a target, the
    same for every document (docs/proposals/0007):

    - ``text_span`` — markers are appended under the block, not spliced
      into the text at their standoff offsets, so marker *position*
      inside a text is lost. Their relative order is preserved.
      This holds for ``links`` exactly as it does for the other three
      families.
    - ``CiteRef.form`` — only the ``none`` (silent citation) and
      prose-vs-bracketed distinctions survive; ``full``, ``author`` and
      ``year`` collapse into their neighbours.
    - ``state_metadata`` on every node, and ``NodeLocation.page``:
      Markdown has no page model and no place for producer state.
    - Node ``id`` and ``label``: Markdown has no element identity, so
      cross-reference markers degrade to plain bracketed labels rather
      than links.
    - ``RawSource`` (``raw`` on math, figure and a ``math`` mark) and
      ``BibEntry.fields``: the producer's verbatim source and the full
      structured bibliography entry have no Markdown target, except that
      a ``math`` mark renders its source between ``$`` and a ``math``
      block its source in a ``math`` fence.
    - Whatever the injected renderer itself drops.

    This conversion does **not** round-trip. Nothing reconstructs a CND
    from the Markdown it produces.
    """

    extension = "md"
    media_type = "text/markdown"

    def __init__(
        self,
        renderer: NodeRenderer | None = None,
        *,
        text_only: bool = False,
        footnotes_title: str = "Footnotes",
        bibliography_title: str = "Bibliography",
    ) -> None:
        if renderer is not None and text_only:
            raise ValueError("text_only shapes the default renderer; set it on the renderer you inject")
        super().__init__(renderer if renderer is not None else self.default_renderer(text_only=text_only))
        self.footnotes_title = footnotes_title
        self.bibliography_title = bibliography_title

    @classmethod
    def default_renderer(cls, *, text_only: bool = False) -> NodeRenderer:
        return MarkdownRenderer(
            tables="inline",
            figures="inline",
            escape=True,
            heading_numbers=True,
            text_only=text_only,
        )

    def convert(self, cnd: Cnd) -> ConversionResult:
        warnings: list[str] = []
        sections = [
            self._front_matter(cnd),
            self._body(cnd, warnings),
            self._footnotes_section(cnd, warnings),
            self._bibliography_section(cnd, warnings),
        ]
        text = "\n\n".join(section for section in sections if section)
        return ConversionResult(text=text + "\n", warnings=tuple(warnings))

    # -- front matter ---------------------------------------------------

    def _front_matter(self, cnd: Cnd) -> str:
        doc: DocMetadata = cnd.doc
        lines = ["---", f"title: {_yaml_scalar(doc.title)}"]
        if doc.authors:
            lines.append("authors:")
            lines.extend(f"  - {_yaml_scalar(author)}" for author in doc.authors)
        if doc.date is not None:
            lines.append(f"date: {format_date(doc.date)}")
        if doc.keywords:
            lines.append("keywords:")
            lines.extend(f"  - {_yaml_scalar(keyword)}" for keyword in doc.keywords)
        if doc.description:
            lines.append(f"description: {_yaml_scalar(doc.description)}")
        if doc.lang:
            lines.append(f"lang: {_yaml_scalar(doc.lang)}")
        if doc.status:
            lines.append(f"status: {_yaml_scalar(doc.status)}")
        if doc.version:
            lines.append(f"version: {_yaml_scalar(doc.version)}")
        if doc.extra:
            lines.append("extra:")
            lines.extend(
                f"  {_yaml_scalar(key)}: {_yaml_scalar(value)}"
                for key, value in doc.extra.items()
            )
        lines.append(f"cnd_version: {_yaml_scalar(cnd.cnd_version)}")
        lines.append(f"built_at: {_yaml_scalar(cnd.built_at.isoformat())}")
        lines.append("---")
        return "\n".join(lines)

    # -- body -----------------------------------------------------------

    def _body(self, cnd: Cnd, warnings: list[str]) -> str:
        blocks = [self._block(cnd, visit.node, warnings) for visit in iter_body(cnd)]
        return "\n\n".join(block for block in blocks if block)

    def _block(self, cnd: Cnd, node: CndNode, warnings: list[str]) -> str:
        """One block and, on its own line under it, its markers."""
        rendered = self.renderer.render(node).strip()
        markers = self._marker_line(cnd, node, warnings)
        if markers and rendered:
            # Only a paragraph or a heading takes its markers on the next
            # line. Under any other block (list, table, quote, admonition,
            # figure, code, math) a bare next line would read as a table
            # row or a lazy continuation, so a blank line separates them.
            tight = isinstance(node, (ParagraphNode, HeadingNode))
            return f"{rendered}{chr(10) if tight else chr(10) * 2}{markers}"
        return markers or rendered

    def _marker_line(self, cnd: Cnd, node: CndNode, warnings: list[str]) -> str:
        rendered = [self._marker(marker) for marker in resolve_markers(cnd, node, warnings)]
        return " ".join(part for part in rendered if part)

    @staticmethod
    def _marker(marker: ResolvedMarker) -> str:
        if marker.family == "refs":
            return f"[{marker.label}]"
        if marker.family == "footnotes":
            return f"[^{marker.label}]"
        if marker.family == "links":
            href = marker.link.href
            if not is_safe_url(href):
                return escape_inline(href)
            return f"[{escape_inline(href)}]({escape_destination(href)})"
        form = getattr(marker.link, "form", None)
        supplement = getattr(marker.link, "supplement", None)
        if form == "none":
            return ""
        if form in ("prose", "author", "year"):
            base = f"@{marker.label}"
            return f"{base} [{supplement}]" if supplement else base
        inner = f"@{marker.label}"
        if supplement:
            inner = f"{inner}, {supplement}"
        return f"[{inner}]"

    # -- pools ----------------------------------------------------------

    def _footnotes_section(self, cnd: Cnd, warnings: list[str]) -> str:
        if not cnd.footnotes:
            return ""
        lines = [f"## {self.footnotes_title}", ""]
        lines.extend(self._footnote_definition(cnd, note, warnings) for note in cnd.footnotes)
        return "\n".join(lines)

    def _footnote_definition(self, cnd: Cnd, note: Footnote, warnings: list[str]) -> str:
        """``[^label]: first block``; every further line is indented four
        spaces, so several blocks stay inside the one footnote."""
        blocks = [self._block(cnd, child, warnings) for child in expand_headings(note.children)]
        body = "\n\n".join(block for block in blocks if block)
        lines = body.split("\n")
        rest = [f"    {line}" if line else "" for line in lines[1:]]
        return "\n".join([f"[^{note.label}]: {lines[0]}".rstrip(), *rest])

    def _bibliography_section(self, cnd: Cnd, warnings: list[str]) -> str:
        if not cnd.bibliography:
            return ""
        lines = [f"## {self.bibliography_title}", ""]
        for entry in cnd.bibliography:
            reference, warning = format_bib_entry(entry)
            if warning:
                warnings.append(warning)
            lines.append(f"- **{entry.label}** — {self.renderer.render_text(reference)}")
        return "\n".join(lines)


def _yaml_scalar(value: str) -> str:
    """Always-quoted YAML double-quoted scalar.

    Quoting unconditionally sidesteps the whole plain-scalar minefield
    (leading ``@``, a colon, ``yes``/``no``) without pulling in a YAML
    library — the SDK's dependency floor is deliberate.
    """
    escaped = value.replace("\\", "\\\\").replace('"', '\\"')
    escaped = escaped.replace("\n", "\\n").replace("\r", "\\r").replace("\t", "\\t")
    return f'"{escaped}"'
