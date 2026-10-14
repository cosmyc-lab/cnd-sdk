"""Build the reconcile fixture pairs and their expected-matching vectors.

ADR 0018's matcher is a *versioned reference algorithm*, not part of the
format — which is exactly why it needs vectors. A normative rule can be
read off the spec; a heuristic can only be reproduced by pinning its
output. Each pair below isolates one matcher pass, plus the combined case
the ADR documents as a failure.

Ids are literal and stable per file so a vector can name them. They are
not durable across builds in the real world (ADR 0015) — here they are
fixture coordinates, nothing more.

Cases 08 to 10 exercise what format 0.5 made finer (docs/proposals/0013):
nodes inside list items and cells, and footnote content.
"""

import json
from pathlib import Path

FIXTURES = Path(__file__).parent.parent / "fixtures" / "reconcile"


def uid(case: int, n: int) -> str:
    return f"00000000-0000-4000-c{case:03d}-{n:012d}"


def para(case: int, n: int, text: str, label: str | None = None) -> dict:
    node = {"id": uid(case, n), "type": "paragraph", "text": {"value": text}}
    if label:
        node["label"] = label
    return node


def items(case: int, n: int, *paragraphs: dict) -> dict:
    """A bullet list whose items each hold one of ``paragraphs``."""
    return {
        "id": uid(case, n),
        "type": "list",
        "items": [{"children": [paragraph]} for paragraph in paragraphs],
    }


def table(case: int, n: int, *cells: list[dict]) -> dict:
    """A one-row table; each argument is one cell's children."""
    return {
        "id": uid(case, n),
        "type": "table",
        "cells": [
            {"row": 0, "col": col, "children": children}
            for col, children in enumerate(cells)
        ],
    }


def note(case: int, n: int, label: str, *children: dict) -> dict:
    return {"id": uid(case, n), "label": label, "children": list(children)}


def cite_notes(case: int, n: int, *labels: str) -> dict:
    """A paragraph whose text references every footnote in ``labels``."""
    node = para(case, n, "See the notes.")
    node["text"]["footnotes"] = [{"label": label} for label in labels]
    return node


def cnd(nodes: list[dict]) -> dict:
    return {
        "cnd_version": "0.5.0",
        "built_at": "2026-07-23T00:00:00Z",
        "doc": {"title": "Reconcile fixture"},
        "nodes": nodes,
        "bibliography": [],
        "footnotes": [],
    }


CASES: dict[str, tuple[dict, dict, str]] = {}

# 1 — label: exact, survives edit AND move at once.
CASES["01-label-survives-edit-and-move"] = (
    cnd([para(1, 1, "alpha"), para(1, 2, "beta", label="sec-b")]),
    cnd([para(1, 3, "beta rewritten", label="sec-b"), para(1, 4, "alpha")]),
    "A labelled node is paired even when both its content and its slot changed.",
)

# 2 — hash + path: unchanged, in place.
CASES["02-unchanged-in-place"] = (
    cnd([para(2, 1, "alpha"), para(2, 2, "beta")]),
    cnd([para(2, 3, "alpha"), para(2, 4, "beta")]),
    "Same content in the same slots: every node is unchanged.",
)

# 3 — hash alone: moved but unchanged, the pass that recovers an insertion.
CASES["03-moved-but-unchanged"] = (
    cnd([para(3, 1, "alpha"), para(3, 2, "beta")]),
    cnd([para(3, 3, "inserted"), para(3, 4, "alpha"), para(3, 5, "beta")]),
    "An insertion shifts every following node; the hash pass recovers them.",
)

# 4 — path + type: same slot, edited content.
CASES["04-same-slot-edited"] = (
    cnd([para(4, 1, "alpha"), para(4, 2, "beta")]),
    cnd([para(4, 3, "alpha"), para(4, 4, "beta edited")]),
    "An edit in place falls through to the path+type pass.",
)

# 5 — nothing matches. The type has to differ: with the same type in the
# same slot, pass 4 would pair them as an edit, which is what case 04 is.
CASES["05-added-and-removed"] = (
    cnd([para(5, 1, "alpha")]),
    cnd(
        [
            {
                "id": uid(5, 2),
                "type": "heading",
                "level": 1,
                "text": {"value": "gamma"},
                "heading_path": ["gamma"],
            }
        ]
    ),
    "No pass applies — different content, different type — so the old node "
    "is removed and the new one added.",
)

# 6 — the combined case ADR 0018 documents as a FAILURE.
CASES["06-combined-case-fails"] = (
    cnd([para(6, 1, "alpha"), para(6, 2, "beta")]),
    cnd([para(6, 3, "inserted"), para(6, 4, "alpha"), para(6, 5, "beta edited")]),
    "Edited AND shifted: misses the hash passes and the path pass, so it is "
    "reported added/removed. Pinned as a failure, not papered over.",
)

# 7 — pools match on their required label: exact, never heuristic.
pool_old = cnd([para(7, 1, "alpha", label="p")])
pool_old["footnotes"] = [
    note(7, 100, "fn-a", para(7, 200, "first")),
    note(7, 101, "fn-b", para(7, 201, "second")),
]
pool_new = cnd([para(7, 2, "alpha", label="p")])
pool_new["footnotes"] = [
    note(7, 102, "fn-b", para(7, 202, "second rewritten")),
    note(7, 103, "fn-c", para(7, 203, "third")),
]
CASES["07-pools-key-on-label"] = (
    pool_old,
    pool_new,
    "Pool entries carry a required label, so the pool diff is exact and "
    "order-independent. A footnote's content is nodes: the rewritten note "
    "is reported as a changed paragraph, its entry stays unchanged.",
)

# 8 — an edited list item is matched and reported on its own.
CASES["08-list-item-edited"] = (
    cnd([items(8, 1, para(8, 2, "alpha"), para(8, 3, "beta"), para(8, 4, "gamma"))]),
    cnd([items(8, 5, para(8, 6, "alpha"), para(8, 7, "beta edited"), para(8, 8, "gamma"))]),
    "Format 0.5 is finer: the list itself is unchanged and only the item's "
    "paragraph is changed, where 0.4 marked the whole list changed.",
)

# 9 — the path tells two cells apart. Cell 0 is emptied and cell 1 edited:
# with a path of depth and sibling index alone, both first paragraphs sat
# in the same slot and the edit would pair with cell 0's paragraph.
CASES["09-cells-are-distinct-slots"] = (
    cnd([table(9, 1, [para(9, 2, "first cell")], [para(9, 3, "second cell")])]),
    cnd([table(9, 4, [], [para(9, 5, "second cell, edited")])]),
    "The edited paragraph pairs with the paragraph of its own cell; the "
    "emptied cell's paragraph is removed.",
)

# 10 — reordering the footnote pool moves nothing: the content of a note
# is keyed by the note's label, not by its pool index.
notes_old = cnd([cite_notes(10, 1, "fn-a", "fn-b")])
notes_old["footnotes"] = [
    note(10, 100, "fn-a", para(10, 200, "first")),
    note(10, 101, "fn-b", para(10, 201, "second")),
]
notes_new = cnd([cite_notes(10, 2, "fn-a", "fn-b")])
notes_new["footnotes"] = [
    note(10, 102, "fn-b", para(10, 202, "second")),
    note(10, 103, "fn-a", para(10, 203, "first, edited")),
]
CASES["10-footnote-content"] = (
    notes_old,
    notes_new,
    "Footnote content is matched like body content. The pool was reordered, "
    "yet the untouched note is unchanged in place and the edited one pairs "
    "with its own note's paragraph.",
)

# 11 — a container whose nested content was edited and which also shifted
# slot misses every earlier pass (its digest and its path both differ); the
# last pass pairs it on its own node hash alone.
CASES["11-container-edited-and-shifted"] = (
    cnd([para(11, 1, "intro"), table(11, 2, [para(11, 3, "a")], [para(11, 4, "b")])]),
    cnd(
        [
            para(11, 5, "inserted"),
            para(11, 6, "intro"),
            table(11, 7, [para(11, 8, "a")], [para(11, 9, "b edited")]),
        ]
    ),
    "The table kept its own hash but its cell was edited and a paragraph was "
    "inserted above it: it is paired on its node hash alone (moved), the "
    "unedited cell moves with it, and the edited cell's paragraph is added "
    "while the old one is removed.",
)



def main() -> None:
    import sys

    sys.path.insert(0, str(Path(__file__).parent.parent / "src"))
    from cnd import Cnd
    from cnd.reconcile import MATCHER_VERSION, diff

    vectors: dict[str, dict] = {"matcher_version": MATCHER_VERSION, "cases": {}}
    for name, (old_doc, new_doc, why) in CASES.items():
        case_dir = FIXTURES / name
        case_dir.mkdir(parents=True, exist_ok=True)
        # A literal document id too, so a regeneration is byte-stable.
        case = int(name[:2])
        old = Cnd.model_validate({"id": uid(case, 900), **old_doc})
        new = Cnd.model_validate({"id": uid(case, 901), **new_doc})
        # The SDK's own writer: default-valued fields omitted.
        (case_dir / "old.cnd").write_text(old.to_json() + "\n")
        (case_dir / "new.cnd").write_text(new.to_json() + "\n")

        report = diff(old, new)
        vectors["cases"][name] = {
            "why": why,
            "nodes": [
                {
                    "status": change.status,
                    "matched_by": change.matched_by,
                    "old_id": str(change.old.node.id) if change.old else None,
                    "new_id": str(change.new.node.id) if change.new else None,
                }
                for change in report.nodes
            ],
            "footnotes": [
                {"status": change.status, "label": change.label}
                for change in report.footnotes.changes
            ],
        }

    (FIXTURES.parent / "matching.json").write_text(
        json.dumps(vectors, indent=2) + "\n"
    )
    print(f"wrote {len(CASES)} pairs + matching.json")


if __name__ == "__main__":
    main()
