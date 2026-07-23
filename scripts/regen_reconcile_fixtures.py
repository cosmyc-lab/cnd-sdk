"""Build the reconcile fixture pairs and their expected-matching vectors.

ADR 0018's matcher is a *versioned reference algorithm*, not part of the
format — which is exactly why it needs vectors. A normative rule can be
read off the spec; a heuristic can only be reproduced by pinning its
output. Each pair below isolates one matcher pass, plus the combined case
the ADR documents as a failure.

Ids are literal and stable per file so a vector can name them. They are
not durable across builds in the real world (ADR 0015) — here they are
fixture coordinates, nothing more.
"""

import json
from pathlib import Path

FIXTURES = Path(__file__).parent.parent / "fixtures" / "reconcile"


def uid(case: int, n: int) -> str:
    return f"00000000-0000-4000-c{case:03d}-{n:012d}"


def para(case: int, n: int, text: str, label: str | None = None) -> dict:
    node = {"id": uid(case, n), "type": "paragraph", "text": text}
    if label:
        node["label"] = label
    return node


def cnd(nodes: list[dict]) -> dict:
    return {
        "cnd_version": "0.3.0",
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
                "text": "gamma",
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
    {"id": uid(7, 100), "label": "fn-a", "text": "first"},
    {"id": uid(7, 101), "label": "fn-b", "text": "second"},
]
pool_new = cnd([para(7, 2, "alpha", label="p")])
pool_new["footnotes"] = [
    {"id": uid(7, 102), "label": "fn-b", "text": "second rewritten"},
    {"id": uid(7, 103), "label": "fn-c", "text": "third"},
]
CASES["07-pools-key-on-label"] = (
    pool_old,
    pool_new,
    "Pool entries carry a required label, so the pool diff is exact and "
    "order-independent.",
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
        (case_dir / "old.cnd").write_text(json.dumps(old_doc, indent=2) + "\n")
        (case_dir / "new.cnd").write_text(json.dumps(new_doc, indent=2) + "\n")

        report = diff(Cnd.model_validate(old_doc), Cnd.model_validate(new_doc))
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
