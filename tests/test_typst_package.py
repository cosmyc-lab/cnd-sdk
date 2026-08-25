"""The Typst authoring package ships inside the installed wheel."""

from importlib.resources import files


def test_typst_package_ships_in_wheel() -> None:
    text = (files("cnd") / "typst" / "cnd.typ").read_text(encoding="utf-8")
    assert 'state("cnd.metadata"' in text
    assert "content_kind" in text
