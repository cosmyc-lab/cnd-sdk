"""The builder — compiles a declaration into a CND (docs/adr/0019).

This is the declarative door's enforcement bottleneck: a producer that
goes through a declaration *cannot* bypass it, which is the door's whole
guarantee (well-formedness, not truth — ADR 0019). Enforcement is
build-then-validate: the transcription below derives what the
declaration deliberately omits, then ``cnd.core.validate.validate``
runs on the result, so the referential invariants stay implemented in
exactly one place ("detected by the builder at build time and by
``validate()``" — ADR 0019 §4 — is literally the same code).

``build`` is a pure value function — declaration in, CND out — so it
crosses any language boundary (ADR 0019 §5).

**What the builder derives** (spec §12): every ``id`` (minted, not
durable — ADR 0015), ``built_at``, ``cnd_version``, ``heading_path``
(ancestor headings plus the heading itself; an element is
``"{number} {text}"`` when numbered, bare ``text`` otherwise), and the
resolved ordinals of ordered-list items. ``location`` is never set — a
declaration is unpaginated by construction. ``text`` passes through
byte-for-byte: an edge's ``text_span`` indexes into it, and any
normalization silently shifts every span.

**List ordinals** resolve independently of ``numbering`` — a markdown
ordered list genuinely carries its numbers. The rule is the one pinned
on ``DeclListItem``: no override → previous sibling's number plus one,
from 1; an override is taken verbatim and **rebases** the rest of the
list. Overrides on an unordered list are dropped.

**The counter engine is opt-in** (``numbering=True``) because the
declarative door serves unnumbered sources — markdown, hand authors —
and inventing "2.1.1" there manufactures presentation state, the
buildable-but-false trap ADR 0019 names. When it runs it applies one
fixed house style, deliberately without options (the declarative door
has no style engine):

- headings: one counter per level; entering level *n* increments it and
  resets deeper levels; ``number`` is the dotted join of levels 1..*n*,
  and a skipped level shows ``0`` (``1.0.1``) rather than being papered
  over;
- figures: one counter per kind, ``kind=None`` resolved from the first
  child's type (the renderer's own inference); bare ordinal (``"3"``);
- math: one document counter, **block** math only; ``"(1)"``.

``counter_label`` is never invented: a wrong-language "Figure" on a
French document is worse than no word, so only authored values pass
through (proposal 0010).
"""

import re
from datetime import datetime, timezone
from uuid import uuid4

from cnd.core.cnd import CND_VERSION, BibEntry, Cnd, Footnote
from cnd.core.nodes import (
    CndNode,
    CodeNode,
    FigureNode,
    HeadingNode,
    ImageNode,
    ListItem,
    ListNode,
    MathNode,
    ParagraphNode,
    QuoteNode,
    TableNode,
    TermsNode,
)
from cnd.core.validate import Violation, validate
from cnd.declaration import (
    DECLARATION_VERSION,
    Declaration,
    DeclCodeNode,
    DeclFigureNode,
    DeclHeadingNode,
    DeclImageNode,
    DeclListItem,
    DeclListNode,
    DeclMathNode,
    DeclNodeBase,
    DeclParagraphNode,
    DeclQuoteNode,
    DeclTableNode,
    DeclTermsNode,
)


class BuildError(Exception):
    """A declaration that cannot become a valid CND.

    Carries the full violation list — a producer wants everything wrong,
    not the first failure — mirroring ``validate()``'s return-all
    contract in exception form (a build cannot half-succeed, so an
    exception is honest where a partial return would not be).
    """

    def __init__(self, violations: list[Violation]) -> None:
        self.violations = violations
        super().__init__("; ".join(str(v) for v in violations))


def build(decl: Declaration, *, numbering: bool = False) -> Cnd:
    """Compile ``decl`` into a valid CND, or raise ``BuildError``.

    ``numbering`` opts into the counter engine (module docstring); off,
    every ``number`` the engine would resolve stays ``None``.
    """
    if decl.declaration_version != DECLARATION_VERSION:
        raise BuildError(
            [
                Violation(
                    "declaration-version-unsupported",
                    f"this builder supports declaration_version "
                    f"{DECLARATION_VERSION}",
                    f"declaration_version {decl.declaration_version}",
                )
            ]
        )

    counters = _Counters() if numbering else None
    cnd = Cnd(
        cnd_version=CND_VERSION,
        built_at=datetime.now(timezone.utc),
        source=decl.source,
        doc=decl.doc,
        nodes=[_node(child, [], counters) for child in decl.nodes],
        bibliography=[
            BibEntry(id=uuid4(), **entry.model_dump())
            for entry in decl.bibliography
        ],
        footnotes=[
            Footnote(id=uuid4(), **note.model_dump())
            for note in decl.footnotes
        ],
    )

    violations = validate(cnd)
    if violations:
        raise BuildError(_relabel(violations, cnd))
    return cnd


def _base(node: DeclNodeBase) -> dict:
    """The ``NodeBase`` fields of a transcribed node: a fresh id, the
    authored identity and link families verbatim, and never a location."""
    return {
        "id": uuid4(),
        "label": node.label,
        "refs": node.refs,
        "cites": node.cites,
        "footnotes": node.footnotes,
        "state_metadata": node.state_metadata,
        "location": None,
    }


def _node(
    node: DeclNodeBase,
    heading_path: list[str],
    counters: "_Counters | None",
) -> CndNode:
    """Transcribe one declaration node (and its subtree) into a CND node."""
    match node:
        case DeclHeadingNode():
            number = counters.heading(node.level) if counters else None
            element = f"{number} {node.text}" if number else node.text
            path = [*heading_path, element]
            return HeadingNode(
                type="heading",
                level=node.level,
                number=number,
                counter_label=node.counter_label,
                text=node.text,
                heading_path=path,
                children=[_node(c, path, counters) for c in node.children],
                **_base(node),
            )
        case DeclParagraphNode():
            return ParagraphNode(
                type="paragraph", text=node.text, lang=node.lang, **_base(node)
            )
        case DeclTableNode():
            return TableNode(
                type="table",
                kind=node.kind,
                content_kind=node.content_kind,
                cells=node.cells,
                raw=node.raw,
                **_base(node),
            )
        case DeclQuoteNode():
            return QuoteNode(
                type="quote",
                text=node.text,
                attribution=node.attribution,
                block=node.block,
                lang=node.lang,
                **_base(node),
            )
        case DeclCodeNode():
            return CodeNode(
                type="code",
                text=node.text,
                lang=node.lang,
                block=node.block,
                **_base(node),
            )
        case DeclMathNode():
            number = (
                counters.math() if counters is not None and node.block else None
            )
            return MathNode(
                type="math",
                text=node.text,
                raw=node.raw,
                number=number,
                counter_label=node.counter_label,
                block=node.block,
                **_base(node),
            )
        case DeclFigureNode():
            number = (
                counters.figure(_figure_counter_kind(node)) if counters else None
            )
            return FigureNode(
                type="figure",
                kind=node.kind,
                caption=node.caption,
                number=number,
                counter_label=node.counter_label,
                children=[
                    _node(c, heading_path, counters) for c in node.children
                ],
                raw=node.raw,
                **_base(node),
            )
        case DeclImageNode():
            return ImageNode(
                type="image", path=node.path, alt=node.alt, **_base(node)
            )
        case DeclListNode():
            return ListNode(
                type="list",
                ordered=node.ordered,
                tight=node.tight,
                items=_items(node.items, ordered=node.ordered),
                **_base(node),
            )
        case DeclTermsNode():
            return TermsNode(
                type="terms", tight=node.tight, items=node.items, **_base(node)
            )
        case _:  # pragma: no cover — the discriminated union is closed
            raise TypeError(f"unknown declaration node type: {type(node)!r}")


def _items(items: list[DeclListItem], *, ordered: bool) -> list[ListItem]:
    """Resolve list ordinals per the rule pinned on ``DeclListItem``.

    Ordered: no override → previous + 1 (from 1); an override is taken
    verbatim and rebases the rest. Unordered: ordinals do not exist, so
    overrides are dropped. Each nesting level counts on its own.
    """
    resolved: list[ListItem] = []
    current = 0
    for item in items:
        if ordered:
            current = item.number if item.number is not None else current + 1
            number: int | None = current
        else:
            number = None
        resolved.append(
            ListItem(
                text=item.text,
                number=number,
                children=_items(item.children, ordered=ordered),
            )
        )
    return resolved


def _figure_counter_kind(node: DeclFigureNode) -> str:
    """The counter a figure draws from: its authored ``kind``, else the
    first child's type — the same inference the markdown renderer applies
    (``MarkdownRenderer._infer_figure_kind``) — else ``"figure"``."""
    if node.kind:
        return node.kind
    for child in node.children:
        return child.type
    return "figure"


class _Counters:
    """The counter engine's running state (module docstring, house style)."""

    def __init__(self) -> None:
        self._heading: list[int] = []
        self._figure: dict[str, int] = {}
        self._math = 0

    def heading(self, level: int) -> str:
        while len(self._heading) < level:
            self._heading.append(0)
        del self._heading[level:]
        self._heading[level - 1] += 1
        return ".".join(str(count) for count in self._heading)

    def figure(self, kind: str) -> str:
        self._figure[kind] = self._figure.get(kind, 0) + 1
        return str(self._figure[kind])

    def math(self) -> str:
        self._math += 1
        return f"({self._math})"


_UUID_RE = re.compile(
    r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}"
)


def _relabel(violations: list[Violation], cnd: Cnd) -> list[Violation]:
    """Rewrite violations label-first for the declaration's author.

    ``validate()`` names nodes by minted UUID — correct for a CND, noise
    for an author who never wrote one. Each UUID becomes ``@label`` when
    the node has one, else its reading-order position (``#7``), which is
    a handle the author can find in their own source.
    """
    handles: dict[str, str] = {}
    # No current rule names the document itself, but a future one might —
    # leak-proofing so that UUID would still relabel cleanly.
    handles[str(cnd.id)] = "the document"
    for visit in cnd.iter():
        node = visit.node
        handles[str(node.id)] = (
            f"@{node.label}" if node.label else f"#{visit.ctx.doc_index}"
        )
    for entry in (*cnd.bibliography, *cnd.footnotes):
        handles[str(entry.id)] = f"@{entry.label}"

    def _sub(match: re.Match[str]) -> str:
        return handles.get(match.group(0), match.group(0))

    return [
        Violation(
            violation.rule,
            _UUID_RE.sub(_sub, violation.message),
            _UUID_RE.sub(_sub, violation.where),
        )
        for violation in violations
    ]
