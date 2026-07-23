"""The conformance CLI — the executable oracle of the fixture corpus.

This is deliberately *not* a general CND tool. ADR 0020 names the
conformance verb set as ``validate``, ``hash``, ``reconcile``/``diff``,
``build`` from a declaration, and terminal inspection. **Three of those
five are implemented here**; the other two are absent for reasons worth
keeping distinct:

- ``build`` and ``reconcile``/``diff`` are conformance verbs by the ADR's
  own words, and they are missing only because the declaration
  (docs/adr/0019) and the reconciliation algorithm (docs/adr/0018) do not
  exist yet. They belong in this CLI when they do.
- ``cnd declare`` — foreign format to declaration — is a different case:
  it belongs with the producers *permanently*. Bundling it would make the
  hub depend on a satellite and let inference-heuristic churn in through
  the window, which ADR 0019 keeps out of the builder and ADR 0020 keeps
  out of the hub.

So an implementer reading this should know: agreeing with these three
verbs is necessary for conformance, not yet sufficient. The corpus is in
the same state — it carries two of the four vector kinds ADR 0020 §4
requires (``hashes.json``, ``traversal.json``); ``declaration → CND`` and
``(old, new) → matching`` await the same two features.

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

from cnd.core.cnd import Cnd
from cnd.core.hashing import content_hash, node_hash
from cnd.core.validate import validate

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
            "Partial: ADR 0020 also specifies `build` (from a declaration) "
            "and `reconcile`/`diff` as conformance verbs. Both await the "
            "features they act on. Agreeing with the three verbs above is "
            "necessary for conformance, not yet sufficient."
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
