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


def test_document_helper_emits_labelled_metadata() -> None:
    text = (files("cnd") / "typst" / "cnd.typ").read_text(encoding="utf-8")
    assert "#let document(status: none, version: none, extra: (:))" in text
    assert "std.metadata((status: status, version: version, extra: extra))" in text
    assert "<cnd-document>" in text


def test_admonition_helper_brackets_its_body() -> None:
    text = (files("cnd") / "typst" / "cnd.typ").read_text(encoding="utf-8")
    assert '#let admonition(body, kind: "note", title: none)' in text
    assert "std.metadata((kind: kind, title: title))" in text
    assert "<cnd-admonition>" in text
    assert "<cnd-admonition-title>" in text
    assert "<cnd-admonition-end>" in text


def test_code_title_is_stored_as_code_title() -> None:
    text = (files("cnd") / "typst" / "cnd.typ").read_text(encoding="utf-8")
    assert "#let code(body, title: none)" in text
    assert '("code-title": title)' in text
    assert 'remove("code-title"' in text


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


def _query(tmp_path: Path, body: str, selector: str) -> list:
    package = (files("cnd") / "typst" / "cnd.typ").read_text(encoding="utf-8")
    (tmp_path / "cnd.typ").write_text(package, encoding="utf-8")
    doc = tmp_path / "doc.typ"
    doc.write_text('#import "/cnd.typ"\n' + body, encoding="utf-8")
    result = subprocess.run(
        ["typst", "query", "--root", str(tmp_path), str(doc), selector],
        capture_output=True,
        text=True,
        check=True,
    )
    return json.loads(result.stdout)


@needs_typst
def test_document_marker_is_queryable(tmp_path: Path) -> None:
    items = _query(
        tmp_path,
        '#cnd.document(status: "Approved", version: "1.2", extra: (client: "ACME"))\n',
        "<cnd-document>",
    )
    assert len(items) == 1
    assert items[0]["value"] == {
        "status": "Approved", "version": "1.2", "extra": {"client": "ACME"}
    }


@needs_typst
@pytest.mark.parametrize(
    "extra",
    ["(title: \"x\")", "(extra: \"x\")", "(version: \"x\")", "(n: 1)"],
)
def test_document_rejects_bad_extra(tmp_path: Path, extra: str) -> None:
    with pytest.raises(subprocess.CalledProcessError) as excinfo:
        _query(tmp_path, f"#cnd.document(extra: {extra})\n", "<cnd-document>")
    assert "cnd.document: extra" in excinfo.value.stderr, excinfo.value.stderr


@needs_typst
def test_admonition_brackets_its_body(tmp_path: Path) -> None:
    body = '#cnd.admonition(kind: "warning", title: "Careful")[Mind the gap.]\n'
    start = _query(tmp_path, body, "<cnd-admonition>")
    end = _query(tmp_path, body, "<cnd-admonition-end>")
    title = _query(tmp_path, body, "<cnd-admonition-title>")
    assert len(start) == 1 and len(end) == 1 and len(title) == 1
    assert start[0]["value"] == {"kind": "warning", "title": "Careful"}


@needs_typst
def test_admonition_without_title_has_no_title_element(tmp_path: Path) -> None:
    body = "#cnd.admonition[Plain.]\n"
    start = _query(tmp_path, body, "<cnd-admonition>")
    assert start[0]["value"] == {"kind": "note", "title": None}
    assert _query(tmp_path, body, "<cnd-admonition-title>") == []
    assert len(_query(tmp_path, body, "<cnd-admonition-end>")) == 1


@needs_typst
def test_code_title_bracket_is_removed_after(tmp_path: Path) -> None:
    states = _compile(
        tmp_path,
        '#cnd.code([#raw("x = 1") ' + _probe("inside") + '], title: "main.py")\n'
        + _probe("after") + "\n",
    )
    assert states["inside"] == {"code-title": "main.py"}
    assert states["after"] == {}
