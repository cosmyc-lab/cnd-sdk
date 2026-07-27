"""The conformance CLI — the executable oracle of the fixture corpus.

This is deliberately *not* a general CND tool. ADR 0020 names the
conformance verb set as ``validate``, ``hash``, ``reconcile``/``diff``,
``build`` from a declaration, and terminal inspection. **All five are
implemented here** — ``build`` landed with the declaration
(docs/adr/0019). One thing this CLI deliberately does *not* carry:

- ``cnd declare`` — foreign format to declaration — is a different case:
  it belongs with the producers *permanently*. Bundling it would make the
  hub depend on a satellite and let inference-heuristic churn in through
  the window, which ADR 0019 keeps out of the builder and ADR 0020 keeps
  out of the hub.

So an implementer reading this should know: agreeing with these verbs is
necessary for conformance, not yet sufficient. The corpus carries all
four vector kinds ADR 0020 §4 requires (``hashes.json``,
``traversal.json``, ``matching.json``, and the ``declaration → CND``
pairs under ``fixtures/declaration/``).

``diff`` is the odd one out and worth flagging to anyone comparing
implementations: matching v1 is a *versioned reference algorithm*, not a
normative rule (docs/adr/0018). Reproducing ``matching.json`` proves an
implementation runs v1; it is not a conformance requirement on the
format, and a later version may legitimately differ.

Output is human-readable by default and machine-readable under ``--json``,
because comparing two implementations is a diff, not a read.

Exit codes are part of the contract:

- ``0`` — conformant / succeeded
- ``1`` — the CND is not conformant, or a file failed to parse
- ``2`` — usage error (argparse's own convention)
"""

import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path

from pydantic import ValidationError

from cnd.builder import BuildError, build
from cnd.core.cnd import Cnd
from cnd.core.hashing import content_hash, node_hash
from cnd.core.validate import validate
from cnd.declaration import Declaration
from cnd.reconcile import diff

EXIT_OK = 0
EXIT_NONCONFORMANT = 1


def main(argv: Sequence[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    return args.run(args)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="cnd",
        description=(
            "CND conformance tools — the executable oracle of the fixture "
            "corpus. Checks a CND against the invariants JSON Schema cannot "
            "express, and computes the reference content hashes."
        ),
        epilog=(
            "`cnd declare` (foreign format → declaration) is not here and "
            "never will be: it belongs with the producers (ADR 0020)."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    sub = parser.add_subparsers(dest="command", required=True)

    check = sub.add_parser(
        "validate",
        help="check the invariants JSON Schema cannot express",
        description=(
            "Global label uniqueness, per-family link domains, "
            "all-or-nothing pagination, and the bibliography content floor "
            "(spec sections 5, 9). Shape errors are the schema's job and are "
            "reported as parse failures."
        ),
    )
    _add_common(check)
    check.set_defaults(run=_run_validate)

    digest = sub.add_parser(
        "hash",
        help="compute the derived content hashes",
        description=(
            "RFC 8785 (JCS) over the hashable subset with strings normalised "
            "to NFC (spec section 10). Never serialised into the CND — this "
            "recomputes it."
        ),
    )
    _add_common(digest)
    digest.add_argument(
        "--nodes",
        action="store_true",
        help="also print each node hash, in reading order",
    )
    digest.set_defaults(run=_run_hash)

    delta = sub.add_parser(
        "diff",
        help="what moved between two builds of a document",
        description=(
            "Matching v1 (docs/adr/0018) over two CNDs: each node is added, "
            "removed, changed, moved or unchanged, plus a label-keyed diff "
            "of both pools. A versioned reference algorithm, NOT part of "
            "the format — exact for labelled nodes, best-effort for the "
            "rest, and it reports which pass paired each node so a caller "
            "can tell the two apart."
        ),
    )
    delta.add_argument("old", type=Path, metavar="OLD")
    delta.add_argument("new", type=Path, metavar="NEW")
    delta.add_argument(
        "--json",
        action="store_true",
        help="machine-readable output, for diffing against another implementation",
    )
    delta.set_defaults(run=_run_diff)

    produce = sub.add_parser(
        "build",
        help="compile a declaration into a CND (docs/adr/0019)",
        description=(
            "The declarative door: reads a declaration (JSON, or YAML with "
            "the yaml extra), derives everything the declaration omits, and "
            "emits a validated CND. Numbering is opt-in — the declarative "
            "door serves unnumbered sources, so inventing counters is a "
            "choice, never a default."
        ),
    )
    produce.add_argument("file", type=Path, metavar="DECL")
    produce.add_argument(
        "--numbering",
        action="store_true",
        help="run the counter engine (one fixed house style)",
    )
    produce.add_argument(
        "-o",
        "--output",
        type=Path,
        help="write the CND here instead of stdout",
    )
    produce.set_defaults(run=_run_build)

    show = sub.add_parser(
        "inspect",
        help="render a readable trace of the tree (needs the display extra)",
    )
    show.add_argument("files", nargs="+", type=Path, metavar="FILE")
    show.set_defaults(run=_run_inspect)

    return parser


def _add_common(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("files", nargs="+", type=Path, metavar="FILE")
    parser.add_argument(
        "--json",
        action="store_true",
        help="machine-readable output, for diffing against another implementation",
    )


def _load(path: Path) -> tuple[Cnd | None, str | None]:
    """Parse a CND, returning either the model or a reason it failed.

    Both failure modes — unreadable file and invalid shape — are reported
    the same way, because to a caller comparing implementations they are
    the same event: this file did not yield a CND.
    """
    try:
        return Cnd.model_validate_json(path.read_text()), None
    except OSError as err:
        return None, f"cannot read: {err.strerror or err}"
    except ValidationError as err:
        count = err.error_count()
        first = err.errors()[0]
        location = ".".join(str(part) for part in first["loc"])
        return None, f"{count} schema error(s), first at {location}: {first['msg']}"


def _load_declaration(path: Path) -> tuple[Declaration | None, str | None]:
    """Parse a declaration, returning either the model or a reason.

    Mirrors ``_load``: unreadable, unparsable and invalid-shape all
    report the same way. YAML needs the ``yaml`` extra and is imported
    lazily so the core keeps its pydantic-only dependency floor
    (ADR 0005's ``[display]`` precedent).
    """
    try:
        text = path.read_text()
    except OSError as err:
        return None, f"cannot read: {err.strerror or err}"

    if path.suffix in {".yaml", ".yml"}:
        try:
            import yaml
        except ImportError:
            return None, (
                "reading a YAML declaration needs the yaml extra: "
                "pip install cnd-sdk[yaml]"
            )
        try:
            data = yaml.safe_load(text)
        except yaml.YAMLError as err:
            return None, f"invalid YAML: {err}"
    else:
        try:
            data = json.loads(text)
        except json.JSONDecodeError as err:
            return None, f"invalid JSON: {err}"

    try:
        return Declaration.model_validate(data), None
    except ValidationError as err:
        count = err.error_count()
        first = err.errors()[0]
        location = ".".join(str(part) for part in first["loc"])
        return None, f"{count} schema error(s), first at {location}: {first['msg']}"


def _run_validate(args: argparse.Namespace) -> int:
    results = []
    failed = False
    for path in args.files:
        cnd, error = _load(path)
        if cnd is None:
            failed = True
            results.append({"file": str(path), "ok": False, "error": error})
            continue
        violations = validate(cnd)
        failed = failed or bool(violations)
        results.append(
            {
                "file": str(path),
                "ok": not violations,
                "violations": [
                    {"rule": v.rule, "where": v.where, "message": v.message}
                    for v in violations
                ],
            }
        )

    if args.json:
        print(json.dumps(results, indent=2))
    else:
        for result in results:
            if result.get("error"):
                print(f"{result['file']}: {result['error']}", file=sys.stderr)
            elif result["ok"]:
                print(f"{result['file']}: ok")
            else:
                count = len(result["violations"])
                print(f"{result['file']}: {count} violation(s)", file=sys.stderr)
                for v in result["violations"]:
                    print(f"  [{v['rule']}] {v['where']}: {v['message']}", file=sys.stderr)
    return EXIT_NONCONFORMANT if failed else EXIT_OK


def _run_hash(args: argparse.Namespace) -> int:
    results = []
    failed = False
    for path in args.files:
        cnd, error = _load(path)
        if cnd is None:
            failed = True
            results.append({"file": str(path), "error": error})
            continue
        entry = {"file": str(path), "content_hash": content_hash(cnd)}
        if args.nodes:
            entry["node_hashes"] = [node_hash(v.node) for v in cnd.iter()]
        results.append(entry)

    if args.json:
        print(json.dumps(results, indent=2))
    else:
        for result in results:
            if "error" in result:
                print(f"{result['file']}: {result['error']}", file=sys.stderr)
                continue
            print(f"{result['content_hash']}  {result['file']}")
            for index, digest in enumerate(result.get("node_hashes", []), start=1):
                print(f"  {index:>4}  {digest}")
    return EXIT_NONCONFORMANT if failed else EXIT_OK


def _run_build(args: argparse.Namespace) -> int:
    decl, error = _load_declaration(args.file)
    if decl is None:
        print(f"{args.file}: {error}", file=sys.stderr)
        return EXIT_NONCONFORMANT

    try:
        cnd = build(decl, numbering=args.numbering)
    except BuildError as err:
        count = len(err.violations)
        print(f"{args.file}: {count} violation(s)", file=sys.stderr)
        for violation in err.violations:
            print(
                f"  [{violation.rule}] {violation.where}: {violation.message}",
                file=sys.stderr,
            )
        return EXIT_NONCONFORMANT

    payload = cnd.model_dump_json(indent=2)
    if args.output is not None:
        args.output.write_text(payload + "\n")
    else:
        print(payload)
    return EXIT_OK


# Statuses in report order: what a reader acts on first.
_DIFF_ORDER = ("changed", "added", "removed", "moved", "unchanged")


def _run_diff(args: argparse.Namespace) -> int:
    old, old_error = _load(args.old)
    new, new_error = _load(args.new)
    for path, error in ((args.old, old_error), (args.new, new_error)):
        if error:
            print(f"{path}: {error}", file=sys.stderr)
    if old is None or new is None:
        return EXIT_NONCONFORMANT

    report = diff(old, new)
    payload = {
        "matcher_version": report.matcher_version,
        "old": str(args.old),
        "new": str(args.new),
        "nodes": [
            {
                "status": change.status,
                "matched_by": change.matched_by,
                "type": (change.new or change.old).node.type,
                "label": (change.new or change.old).node.label,
                "old_id": str(change.old.node.id) if change.old else None,
                "new_id": str(change.new.node.id) if change.new else None,
            }
            for change in report.nodes
        ],
        "bibliography": _pool_payload(report.bibliography),
        "footnotes": _pool_payload(report.footnotes),
    }

    if args.json:
        print(json.dumps(payload, indent=2))
        return EXIT_OK

    counts = {
        status: sum(1 for c in report.nodes if c.status == status)
        for status in _DIFF_ORDER
    }
    summary = "  ".join(f"{status}={counts[status]}" for status in _DIFF_ORDER)
    print(f"matching {report.matcher_version}   {summary}")
    for change in report.nodes:
        if change.status == "unchanged":
            continue
        entry = change.new or change.old
        name = f"@{entry.node.label}" if entry.node.label else entry.node.type
        # A pairing is only exact when a label made it so; saying which
        # pass matched is the difference between a fact and a guess.
        via = f" via {change.matched_by}" if change.matched_by else ""
        print(f"  {change.status:<9} {name}{via}")
    for pool_name, pool in (
        ("bibliography", report.bibliography),
        ("footnotes", report.footnotes),
    ):
        for change in pool.changes:
            if change.status != "unchanged":
                print(f"  {change.status:<9} @{change.label} ({pool_name})")
    return EXIT_OK


def _pool_payload(pool) -> list[dict]:
    return [
        {"status": change.status, "label": change.label}
        for change in pool.changes
    ]


def _run_inspect(args: argparse.Namespace) -> int:
    try:
        from cnd.visitors.node_display_visitor import NodeDisplayVisitor
    except ImportError:
        print(
            "inspect needs the display extra: pip install cnd-sdk[display]",
            file=sys.stderr,
        )
        return EXIT_NONCONFORMANT

    failed = False
    for path in args.files:
        cnd, error = _load(path)
        if cnd is None:
            failed = True
            print(f"{path}: {error}", file=sys.stderr)
            continue
        NodeDisplayVisitor().visit(cnd)
    return EXIT_NONCONFORMANT if failed else EXIT_OK


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
