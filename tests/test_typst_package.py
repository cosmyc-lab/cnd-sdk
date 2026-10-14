"""The Typst authoring package ships inside the installed wheel."""

from importlib.resources import files


def test_typst_package_ships_in_wheel() -> None:
    text = (files("cnd") / "typst" / "cnd.typ").read_text(encoding="utf-8")
    assert 'state("cnd.metadata"' in text


def test_table_hint_is_kind() -> None:
    """The hint carries the CND's `table.kind` under the same name
    (docs/proposals/0013); the 0.4 `content_kind` is gone."""
    text = (files("cnd") / "typst" / "cnd.typ").read_text(encoding="utf-8")
    assert "#let table(body, kind: none)" in text
    assert "(kind: kind)" in text
    assert "content_kind" not in text


def test_decorative_helper_is_pdf_artifact() -> None:
    text = (files("cnd") / "typst" / "cnd.typ").read_text(encoding="utf-8")
    assert "#let decorative(body) = pdf.artifact(body)" in text


# -- compiled behaviour -------------------------------------------------
#
# The checks below compile a document against the package with the
# `typst` binary and read the state back with `typst query`. They skip
# cleanly where typst is not installed.

import json  # noqa: E402
import shutil  # noqa: E402
import subprocess  # noqa: E402
from pathlib import Path  # noqa: E402

import pytest  # noqa: E402

needs_typst = pytest.mark.skipif(
    shutil.which("typst") is None, reason="the typst binary is not installed"
)


def _state_at(tmp_path: Path, body: str) -> dict[str, dict]:
    """Compile ``body`` after ``#import "/cnd.typ"`` and return the
    cnd.metadata state at each ``<probe-…>`` point, by probe name."""
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
    return {
        item["value"]["probe"]: item["value"]["state"]
        for item in json.loads(result.stdout)
    }


def _probe(name: str) -> str:
    return f'#context metadata((probe: "{name}", state: cnd.metadata.get()))\n'


@needs_typst
def test_table_hint_restores_a_document_level_kind(tmp_path: Path) -> None:
    """A document-level ``kind`` the author set survives a table hint:
    inside the table the hint wins, after it the author's value is back."""
    states = _state_at(
        tmp_path,
        '#cnd.metadata.update(it => it + (kind: "report", revision: "1"))\n'
        '#cnd.table([table(columns: 1, [A]) ' + _probe("inside").strip() + '],'
        ' kind: "data")\n'
        + _probe("after"),
    )
    assert states["inside"] == {"kind": "data", "revision": "1"}
    assert states["after"] == {"kind": "report", "revision": "1"}


@needs_typst
def test_table_hint_leaves_no_kind_when_there_was_none(tmp_path: Path) -> None:
    states = _state_at(
        tmp_path,
        '#cnd.metadata.update(it => it + (revision: "1"))\n'
        '#cnd.table(table(columns: 1, [A]), kind: "data")\n'
        + _probe("after"),
    )
    assert states["after"] == {"revision": "1"}


@needs_typst
def test_nested_table_hints_unwind_in_order(tmp_path: Path) -> None:
    states = _state_at(
        tmp_path,
        '#cnd.table([#cnd.table([' + _probe("inner").strip() + '], kind: "content")'
        + _probe("between").strip() + '], kind: "data")\n'
        + _probe("after"),
    )
    assert states["inner"] == {"kind": "content"}
    assert states["between"] == {"kind": "data"}
    assert states["after"] == {}
