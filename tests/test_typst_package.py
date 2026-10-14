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
