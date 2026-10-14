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

**What the builder derives** (spec §12): every ``id`` — body nodes,
nodes inside list items, term items, cells and footnotes, and pool
entries (minted, not durable — ADR 0015) — ``built_at``, ``cnd_version``,
``heading_path`` (ancestor headings plus the heading itself; an element
is ``"{value} {text}"`` when numbered, the bare text otherwise, always
the plain ``RichText.value``), the resolved ordinals of ordered-list
items, and ``numbering.value``. ``location`` is never set — a
declaration is unpaginated by construction. Every ``RichText.value``
passes through byte-for-byte: marks and ``text_span`` index into it, and
any normalization silently shifts every span.

**List ordinals** resolve independently of the counter engine — a
markdown ordered list genuinely carries its numbers. The rule is the one
pinned on ``DeclListItem``: no override → previous sibling's number plus
one, from 1; an override is taken verbatim and **rebases** the rest of
the list. Overrides on an unordered list are dropped.

**The counter engine is opt-in** (``numbering=True``) because the
declarative door serves unnumbered sources — markdown, hand authors —
and inventing "2.1.1" there manufactures presentation state, the
buildable-but-false trap ADR 0019 names. When it runs it numbers every
heading, figure and equation, in full-walk order (the body, then each
footnote's content, spec §8), with one fixed house style, deliberately
without options (the declarative door has no style engine):

- headings: one counter per level; entering level *n* increments it and
  resets deeper levels; the value is the dotted join of levels 1..*n*,
  and a skipped level shows ``0`` (``1.0.1``) rather than being papered
  over;
- figures: one counter per kind, ``kind=None`` resolved from the first
  child's type (the renderer's own inference); bare ordinal (``"3"``);
- math: one document counter, ``"(1)"``. Every ``math`` node is a block
  in 0.5; inline math is a mark and is never numbered.

``numbering.name`` is never invented: a wrong-language "Figure" on a
French document is worse than no word, so only the authored word passes
through. With the engine off, a node that authors ``numbering`` cannot be
built: a CND cannot carry a word without a value (docs/proposals/0013,
"Numbering"), and dropping an authored word silently is what the
declaration refuses everywhere else. That is a ``BuildError``
(``numbering-without-engine``).
"""

import re
from datetime import datetime, timezone
from uuid import uuid4

from cnd.core.cnd import CND_VERSION, BibEntry, Cnd, Footnote
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
    Numbering,
    ParagraphNode,
    QuoteNode,
    TableNode,
    TermItem,
    TermsNode,
)
from cnd.core.text import RichText
from cnd.core.validate import Violation, validate
from cnd.declaration import (
    DECLARATION_VERSION,
    DeclAdmonitionNode,
    DeclCell,
    DeclCodeNode,
    Declaration,
    DeclFigureNode,
    DeclHeadingNode,
    DeclImageNode,
    DeclLayoutNode,
    DeclListItem,
    DeclListNode,
    DeclMathNode,
    DeclNodeBase,
    DeclNumbering,
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
    every ``numbering`` stays ``None`` and an authored one is an error.
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

    # The CND never shares a mutable object with the declaration it came
    # from: source, doc, raw and every state_metadata would otherwise be
    # the very objects the caller still holds, and editing the declaration
    # after a build would silently edit the CND too.
    decl = decl.model_copy(deep=True)

    builder = _Builder(numbering)
    # Body first, then the footnotes in pool order: the full walk (spec
    # §8), so the engine's counters run in the one order a CND defines.
    nodes = [builder.node(child, []) for child in decl.nodes]
    footnotes = [
        Footnote(
            id=uuid4(),
            label=note.label,
            children=[builder.node(child, []) for child in note.children],
        )
        for note in decl.footnotes
    ]
    cnd = Cnd(
        cnd_version=CND_VERSION,
        built_at=datetime.now(timezone.utc),
        source=decl.source,
        doc=decl.doc,
        nodes=nodes,
        bibliography=[
            BibEntry(id=uuid4(), **entry.model_dump())
            for entry in decl.bibliography
        ],
        footnotes=footnotes,
    )

    violations = builder.violations + validate(cnd)
    if violations:
        raise BuildError(_relabel(violations, cnd))
    return cnd


class _Builder:
    """One build's transcription state: the counters, when the engine
    runs, and the violations only the transcription can see."""

    def __init__(self, numbering: bool) -> None:
        self.counters = _Counters() if numbering else None
        self.violations: list[Violation] = []

    def node(self, node: DeclNodeBase, heading_path: list[str]) -> CndNode:
        """Transcribe one declaration node and its subtree.

        ``heading_path`` is the path of the nearest enclosing heading; it
        is threaded through every container, so a heading inside a list
        item or a cell still knows its ancestors.
        """
        base = _base(node)
        match node:
            case DeclHeadingNode():
                resolved = self._numbering(
                    node, base, lambda c: c.heading(node.level)
                )
                element = (
                    f"{resolved.value} {node.text.value}"
                    if resolved
                    else node.text.value
                )
                path = [*heading_path, element]
                return HeadingNode(
                    type="heading",
                    level=node.level,
                    numbering=resolved,
                    text=_text(node.text),
                    heading_path=path,
                    children=self.nodes(node.children, path),
                    **base,
                )
            case DeclParagraphNode():
                return ParagraphNode(type="paragraph", text=_text(node.text), **base)
            case DeclQuoteNode():
                return QuoteNode(
                    type="quote",
                    attribution=_text(node.attribution),
                    children=self.nodes(node.children, heading_path),
                    **base,
                )
            case DeclCodeNode():
                return CodeNode(
                    type="code",
                    text=node.text,
                    lang=node.lang,
                    title=node.title,
                    **base,
                )
            case DeclMathNode():
                return MathNode(
                    type="math",
                    text=node.text,
                    raw=node.raw,
                    numbering=self._numbering(node, base, lambda c: c.math()),
                    **base,
                )
            case DeclImageNode():
                return ImageNode(type="image", path=node.path, alt=node.alt, **base)
            case DeclFigureNode():
                kind = _figure_counter_kind(node)
                return FigureNode(
                    type="figure",
                    kind=node.kind,
                    caption=_text(node.caption),
                    description=_text(node.description),
                    numbering=self._numbering(node, base, lambda c: c.figure(kind)),
                    children=self.nodes(node.children, heading_path),
                    raw=node.raw,
                    **base,
                )
            case DeclAdmonitionNode():
                return AdmonitionNode(
                    type="admonition",
                    kind=node.kind,
                    title=_text(node.title),
                    children=self.nodes(node.children, heading_path),
                    **base,
                )
            case DeclListNode():
                return ListNode(
                    type="list",
                    ordered=node.ordered,
                    items=self._items(node.items, node.ordered, heading_path),
                    **base,
                )
            case DeclTermsNode():
                return TermsNode(
                    type="terms",
                    items=[
                        TermItem(
                            term=_text(item.term),
                            children=self.nodes(item.children, heading_path),
                        )
                        for item in node.items
                    ],
                    **base,
                )
            case DeclTableNode():
                return TableNode(
                    type="table",
                    kind=node.kind,
                    cells=self._cells(node.cells, heading_path),
                    **base,
                )
            case DeclLayoutNode():
                return LayoutNode(
                    type="layout", cells=self._cells(node.cells, heading_path), **base
                )
            case _:  # pragma: no cover — the discriminated union is closed
                raise TypeError(f"unknown declaration node type: {type(node)!r}")

    def nodes(self, nodes: list[DeclNodeBase], heading_path: list[str]) -> list[CndNode]:
        return [self.node(child, heading_path) for child in nodes]

    def _numbering(self, node, base: dict, resolve) -> Numbering | None:
        """The node's resolved ``numbering``: the engine's value with the
        authored word, ``None`` with the engine off. An authored word with
        the engine off is recorded as a violation, never dropped."""
        authored: DeclNumbering | None = node.numbering
        if self.counters is None:
            if authored is not None:
                self.violations.append(
                    Violation(
                        "numbering-without-engine",
                        "numbering is authored but the counter engine is off, "
                        "and a CND cannot carry a counter word without a value: "
                        "build with numbering=True (cnd build --numbering), or "
                        "remove it",
                        f"{node.type} {base['id']}",
                    )
                )
            return None
        name = authored.name if authored is not None else None
        return Numbering(value=resolve(self.counters), name=name)

    def _items(
        self, items: list[DeclListItem], ordered: bool, heading_path: list[str]
    ) -> list[ListItem]:
        """Resolve list ordinals per the rule pinned on ``DeclListItem``.

        Ordered: no override → previous + 1 (from 1); an override is taken
        verbatim and rebases the rest. Unordered: ordinals do not exist, so
        overrides are dropped. A nested list counts on its own.
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
                    number=number,
                    checked=item.checked,
                    children=self.nodes(item.children, heading_path),
                )
            )
        return resolved

    def _cells(self, cells: list[DeclCell], heading_path: list[str]) -> list[Cell]:
        return [
            Cell(
                row=cell.row,
                col=cell.col,
                rowspan=cell.rowspan,
                colspan=cell.colspan,
                is_header=cell.is_header,
                children=self.nodes(cell.children, heading_path),
            )
            for cell in cells
        ]


def _base(node: DeclNodeBase) -> dict:
    """The ``NodeBase`` fields of a transcribed node: a fresh id, the
    authored identity, and never a location."""
    return {
        "id": uuid4(),
        "label": node.label,
        "state_metadata": node.state_metadata,
        "location": None,
    }


def _text(text: RichText | None) -> RichText | None:
    """A copy of an authored text, value untouched: the CND never shares
    a mutable object with the declaration it came from."""
    return None if text is None else text.model_copy(deep=True)


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
    the node has one, else its reading-order position: ``#7`` in the
    body, ``@fn-a#2`` for the second node of footnote ``fn-a`` (positions
    inside a footnote count within it, spec §8). Both are handles the
    author can find in their own source.
    """
    handles: dict[str, str] = {}
    # No current rule names the document itself, but a future one might —
    # leak-proofing so that UUID would still relabel cleanly.
    handles[str(cnd.id)] = "the document"
    for visit in cnd.iter_all():
        node = visit.node
        if node.label:
            handle = f"@{node.label}"
        elif visit.ctx.path[0] == "footnotes":
            note = cnd.footnotes[visit.ctx.path[1]]
            handle = f"@{note.label}#{visit.ctx.doc_index}"
        else:
            handle = f"#{visit.ctx.doc_index}"
        handles[str(node.id)] = handle
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
