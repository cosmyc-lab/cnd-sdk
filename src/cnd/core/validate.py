"""CND validation — the invariants JSON Schema cannot express.

The schema settles shape: which fields exist, of what type. What it
cannot state is anything relational or document-wide — that a label is
unique across the whole CND, that an edge resolves in *its own* domain,
that pagination is all-or-nothing. Those are checked here.

This is the enforcement half of one contract with two enforcements of
unequal strength (docs/adr/0019): a declarative producer cannot bypass
the builder, while a direct producer can forget ``validate()``. The
asymmetry is deliberate and named rather than papered over.

The function is a value function — CND in, list of violations out — so
it crosses any boundary (docs/adr/0019 §5).

Invariants checked: ``cnd_version`` is the version this SDK implements;
ids unique across the whole CND; labels unique;
edges resolve in their own domain; ``text_span`` inside its text; marks
in bounds, canonically ordered, merged per kind and never reaching into
an atomic mark; each ``heading_path`` consistent with the tree; no two
cells of a grid covering the same position; pagination all-or-nothing;
bibliography floor; no ``doc.extra`` key repeating a named metadata
field.

What a single value can say about itself — an unknown key, a heading
level below 1, a negative cell coordinate, a ``text_span`` that is
not two non-negative offsets — is the models' and the schema's, and is
refused on parse before ``validate()`` runs.
"""

import heapq
from bisect import bisect_left
from dataclasses import dataclass

from cnd.core.cnd import CND_VERSION, BibEntry, Cnd, DocMetadata, Footnote
from cnd.core.nodes import Cell, CndNode, HeadingNode, LayoutNode, TableNode, texts_of
from cnd.core.text import ATOMIC_MARK_KINDS, LinkRef, RichText

# The lifted bibliographic fields; an entry satisfies the content floor
# with a `formatted` string or with at least one of these.
_BIB_STRUCTURED_FIELDS = (
    "type",
    "authors",
    "title",
    "year",
    "container",
    "doi",
    "url",
    "fields",
)


@dataclass(frozen=True)
class Violation:
    """A single broken invariant.

    ``rule`` is a stable identifier a caller can branch on; ``message``
    is for humans. ``where`` names the offending node, entry or label —
    a CND has no path syntax, so it is the most specific handle
    available.
    """

    rule: str
    message: str
    where: str

    def __str__(self) -> str:
        return f"[{self.rule}] {self.where}: {self.message}"


def validate(cnd: Cnd) -> list[Violation]:
    """Every invariant this CND breaks, in a stable order. Empty means valid.

    Returns rather than raises: a producer wants the whole list, not the
    first failure, and a caller that prefers an exception can raise on a
    non-empty result. Shape errors are Pydantic's job and have already
    been raised by the time a ``Cnd`` exists.
    """
    violations: list[Violation] = []
    violations += _check_cnd_version(cnd)
    violations += _check_id_uniqueness(cnd)
    violations += _check_label_uniqueness(cnd)
    violations += _check_link_domains(cnd)
    violations += _check_text_spans(cnd)
    violations += _check_marks(cnd)
    violations += _check_heading_paths(cnd)
    violations += _check_cell_grids(cnd)
    violations += _check_pagination(cnd)
    violations += _check_bibliography_floor(cnd)
    violations += _check_doc_extra(cnd)
    return violations


def _check_cnd_version(cnd: Cnd) -> list[Violation]:
    """The CND declares the format version this SDK implements (spec §11).

    Before 1.0.0 a minor version may change what any field means
    (docs/adr/0027), so a CND stamped with another version is not
    conformant to this one even when its shape happens to parse.
    """
    if cnd.cnd_version == CND_VERSION:
        return []
    return [
        Violation(
            "cnd-version-unsupported",
            f"this SDK implements CND {CND_VERSION} only; there is no "
            f"upgrader between pre-1.0 versions",
            f"cnd_version {cnd.cnd_version}",
        )
    ]


def _all_texts(cnd: Cnd):
    """Every RichText of the CND with a handle for messages: the node
    texts of the body and the footnotes, then formatted bibliography
    entries."""
    for visit in cnd.iter_all():
        for text in texts_of(visit.node):
            yield text, f"{visit.node.type} {visit.node.id}"
    for entry in cnd.bibliography:
        if entry.formatted is not None:
            yield entry.formatted, f"bibliography entry {entry.id}"


def _check_label_uniqueness(cnd: Cnd) -> list[Violation]:
    """Labels are globally unique within a CND (docs/adr/0017).

    Global rather than per-domain, because that is what lets an edge name
    its target by label alone. A producer sees only its own document and
    not the label space it lands in, so collisions are the likely failure
    and must be caught rather than silently resolved to the first match.
    """
    seen: dict[str, str] = {}
    violations: list[Violation] = []

    def claim(label: str | None, owner: str) -> None:
        if label is None:
            return
        if label in seen:
            violations.append(
                Violation(
                    "label-not-unique",
                    f"label is already claimed by {seen[label]}",
                    f"@{label} on {owner}",
                )
            )
            return
        seen[label] = owner

    for visit in cnd.iter_all():
        claim(visit.node.label, f"{visit.node.type} {visit.node.id}")
    for entry in cnd.bibliography:
        claim(entry.label, f"bibliography entry {entry.id}")
    for note in cnd.footnotes:
        claim(note.label, f"footnote {note.id}")
    return violations


def _check_link_domains(cnd: Cnd) -> list[Violation]:
    """Each label-keyed link family resolves in its own domain (docs/adr/0017).

    Existence is not enough: labels are unique across the whole CND, so a
    ``cites`` edge naming a heading resolves to *something*. The family an
    edge sits in fixes what that something must be.

    This subsumes the "a refs target must carry a label" rule — an
    unlabelled node is unreachable by any edge, so nothing can point at
    it in the first place.

    ``links`` is deliberately not in ``families`` below: it is href-keyed,
    not label-keyed, so it has no label to resolve and no domain to check
    against. Its target is outside the CND by definition (spec §5).
    """
    violations: list[Violation] = []
    families: tuple[tuple[str, type | tuple[type, ...], str], ...] = (
        ("refs", (), "a node"),
        ("cites", BibEntry, "a bibliography entry"),
        ("footnotes", Footnote, "a footnote"),
    )
    for text, where in _all_texts(cnd):
        for family, expected, described in families:
            for link in getattr(text, family):
                target = cnd.resolve(link.label)
                if target is None:
                    violations.append(
                        Violation(
                            "link-unresolved",
                            f"{family} edge names a label nothing carries",
                            f"@{link.label} on {where}",
                        )
                    )
                    continue
                if not _in_domain(target, expected):
                    violations.append(
                        Violation(
                            "link-wrong-domain",
                            f"{family} edge must resolve to {described}, "
                            f"got {type(target).__name__}",
                            f"@{link.label} on {where}",
                        )
                    )
    return violations


def _in_domain(target: object, expected: type | tuple[type, ...]) -> bool:
    """Whether ``target`` sits in the domain a family resolves into.

    ``refs`` points into the tree, whose members are a discriminated union
    of node classes rather than one type — it is expressed here as "not a
    pool entry", which is the same statement without enumerating a union
    that grows.
    """
    if expected == ():
        return not isinstance(target, (BibEntry, Footnote))
    return isinstance(target, expected)


def _check_pagination(cnd: Cnd) -> list[Violation]:
    """Pagination is all-or-nothing (docs/proposals/0008).

    Either every node carries a ``location`` or none does. This removes
    the "unknown page" vs. "not paginated" ambiguity without adding a
    field, and it is what makes ``Cnd.paginated`` safe to derive from the
    first node alone.
    """
    located: list[CndNode] = []
    unlocated: list[CndNode] = []
    for visit in cnd.iter_all():
        (located if visit.node.location is not None else unlocated).append(visit.node)

    if not located or not unlocated:
        return []

    # Report the minority — it is the anomaly, and a short list is more
    # actionable than the same finding repeated across a whole document.
    partial, expected = (
        (unlocated, "carry a location") if len(unlocated) <= len(located)
        else (located, "omit their location")
    )
    return [
        Violation(
            "pagination-partial",
            f"CND is partially paginated; these nodes should {expected}",
            f"{node.type} {node.id}",
        )
        for node in partial
    ]


def _check_bibliography_floor(cnd: Cnd) -> list[Violation]:
    """An entry must carry ``formatted``, structured fields, or both.

    ``formatted`` is nullable because a hand author has no style engine,
    and the structured fields are optional because a compiler may only
    have the rendered string. Neither being present leaves an entry a
    citation can reach but nothing can display.
    """
    return [
        Violation(
            "bib-entry-empty",
            "entry has neither `formatted` nor any structured field",
            f"@{entry.label} (bibliography entry {entry.id})",
        )
        for entry in cnd.bibliography
        if entry.formatted is None and not _has_structured_fields(entry)
    ]


def _has_structured_fields(entry: BibEntry) -> bool:
    return any(getattr(entry, name) for name in _BIB_STRUCTURED_FIELDS)


def _check_id_uniqueness(cnd: Cnd) -> list[Violation]:
    """Every id is unique across the whole CND (§2): body nodes, footnote
    content nodes and the entries of both pools."""
    seen: dict[str, str] = {}
    violations: list[Violation] = []
    owners = [(v.node.id, f"{v.node.type} {v.node.id}") for v in cnd.iter_all()]
    owners += [(e.id, f"bibliography entry {e.id}") for e in cnd.bibliography]
    owners += [(f.id, f"footnote {f.id}") for f in cnd.footnotes]
    for ident, owner in owners:
        key = str(ident)
        if key in seen:
            violations.append(
                Violation(
                    "id-not-unique", f"id is already used by {seen[key]}", owner
                )
            )
            continue
        seen[key] = owner
    return violations


def _check_text_spans(cnd: Cnd) -> list[Violation]:
    """Every ``text_span`` lies inside the ``value`` it indexes (§5)."""
    violations: list[Violation] = []
    for text, where in _all_texts(cnd):
        length = len(text.value)
        for edge in text.edges():
            span = edge.text_span
            if span is None:
                continue
            if len(span) != 2 or not 0 <= span[0] <= span[1] <= length:
                name = edge.href if isinstance(edge, LinkRef) else edge.label
                violations.append(
                    Violation(
                        "text-span-out-of-bounds",
                        f"text_span {span} is outside a text of {length} code points",
                        f"@{name} on {where}",
                    )
                )
    return violations


def _check_marks(cnd: Cnd) -> list[Violation]:
    """Mark invariants (docs/proposals/0013, Marks): bounds, canonical
    order, same-kind merge, atomic verbatim."""
    violations: list[Violation] = []
    for text, where in _all_texts(cnd):
        violations += _mark_violations(text, where)
    return violations


def _mark_violations(text: RichText, where: str) -> list[Violation]:
    out: list[Violation] = []
    length = len(text.value)
    for mark in text.marks:
        if mark.start == mark.end and 0 <= mark.start <= length:
            out.append(
                Violation(
                    "mark-out-of-bounds",
                    f"{mark.kind} mark [{mark.start}, {mark.end}) is empty",
                    where,
                )
            )
        elif not 0 <= mark.start < mark.end <= length:
            out.append(
                Violation(
                    "mark-out-of-bounds",
                    f"{mark.kind} mark [{mark.start}, {mark.end}) is outside a text of {length} code points",
                    where,
                )
            )
    keys = [(m.start, m.end, m.kind) for m in text.marks]
    if keys != sorted(keys):
        out.append(
            Violation(
                "mark-not-canonical",
                "marks are not sorted by (start, end, kind)",
                where,
            )
        )
    by_kind: dict[str, list] = {}
    for mark in text.marks:
        by_kind.setdefault(mark.kind, []).append(mark)
    for kind, marks in by_kind.items():
        ordered = sorted(marks, key=lambda m: (m.start, m.end))
        for prev, cur in zip(ordered, ordered[1:]):
            if cur.start <= prev.end:
                out.append(
                    Violation(
                        "mark-same-kind-overlap",
                        f"two {kind} marks overlap or touch at {cur.start}; merge them",
                        where,
                    )
                )
    spans = [(i, m.start, m.end, f"{m.kind} mark") for i, m in enumerate(text.marks)]
    spans += [
        (None, e.text_span[0], e.text_span[1], "edge span")
        for e in text.edges()
        if e.text_span is not None and len(e.text_span) == 2
    ]
    for index, atom in enumerate(text.marks):
        if atom.kind not in ATOMIC_MARK_KINDS:
            continue
        for other, start, end, what in spans:
            if other == index:
                continue
            disjoint = end <= atom.start or start >= atom.end
            covers = start <= atom.start and end >= atom.end
            if not (disjoint or covers):
                out.append(
                    Violation(
                        "mark-atomic-crossed",
                        f"{what} [{start}, {end}) reaches inside the {atom.kind} mark "
                        f"[{atom.start}, {atom.end})",
                        where,
                    )
                )
    return out


def _check_heading_paths(cnd: Cnd) -> list[Violation]:
    """Each ``heading_path`` is its nearest enclosing heading's path plus
    one element for the heading itself.

    The enclosing heading is found through any container (a list item, a
    cell, a quote), and the top of the body and of each footnote starts
    from ``[]``. A heading is compared with its parent's path *as
    written*, so one wrong path is reported once rather than again for
    every consistent heading below it. What an element holds — a bare
    title or one prefixed with its number — is the producer's choice and
    is not checked.
    """
    violations: list[Violation] = []
    for visit in cnd.iter_all():
        node = visit.node
        if not isinstance(node, HeadingNode):
            continue
        enclosing = visit.ctx.heading_path
        path = node.heading_path
        if len(path) == len(enclosing) + 1 and path[:-1] == enclosing:
            continue
        violations.append(
            Violation(
                "heading-path-mismatch",
                f"heading_path {path!r} should be the enclosing heading's "
                f"path {enclosing!r} plus one element for this heading",
                f"heading {node.id}",
            )
        )
    return violations


def _check_cell_grids(cnd: Cnd) -> list[Violation]:
    """No two cells of a ``table`` or ``layout`` cover the same grid
    position, spans included; two cells at the same ``(row, col)`` are the
    simplest case."""
    violations: list[Violation] = []
    for visit in cnd.iter_all():
        node = visit.node
        if not isinstance(node, (TableNode, LayoutNode)):
            continue
        for index, other_index in _overlapping_cells(node.cells):
            cell, other = node.cells[index], node.cells[other_index]
            same = (cell.row, cell.col) == (other.row, other.col)
            violations.append(
                Violation(
                    "cell-overlap",
                    (
                        f"sits at the same position as cell {other_index}"
                        if same
                        else f"overlaps cell {other_index} "
                        f"(row {other.row}, col {other.col})"
                    ),
                    f"cell {index} (row {cell.row}, col {cell.col}) "
                    f"of {node.type} {node.id}",
                )
            )
    return violations


def _overlapping_cells(cells: list[Cell]) -> list[tuple[int, int]]:
    """``(index, other_index)`` for every cell whose rectangle meets the
    rectangle of a cell placed before it in the sweep, sorted by
    ``index``.

    The sweep visits cells in ``(row, col)`` order, which is not
    necessarily ``cells`` order, so ``other_index`` may be the larger of
    the two. It compares rectangles and never fills a grid, so its cost
    does not depend on the spans: a cell of a billion rows costs what a
    cell of one does. A cell found overlapping is reported and left out of
    the sweep, so the cells that remain cover each position at most once.

    The cells still covering the current row form disjoint column
    intervals. Each is keyed by its first column, ranked among the
    distinct ``col`` values of the grid, in a Fenwick tree of live ranks.
    A new cell ``[col, col + colspan)`` meets a live interval exactly when
    a live interval starts inside it, or when the nearest one starting
    before it reaches past ``col``; both questions, like inserting and
    expiring an interval, cost O(log n). The whole sweep is O(n log n) in
    the number of cells, whatever the grid's shape.
    """
    order = sorted(range(len(cells)), key=lambda i: (cells[i].row, cells[i].col))
    columns = sorted({cell.col for cell in cells})
    rank = {col: at for at, col in enumerate(columns)}
    live = _LiveRanks(len(columns))
    end_col = [0] * len(columns)  # end column of the live interval at a rank
    owner = [0] * len(columns)  # cell index of the live interval at a rank
    expiry: list[tuple[int, int]] = []  # heap of (end row, rank)
    found: list[tuple[int, int]] = []
    for index in order:
        cell = cells[index]
        while expiry and expiry[0][0] <= cell.row:
            live.remove(heapq.heappop(expiry)[1])
        first, end = cell.col, cell.col + cell.colspan
        at = rank[first]
        before = live.count_below(at)
        if live.count_below(bisect_left(columns, end)) > before:
            found.append((index, owner[live.kth(before + 1)]))
            continue
        if before and end_col[left := live.kth(before)] > first:
            found.append((index, owner[left]))
            continue
        live.add(at)
        end_col[at], owner[at] = end, index
        heapq.heappush(expiry, (cell.row + cell.rowspan, at))
    return sorted(found)


class _LiveRanks:
    """A set of ranks in ``range(size)``, as a Fenwick tree of 0/1 counts:
    insert, remove, count below a rank and find the k-th smallest member,
    each in O(log size)."""

    def __init__(self, size: int) -> None:
        self._size = size
        self._tree = [0] * (size + 1)
        self._top = 1 << size.bit_length()

    def _update(self, rank: int, delta: int) -> None:
        tree, size, at = self._tree, self._size, rank + 1
        while at <= size:
            tree[at] += delta
            at += at & -at

    def add(self, rank: int) -> None:
        self._update(rank, 1)

    def remove(self, rank: int) -> None:
        self._update(rank, -1)

    def count_below(self, rank: int) -> int:
        """How many members are smaller than ``rank``."""
        tree, total = self._tree, 0
        while rank > 0:
            total += tree[rank]
            rank -= rank & -rank
        return total

    def kth(self, k: int) -> int:
        """The ``k``-th smallest member (1-based); ``k`` must not exceed
        the number of members."""
        tree, size, at, step = self._tree, self._size, 0, self._top
        while step:
            ahead = at + step
            if ahead <= size and tree[ahead] < k:
                at = ahead
                k -= tree[ahead]
            step >>= 1
        return at


def _check_doc_extra(cnd: Cnd) -> list[Violation]:
    """No ``doc.extra`` key repeats a named metadata field (§3), or the
    document would carry two contradictory values."""
    named = set(DocMetadata.model_fields)
    return [
        Violation(
            "doc-extra-shadows-field",
            "an extra key repeats a named metadata field",
            f"doc.extra[{key!r}]",
        )
        for key in sorted(cnd.doc.extra)
        if key in named
    ]
