"""Reconciliation — matching nodes across two builds (docs/adr/0018).

A **versioned reference algorithm**, not part of the format: it is an SDK
facility (docs/adr/0006) and creates no conformance obligation on a
producer. ``MATCHER_VERSION`` names the version implemented here.

    from cnd.reconcile import diff

    report = diff(previous, current)
    for change in report.changed:
        ...

Id inheritance — rewriting a new CND's ids with a previous build's where
nodes correspond — is the other half of ADR 0018 and is not implemented
yet. When it lands it consumes this matching; nothing about it is
implied by what is here.
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
from cnd.reconcile.match import (
    MATCHER_VERSION,
    PASS_HASH,
    PASS_HASH_PATH,
    PASS_LABEL,
    PASS_PATH_TYPE,
    MatchPass,
    NodeEntry,
    NodeMatch,
    NodeMatching,
    PoolEntry,
    PoolMatching,
    StructuralPath,
    entries,
    match_entries,
    match_nodes,
    match_pool,
    pool_entries,
)

__all__ = [
    "MATCHER_VERSION",
    "PASS_HASH",
    "PASS_HASH_PATH",
    "PASS_LABEL",
    "PASS_PATH_TYPE",
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
    "PoolMatching",
    "PoolStatus",
    "StructuralPath",
    "diff",
    "entries",
    "match_entries",
    "match_nodes",
    "match_pool",
    "pool_entries",
]
