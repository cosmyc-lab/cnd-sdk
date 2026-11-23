"""Reconciliation — matching nodes across two builds (docs/adr/0018;
matching v3, docs/adr/0032, which builds on matching v2, docs/adr/0029).

A **versioned reference algorithm**, not part of the format: it is an SDK
facility (docs/adr/0006) and creates no conformance obligation on a
producer. ``MATCHER_VERSION`` names the version implemented here.

    from cnd.reconcile import diff

    report = diff(previous, current)
    for change in report.changed:
        ...

Id inheritance is the other half, and consumes the same matching:

    from cnd.reconcile import reconcile

    result = reconcile(current, previous)   # current, with previous' ids

Both are standalone passes over two *built* CNDs rather than build
parameters, which is what makes them door-agnostic (docs/adr/0018).
"""

from cnd.reconcile.diff import (
    CndDiff,
    NodeChange,
    NodeStatus,
    PoolChange,
    PoolDiff,
    PoolStatus,
    diff,
)
from cnd.reconcile.inherit import ReconcileError, Reconciliation, reconcile
from cnd.reconcile.match import (
    MATCHER_VERSION,
    NEW_FOOTNOTES,
    PASS_CONTAINER_HASH,
    PASS_HASH,
    PASS_HASH_PATH,
    PASS_LABEL,
    PASS_PATH_TYPE,
    POOL_PASS_CONTENT,
    POOL_PASS_LABEL,
    MatchPass,
    NodeEntry,
    NodeMatch,
    NodeMatching,
    PoolEntry,
    PoolMatch,
    PoolMatching,
    PoolMatchPass,
    StructuralPath,
    align_footnote_paths,
    entries,
    match_entries,
    match_nodes,
    match_pool,
    pool_entries,
)

__all__ = [
    "MATCHER_VERSION",
    "NEW_FOOTNOTES",
    "PASS_CONTAINER_HASH",
    "PASS_HASH",
    "PASS_HASH_PATH",
    "PASS_LABEL",
    "PASS_PATH_TYPE",
    "POOL_PASS_CONTENT",
    "POOL_PASS_LABEL",
    "CndDiff",
    "MatchPass",
    "NodeChange",
    "NodeEntry",
    "NodeMatch",
    "NodeMatching",
    "NodeStatus",
    "PoolChange",
    "PoolDiff",
    "PoolEntry",
    "PoolMatch",
    "PoolMatchPass",
    "PoolMatching",
    "PoolStatus",
    "ReconcileError",
    "Reconciliation",
    "StructuralPath",
    "align_footnote_paths",
    "diff",
    "entries",
    "match_entries",
    "match_nodes",
    "match_pool",
    "pool_entries",
    "reconcile",
]
