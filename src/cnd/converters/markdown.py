"""cnd -> markdown: a whole ``Cnd`` as one complete ``.md`` document.

Target 1 of docs/proposals/0007, built directly on
``cnd.core.render.MarkdownRenderer``.
"""

from cnd.core.cnd import BibEntry, Cnd, DocMetadata, Footnote
from cnd.core.render import MarkdownRenderer, NodeRenderer

from cnd.converters.base import (
    CndConverter,
    ConversionResult,
    ResolvedMarker,
    format_date,
    iter_body,
    resolve_markers,
)

__all__ = ["MarkdownConverter", "format_bib_entry"]


def format_bib_entry(entry: BibEntry) -> tuple[str, str | None]:
    """The reference string for ``entry``, plus a warning when composed.

    **This is not a citation-style implementation.** ``formatted`` — the
    reference string as it was displayed in the built document, produced
    by whatever style engine the producer ran — is preferred whenever it
    is present, and is emitted verbatim.

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
    if entry.formatted:
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
        return entry.label, warning
    return ". ".join(parts), warning


class MarkdownConverter(CndConverter):
    """Convert a whole ``Cnd`` into one standalone Markdown document.

    Output shape, all of it **non-normative** (spec §7):

    - YAML front matter from ``cnd.doc`` (title, authors, date, keywords,
      description, lang) plus ``cnd_version`` and ``built_at``.
    - The body, assembled by walking the tree in reading order and
      delegating each node to the injected ``NodeRenderer``. Figures are
      rendered once, by the renderer, from the wrapper node; the walk
      does not descend into them.
    - A footnotes section (``[^label]: text``) and a bibliography section,
      both emitted from the pools in pool order — pools are out of tree
      and out of reading order (spec §8).
    - Per-node markers appended on their own line under each block:
      ``[label]`` for ``refs``, pandoc-style ``[@label]`` / ``@label``
      for ``cites``, ``[^label]`` for ``footnotes``. Markers are ordered
      by ``text_span`` where one exists, then by family (spec §8).

    The default renderer is ``MarkdownRenderer(tables="inline",
    figures="inline")``: a standalone document wants its content, not the
    ``[[figure:…]]`` placeholders that serve chunking pipelines. Inject
    another renderer to change that.

    **Irreducibly dropped** — properties of Markdown as a target, the
    same for every document (docs/proposals/0007):

    - ``text_span`` — markers are appended under the block, not spliced
      into the text at their standoff offsets, so marker *position*
      inside a node's text is lost. Their relative order is preserved.
    - ``CiteRef.form`` — only the ``none`` (silent citation) and
      prose-vs-bracketed distinctions survive; ``full``, ``author`` and
      ``year`` collapse into their neighbours.
    - ``state_metadata`` on every node, and ``NodeLocation.page``:
      Markdown has no page model and no place for producer state.
    - Node ``id`` and ``label``: Markdown has no element identity, so
      cross-reference markers degrade to plain bracketed labels rather
      than links.
    - ``RawSource`` (``raw`` on table, math, figure) and
      ``BibEntry.fields``: the producer's verbatim source and the full
      structured bibliography entry have no Markdown target.
    - Whatever the injected renderer itself drops — ``MarkdownRenderer``
      drops heading ``number``/``counter_label``, for instance.

    This conversion does **not** round-trip. Nothing reconstructs a CND
    from the Markdown it produces.
    """

    extension = "md"
    media_type = "text/markdown"

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
        return MarkdownRenderer(tables="inline", figures="inline")

    def convert(self, cnd: Cnd) -> ConversionResult:
        warnings: list[str] = []
        sections = [
            self._front_matter(cnd),
            self._body(cnd, warnings),
            self._footnotes_section(cnd),
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
        lines.append(f"cnd_version: {_yaml_scalar(cnd.cnd_version)}")
        lines.append(f"built_at: {_yaml_scalar(cnd.built_at.isoformat())}")
        lines.append("---")
        return "\n".join(lines)

    # -- body -----------------------------------------------------------

    def _body(self, cnd: Cnd, warnings: list[str]) -> str:
        blocks: list[str] = []
        for visit in iter_body(cnd):
            rendered = self.renderer.render(visit.node).strip()
            markers = self._marker_line(cnd, visit.node, warnings)
            if markers and rendered:
                rendered = f"{rendered}\n{markers}"
            elif markers:
                rendered = markers
            if rendered:
                blocks.append(rendered)
        return "\n\n".join(blocks)

    def _marker_line(self, cnd: Cnd, node, warnings: list[str]) -> str:
        markers = resolve_markers(cnd, node, warnings)
        rendered = [self._marker(marker) for marker in markers]
        return " ".join(part for part in rendered if part)

    @staticmethod
    def _marker(marker: ResolvedMarker) -> str:
        if marker.family == "refs":
            return f"[{marker.label}]"
        if marker.family == "footnotes":
            return f"[^{marker.label}]"
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

    def _footnotes_section(self, cnd: Cnd) -> str:
        if not cnd.footnotes:
            return ""
        lines = [f"## {self.footnotes_title}", ""]
        lines.extend(_footnote_definition(note) for note in cnd.footnotes)
        return "\n".join(lines)

    def _bibliography_section(self, cnd: Cnd, warnings: list[str]) -> str:
        if not cnd.bibliography:
            return ""
        lines = [f"## {self.bibliography_title}", ""]
        for entry in cnd.bibliography:
            reference, warning = format_bib_entry(entry)
            if warning:
                warnings.append(warning)
            lines.append(f"- **{entry.label}** — {reference}")
        return "\n".join(lines)


def _footnote_definition(note: Footnote) -> str:
    text = note.text.replace("\n", "\n    ")
    return f"[^{note.label}]: {text}"


def _yaml_scalar(value: str) -> str:
    """Always-quoted YAML double-quoted scalar.

    Quoting unconditionally sidesteps the whole plain-scalar minefield
    (leading ``@``, a colon, ``yes``/``no``) without pulling in a YAML
    library — the SDK's dependency floor is deliberate.
    """
    escaped = value.replace("\\", "\\\\").replace('"', '\\"')
    escaped = escaped.replace("\n", "\\n").replace("\r", "\\r").replace("\t", "\\t")
    return f'"{escaped}"'
