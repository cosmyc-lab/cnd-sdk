"""The Typst authoring package ships inside the installed wheel."""

from importlib.resources import files


def test_typst_package_ships_in_wheel() -> None:
    text = (files("cnd") / "typst" / "cnd.typ").read_text(encoding="utf-8")
    assert 'state("cnd.metadata"' in text


def test_table_hint_is_kind_stored_as_table_kind() -> None:
    """The author writes `kind:`, the CND's `table.kind`
    (docs/proposals/0013); the state stores it under `table-kind`, so a
    document-level `kind` the author sets never collides with it. The 0.4
    `content_kind` is gone."""
    text = (files("cnd") / "typst" / "cnd.typ").read_text(encoding="utf-8")
    assert "#let table(body, kind: none)" in text
    assert '("table-kind": kind)' in text
    assert 'remove("table-kind"' in text
    assert "content_kind" not in text


def test_decorative_helper_is_pdf_artifact() -> None:
    text = (files("cnd") / "typst" / "cnd.typ").read_text(encoding="utf-8")
    assert "#let decorative(body) = pdf.artifact(body)" in text


# -- compiled behaviour -------------------------------------------------
#
# These compile a document against the package with the `typst` binary and
# read the state back with `typst query`. They skip where typst is missing.

import json  # noqa: E402
import shutil  # noqa: E402
import subprocess  # noqa: E402
from pathlib import Path  # noqa: E402

import pytest  # noqa: E402

needs_typst = pytest.mark.skipif(
    shutil.which("typst") is None, reason="the typst binary is not installed"
)


def _compile(tmp_path: Path, body: str) -> dict[str, dict]:
    """Compile ``body`` after ``#import "/cnd.typ"`` and return the
    cnd.metadata state at each probe, by probe name. Fails on any
    warning other than the CLI's own deprecation notice for `query`."""
    package = (files("cnd") / "typst" / "cnd.typ").read_text(encoding="utf-8")
    (tmp_path / "cnd.typ").write_text(package, encoding="utf-8")
    doc = tmp_path / "doc.typ"
    doc.write_text('#import "/cnd.typ"\n' + body, encoding="utf-8")
    result = subprocess.run(
        ["typst", "query", "--root", str(tmp_path), str(doc), "metadata"],
        capture_output=True,
        text=True,
        check=True,
    )
    assert "converge" not in result.stderr, result.stderr
    warnings = [
        line for line in result.stderr.splitlines()
        if line.startswith("warning:") and "deprecated" not in line
    ]
    assert warnings == [], result.stderr
    return {
        item["value"]["probe"]: item["value"]["state"]
        for item in json.loads(result.stdout)
    }


def _probe(name: str) -> str:
    return f'#context metadata((probe: "{name}", state: cnd.metadata.get()))'


def _hinted_table(kind: str, probe: str) -> str:
    return f'#cnd.table([#table(columns: 1, [A]) {_probe(probe)}], kind: "{kind}")\n'


@needs_typst
def test_many_hinted_tables_converge(tmp_path: Path) -> None:
    kinds = ["data", "content", "data", "content", "data"]
    states = _compile(
        tmp_path,
        "".join(_hinted_table(kind, f"t{i}") for i, kind in enumerate(kinds))
        + _probe("after") + "\n",
    )
    for i, kind in enumerate(kinds):
        assert states[f"t{i}"] == {"table-kind": kind}
    assert states["after"] == {}


@needs_typst
def test_a_document_level_kind_survives_hinted_tables(tmp_path: Path) -> None:
    states = _compile(
        tmp_path,
        '#cnd.metadata.update(it => it + (kind: "report", revision: "1"))\n'
        + _hinted_table("data", "first")
        + _hinted_table("content", "second")
        + _probe("after") + "\n",
    )
    assert states["first"] == {"kind": "report", "revision": "1", "table-kind": "data"}
    assert states["second"] == {
        "kind": "report", "revision": "1", "table-kind": "content"
    }
    assert states["after"] == {"kind": "report", "revision": "1"}
