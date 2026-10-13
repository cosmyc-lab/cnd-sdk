"""Inline rendering of rich text: one layer for every output dialect.

A ``RichText`` is a plain ``value`` plus standoff marks
(docs/proposals/0013). This module turns it into Markdown, HTML or plain
text, and every renderer and converter goes through it: none walks marks
on its own.

It cuts ``value`` at every mark boundary, and at every edge boundary
when the caller asks for edges to be wrapped (``edge_wrap``), and builds
a tree of nested spans. Where two spans cross, the one that ends first
closes and the other is reopened after it, as text editors do, so the
output always nests. The converters shipped today append their markers
after the block (see ``cnd.converters.base``) and pass no ``edge_wrap``:
an edge cut that renders nothing would only split marks for no reason.

Policy (spec §7): a dialect renders the marks it supports and leaves the
text of any other mark unchanged. ``value`` is always the plain text, so
dropping a mark never loses words.
"""

import unicodedata
from collections.abc import Callable
from dataclasses import dataclass, field
from html import escape as html_escape
from typing import Literal

from cnd.core.markdown_escape import escape_block
from cnd.core.text import ATOMIC_MARK_KINDS, Edge, Mark, RichText

InlineDialect = Literal["markdown", "html", "plain"]

EdgeWrap = Callable[[Edge], "tuple[str, str] | None"]
"""Given an edge, the text to put before and after the span it covers,
inserted verbatim; ``None`` leaves that edge out."""

_EDGE = "\x00edge"
"""The kind of an edge span; no mark kind can collide with it."""

HTML_TAGS = {
    "strong": "strong",
    "emph": "em",
    "code": "code",
    "strike": "s",
    "sup": "sup",
    "sub": "sub",
    "underline": "u",
    "highlight": "mark",
}
"""The HTML element of every known mark except ``math``."""

MARKDOWN_DELIMITERS = {"strong": "**", "emph": "*", "strike": "~~"}
"""Marks with a CommonMark or GFM delimiter. ``code`` and ``math`` are
atoms with their own syntax; the four others have no Markdown syntax."""

HTML_ONLY_MARKS = frozenset({"sup", "sub", "underline", "highlight"})
"""Marks Markdown can only show as inline HTML; the text-only option
drops them to plain text."""


@dataclass(eq=False)
class _Span:
    """A mark or a wrapped edge clamped to its text, compared by identity."""

    start: int
    end: int
    kind: str
    mark: Mark | None = None
    wrap: tuple[str, str] = ("", "")


@dataclass
class _Piece:
    """One rendered occurrence of a span: a mark split at a crossing
    yields several pieces. ``span`` is ``None`` for the root."""

    span: _Span | None
    start: int
    end: int = 0
    children: list["_Piece | tuple[int, int]"] = field(default_factory=list)


def render_inline(
    text: RichText,
    dialect: InlineDialect = "plain",
    *,
    escape: bool = False,
    text_only: bool = False,
    edge_wrap: EdgeWrap | None = None,
) -> str:
    """Render ``text`` with its marks in ``dialect``.

    - ``"plain"`` returns ``value``: every mark is dropped, and a ``math``
      mark keeps its readable ``value``.
    - ``"html"`` escapes the text and maps every known mark to its
      element; ``math`` becomes ``<code class="math">`` holding its source.
    - ``"markdown"`` follows spec §7. ``escape`` escapes the plain
      segments (never code or math) with ``escape_block``. ``text_only``
      drops ``sup``, ``sub``, ``underline`` and ``highlight`` to plain
      text and never falls back to an HTML tag.

    ``edge_wrap``, when given, wraps the span of every edge with a
    ``text_span`` in the strings it returns; edge spans nest and split
    like marks. ``"plain"`` ignores it.

    Unknown mark kinds render their covered text unchanged. Bounds are
    clamped, so an unvalidated text with a stray mark never raises.
    """
    if dialect == "plain":
        return text.value
    spans = _spans(text, dialect, text_only) + _edge_spans(text, edge_wrap)
    root = _tree(text.value, spans)
    if dialect == "html":
        return _render_html(text.value, root)
    return _MarkdownWriter(text.value, escape=escape, text_only=text_only).render(root)


def concat_texts(*parts: "str | RichText | None") -> RichText:
    """One ``RichText`` from several parts, marks shifted to the new
    offsets. Strings carry no marks; ``None`` parts are skipped. Edges are
    not carried: the result is for rendering, not for resolution."""
    value = ""
    marks: list[Mark] = []
    for part in parts:
        if part is None:
            continue
        if isinstance(part, str):
            value += part
            continue
        offset = len(value)
        marks.extend(
            mark.model_copy(update={"start": mark.start + offset, "end": mark.end + offset})
            for mark in part.marks
        )
        value += part.value
    return RichText(value=value, marks=marks)


def with_whole_mark(text: RichText, kind: str) -> RichText:
    """``text`` with one ``kind`` mark over all of it; the same-kind marks
    it already had merge into that one (Marks rule 3)."""
    if not text.value:
        return text
    marks = [mark for mark in text.marks if mark.kind != kind]
    marks.append(Mark(start=0, end=len(text.value), kind=kind))
    return text.model_copy(update={"marks": marks})


def _spans(text: RichText, dialect: InlineDialect, text_only: bool) -> list[_Span]:
    if dialect == "html":
        supported = set(HTML_TAGS) | {"math"}
    else:
        supported = set(MARKDOWN_DELIMITERS) | ATOMIC_MARK_KINDS
        if not text_only:
            supported |= HTML_ONLY_MARKS
    value = text.value
    spans: list[_Span] = []
    for mark in text.marks:
        if mark.kind not in supported:
            continue
        start, end = max(mark.start, 0), min(mark.end, len(value))
        if dialect == "markdown" and mark.kind not in ATOMIC_MARK_KINDS:
            # A delimiter next to a space never opens or closes: move the
            # span's outer whitespace outside it.
            while start < end and value[start].isspace():
                start += 1
            while end > start and value[end - 1].isspace():
                end -= 1
        if start < end:
            spans.append(_Span(start, end, mark.kind, mark))
    return spans


def _edge_spans(text: RichText, edge_wrap: EdgeWrap | None) -> list[_Span]:
    if edge_wrap is None:
        return []
    spans: list[_Span] = []
    for edge in text.edges():
        if not edge.text_span or len(edge.text_span) != 2:
            continue
        start = max(edge.text_span[0], 0)
        end = min(edge.text_span[1], len(text.value))
        wrap = edge_wrap(edge)
        if wrap is not None and start < end:
            spans.append(_Span(start, end, _EDGE, wrap=wrap))
    return spans


def _tree(value: str, spans: list[_Span]) -> _Piece:
    """Nest ``spans`` over ``value``; crossing spans are split."""
    atoms = [s for s in spans if s.kind in ATOMIC_MARK_KINDS]
    cuts = {0, len(value)}
    for span in spans:
        cuts.update((span.start, span.end))
    # An atom is verbatim: no cut falls inside it (Marks rule 4).
    cuts = sorted(c for c in cuts if not any(a.start < c < a.end for a in atoms))
    root = _Piece(span=None, start=0)
    stack = [root]
    for a, b in zip(cuts, cuts[1:]):
        active = [s for s in spans if s.start <= a and b <= s.end]
        keep = 1
        while keep < len(stack) and stack[keep].span in active:
            keep += 1
        for piece in stack[keep:]:
            piece.end = a
        del stack[keep:]
        open_spans = [p.span for p in stack[1:]]
        for span in sorted(
            (s for s in active if s not in open_spans),
            key=lambda s: (-s.end, s.kind in ATOMIC_MARK_KINDS, s.kind != _EDGE, s.kind),
        ):
            piece = _Piece(span=span, start=a)
            stack[-1].children.append(piece)
            stack.append(piece)
        stack[-1].children.append((a, b))
    for piece in stack[1:]:
        piece.end = len(value)
    root.end = len(value)
    return root


def _render_html(value: str, piece: _Piece) -> str:
    span = piece.span
    if span is not None and span.kind == "math":
        raw = span.mark.raw if span.mark is not None else None
        source = raw.value if raw is not None else value[piece.start : piece.end]
        return f'<code class="math">{html_escape(source)}</code>'
    if span is not None and span.kind == "code":
        return f"<code>{html_escape(value[piece.start : piece.end])}</code>"
    inner = "".join(
        html_escape(value[child[0] : child[1]])
        if isinstance(child, tuple)
        else _render_html(value, child)
        for child in piece.children
    )
    if span is None:
        return inner
    if span.kind == _EDGE:
        return f"{span.wrap[0]}{inner}{span.wrap[1]}"
    tag = HTML_TAGS[span.kind]
    return f"<{tag}>{inner}</{tag}>"


def _is_punct(ch: str | None) -> bool:
    return ch is not None and unicodedata.category(ch)[0] in "PS"


def _is_space(ch: str | None) -> bool:
    return ch is None or ch.isspace()


def _left_flanking(prev: str | None, nxt: str | None) -> bool:
    """CommonMark: a delimiter run that can open (prev/nxt are the
    characters around it; ``None`` is a line edge)."""
    if _is_space(nxt):
        return False
    return not _is_punct(nxt) or _is_space(prev) or _is_punct(prev)


def _right_flanking(prev: str | None, nxt: str | None) -> bool:
    """CommonMark: a delimiter run that can close."""
    if _is_space(prev):
        return False
    return not _is_punct(prev) or _is_space(nxt) or _is_punct(nxt)


class _MarkdownWriter:
    def __init__(self, value: str, *, escape: bool, text_only: bool) -> None:
        self.value = value
        self.escape = escape
        self.text_only = text_only

    def render(self, piece: _Piece) -> str:
        out: list[str] = []
        previous: tuple[_Piece, str] | None = None
        for child in piece.children:
            if isinstance(child, tuple):
                chunk = self.value[child[0] : child[1]]
                out.append(escape_block(chunk) if self.escape else chunk)
                previous = None
                continue
            touches_star = (
                previous is not None
                and previous[1].startswith("*")
                and previous[0].end == child.start
            )
            rendered, syntax = self._piece(child, touches_star)
            out.append(rendered)
            previous = (child, syntax)
        return "".join(out)

    def _piece(self, piece: _Piece, touches_star: bool) -> tuple[str, str]:
        """The piece rendered, and the syntax used (a delimiter, ``"<"``
        for an HTML tag, ``""`` for none)."""
        span = piece.span
        assert span is not None
        covered = self.value[piece.start : piece.end]
        if span.kind == "code":
            return _code_span(covered), "`"
        if span.kind == "math":
            raw = span.mark.raw if span.mark is not None else None
            source = raw.value if raw is not None else covered
            return f"${_one_line(source)}$", "$"
        inner = self.render(piece)
        if span.kind == _EDGE:
            return f"{span.wrap[0]}{inner}{span.wrap[1]}", ""
        delimiter = MARKDOWN_DELIMITERS.get(span.kind)
        if delimiter is not None and self._can_delimit(piece, inner, delimiter, touches_star):
            return f"{delimiter}{inner}{delimiter}", delimiter
        if self.text_only:
            return inner, ""
        tag = HTML_TAGS[span.kind]
        return f"<{tag}>{inner}</{tag}>", "<"

    def _can_delimit(
        self, piece: _Piece, inner: str, delimiter: str, touches_star: bool
    ) -> bool:
        """Whether ``delimiter`` around the piece parses back as this mark.

        It must open and close by CommonMark's flanking rules. Inside, the
        delimiter touches the first and last characters of the rendered
        ``inner``, which are a nested mark's own delimiter or tag when one
        opens or closes at the edge, or an escape; outside, it touches the
        characters around the piece in ``value``. A ``*`` opener never
        directly follows a ``*`` closer, since the two runs would merge
        into one.
        """
        if not inner or (touches_star and delimiter.startswith("*")):
            return False
        value = self.value
        prev = value[piece.start - 1] if piece.start > 0 else None
        first, last = inner[0], inner[-1]
        nxt = value[piece.end] if piece.end < len(value) else None
        return _left_flanking(prev, first) and _right_flanking(last, nxt)


def _one_line(text: str) -> str:
    """Verbatim inline content on one line: a newline inside a code span
    or a formula would otherwise let the next line start a block."""
    return text.replace("\r\n", " ").replace("\r", " ").replace("\n", " ")


def _code_span(text: str) -> str:
    """A CommonMark code span holding ``text`` verbatim: the backtick run
    is longer than any run inside, and a space pads content that starts
    or ends with a backtick, or with a space on both sides."""
    text = _one_line(text)
    longest = run = 0
    for ch in text:
        run = run + 1 if ch == "`" else 0
        longest = max(longest, run)
    fence = "`" * (longest + 1)
    pad = text.startswith("`") or text.endswith("`") or (
        text.startswith(" ") and text.endswith(" ") and text.strip() != ""
    )
    space = " " if pad else ""
    return f"{fence}{space}{text}{space}{fence}"
