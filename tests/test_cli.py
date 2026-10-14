"""The conformance CLI (docs/adr/0020).

Exit codes and `--json` shape are the contract here, not the prose: this
tool exists so another implementation can compare itself against it
mechanically, and a caller that cannot branch on the result cannot do
that.
"""

import json
from pathlib import Path

import pytest
import yaml

from cnd import Cnd, content_hash
from cnd.builder import build
from cnd.cli import main
from cnd.declaration import DECLARATION_VERSION, Declaration

FIXTURES = Path(__file__).parent.parent / "fixtures"
LEGACY = Path(__file__).parent / "legacy"


def _run(capsys, *argv) -> tuple[int, str, str]:
    code = main([str(a) for a in argv])
    captured = capsys.readouterr()
    return code, captured.out, captured.err


def _corpus() -> list[Path]:
    return sorted(FIXTURES.glob("*.cnd")) + sorted(
        FIXTURES.glob("declaration/*.cnd")
    )


class TestValidate:
    def test_the_whole_corpus_is_conformant(self, capsys) -> None:
        cnds = _corpus()
        code, out, _ = _run(capsys, "validate", *cnds)

        assert code == 0
        assert out.count(": ok") == len(cnds)

    def test_a_violation_exits_nonzero_and_names_the_rule(
        self, capsys, tmp_path: Path,
    ) -> None:
        broken = json.loads((FIXTURES / "rich_content.cnd").read_text())
        # A cites edge pointing at a figure: the label resolves — labels are
        # unique document-wide — but not in the family's domain.
        broken["nodes"][0]["children"][0]["text"]["cites"][0]["label"] = "lst-api"
        path = tmp_path / "broken.cnd"
        path.write_text(json.dumps(broken))

        code, _, err = _run(capsys, "validate", path)

        assert code == 1
        assert "link-wrong-domain" in err

    def test_json_output_is_machine_readable(self, capsys) -> None:
        code, out, _ = _run(capsys, "validate", "--json", FIXTURES / "minimal.cnd")

        [result] = json.loads(out)
        assert code == 0
        assert result["ok"] is True and result["violations"] == []

    def test_a_malformed_file_is_a_failure_not_a_crash(
        self, capsys, tmp_path: Path,
    ) -> None:
        path = tmp_path / "bad.cnd"
        path.write_text('{"cnd_version": "0.5.0"}')

        code, _, err = _run(capsys, "validate", path)

        assert code == 1
        assert "schema error" in err

    def test_a_missing_file_is_a_failure_not_a_crash(
        self, capsys, tmp_path: Path,
    ) -> None:
        code, _, err = _run(capsys, "validate", tmp_path / "absent.cnd")

        assert code == 1
        assert "cannot read" in err

    def test_one_bad_file_among_good_ones_still_fails(
        self, capsys, tmp_path: Path,
    ) -> None:
        """A batch is conformant only if every file in it is."""
        code, _, _ = _run(
            capsys, "validate", FIXTURES / "minimal.cnd", tmp_path / "absent.cnd"
        )

        assert code == 1


class TestVersionRefusal:
    """A file from another format version is refused by name, before its
    shape is checked: a 0.4 CND failing on "Input should be an object"
    never tells its reader that the version is the problem (spec §11)."""

    def test_a_real_0_4_cnd_is_refused_with_its_version(self, capsys) -> None:
        # main's minimal.cnd, a 0.3.0 file that parses unchanged as 0.4.0,
        # stamped 0.4.0.
        code, _, err = _run(capsys, "validate", LEGACY / "minimal-0.4.0.cnd")

        assert code == 1
        assert "cnd-version-unsupported" in err
        assert "0.4.0" in err and "0.5.0" in err
        assert "schema error" not in err

    @pytest.mark.parametrize("version", ["0.4.0", "9.9.9"])
    def test_a_0_5_shaped_cnd_stamped_with_another_version_is_refused(
        self, capsys, tmp_path: Path, version: str,
    ) -> None:
        data = json.loads((FIXTURES / "minimal.cnd").read_text(encoding="utf-8"))
        data["cnd_version"] = version
        path = tmp_path / "stamped.cnd"
        path.write_text(json.dumps(data), encoding="utf-8")

        code, out, err = _run(capsys, "validate", path)

        assert code == 1
        assert ": ok" not in out
        assert "cnd-version-unsupported" in err and version in err

    def test_hash_refuses_another_version_too(self, capsys) -> None:
        """A 0.5 hash of a 0.4 document means nothing: every loader
        refuses, not only validate."""
        code, out, err = _run(capsys, "hash", LEGACY / "minimal-0.4.0.cnd")

        assert code == 1
        assert out == ""
        assert "cnd-version-unsupported" in err

    def test_a_real_0_1_declaration_is_refused_with_its_version(
        self, capsys,
    ) -> None:
        # main's article.decl.yaml, byte for byte.
        code, out, err = _run(capsys, "build", LEGACY / "article-0.1.0.decl.yaml")

        assert code == 1
        assert out == ""
        assert "declaration-version-unsupported" in err
        assert "0.1.0" in err and DECLARATION_VERSION in err
        assert "Extra inputs" not in err


class TestHash:
    def test_it_reproduces_the_committed_vectors(self, capsys) -> None:
        """The oracle must agree with the corpus it is the oracle of."""
        vectors = json.loads((FIXTURES / "hashes.json").read_text())

        code, out, _ = _run(
            capsys, "hash", "--json", "--nodes", *sorted(FIXTURES.glob("*.cnd"))
        )

        assert code == 0
        for result in json.loads(out):
            expected = vectors[Path(result["file"]).name]
            assert result["content_hash"] == expected["content_hash"]
            assert result["node_hashes"] == expected["node_hashes"]

    def test_plain_output_is_hash_then_path(self, capsys) -> None:
        code, out, _ = _run(capsys, "hash", FIXTURES / "minimal.cnd")

        digest, path = out.split()
        assert code == 0
        assert digest.startswith("sha256:") and path.endswith("minimal.cnd")

    def test_node_hashes_are_omitted_unless_asked(self, capsys) -> None:
        _, out, _ = _run(capsys, "hash", "--json", FIXTURES / "minimal.cnd")

        assert "node_hashes" not in json.loads(out)[0]


class TestUsage:
    def test_no_command_is_a_usage_error(self, capsys) -> None:
        with pytest.raises(SystemExit) as exit_info:
            main([])

        assert exit_info.value.code == 2


class TestDiff:
    CASES = FIXTURES / "reconcile"

    def _pair(self, name: str) -> tuple[Path, Path]:
        return self.CASES / name / "old.cnd", self.CASES / name / "new.cnd"

    def test_it_reproduces_the_committed_matching_vectors(self, capsys) -> None:
        """The oracle must agree with the corpus it is the oracle of —
        the same bar `cnd hash` is held to."""
        vectors = json.loads((FIXTURES / "matching.json").read_text())

        for name, case in vectors["cases"].items():
            code, out, _ = _run(capsys, "diff", "--json", *self._pair(name))

            payload = json.loads(out)
            assert code == 0
            assert payload["matcher_version"] == vectors["matcher_version"]
            assert [
                {
                    "status": n["status"],
                    "matched_by": n["matched_by"],
                    "old_id": n["old_id"],
                    "new_id": n["new_id"],
                }
                for n in payload["nodes"]
            ] == case["nodes"], name

    def test_plain_output_names_the_pass_that_matched(self, capsys) -> None:
        """`via label` is a fact, `via hash` is a guess — a reader has to
        be able to tell them apart."""
        _, out, _ = _run(capsys, "diff", *self._pair("01-label-survives-edit-and-move"))

        assert "via label" in out
        assert "matching v2" in out

    def test_an_identical_pair_reports_nothing_changed(self, capsys) -> None:
        code, out, _ = _run(
            capsys, "diff", FIXTURES / "minimal.cnd", FIXTURES / "minimal.cnd"
        )

        assert code == 0
        assert "changed=0" in out and "added=0" in out and "removed=0" in out

    def test_an_unreadable_side_fails_without_crashing(self, capsys) -> None:
        code, _, err = _run(
            capsys, "diff", FIXTURES / "minimal.cnd", FIXTURES / "absent.cnd"
        )

        assert code == 1
        assert "cannot read" in err


class TestBuild:
    DECL = FIXTURES / "declaration" / "article.decl.yaml"

    def test_builds_a_declaration_to_stdout(self, capsys) -> None:
        code, out, _ = _run(capsys, "build", self.DECL)

        assert code == 0
        built = json.loads(out)
        assert built["cnd_version"] == "0.5.0"
        assert built["nodes"][0]["type"] == "heading"
        # Engine off by default: nothing numbered, so nothing written.
        assert "numbering" not in built["nodes"][0]

    def test_numbering_flag_runs_the_counter_engine(self, capsys) -> None:
        code, out, _ = _run(capsys, "build", "--numbering", self.DECL)

        assert code == 0
        assert json.loads(out)["nodes"][0]["numbering"] == {"value": "1"}

    def test_the_output_omits_default_valued_fields(self, capsys) -> None:
        """The SDK writer (docs/proposals/0013): no empty list, no null and
        no empty object is written, and the CND is the one `build` makes."""
        code, out, _ = _run(capsys, "build", self.DECL)

        assert code == 0
        assert ": []" not in out and ": null" not in out and ": {}" not in out
        decl = Declaration.model_validate(yaml.safe_load(self.DECL.read_text()))
        assert content_hash(Cnd.model_validate_json(out)) == content_hash(build(decl))

    def test_output_flag_writes_a_file(self, capsys, tmp_path: Path) -> None:
        target = tmp_path / "article.cnd"

        code, out, _ = _run(capsys, "build", self.DECL, "-o", target)

        assert code == 0
        assert out == ""
        assert json.loads(target.read_text())["cnd_version"] == "0.5.0"

    def test_unbuildable_declaration_exits_nonzero_with_rules(
        self, capsys, tmp_path: Path,
    ) -> None:
        decl = {
            "declaration_version": DECLARATION_VERSION,
            "doc": {"title": "T"},
            "nodes": [
                {"type": "paragraph",
                 "text": {"value": "a", "refs": [{"label": "ghost"}]}},
            ],
        }
        path = tmp_path / "bad.decl.json"
        path.write_text(json.dumps(decl))

        code, _, err = _run(capsys, "build", path)

        assert code == 1
        assert "link-unresolved" in err
        assert "@ghost" in err

    def test_a_stray_key_is_rejected_not_dropped(
        self, capsys, tmp_path: Path,
    ) -> None:
        decl = {
            "declaration_version": DECLARATION_VERSION,
            "doc": {"title": "T"},
            "nodes": [{"type": "paragraph", "text": "a", "capton": "typo"}],
        }
        path = tmp_path / "typo.decl.json"
        path.write_text(json.dumps(decl))

        code, _, err = _run(capsys, "build", path)

        assert code == 1
        assert "capton" in err

    def test_authored_numbering_needs_the_flag(
        self, capsys, tmp_path: Path,
    ) -> None:
        decl = {
            "declaration_version": DECLARATION_VERSION,
            "doc": {"title": "T"},
            "nodes": [{"type": "math", "text": "x", "numbering": {"name": "Eq."}}],
        }
        path = tmp_path / "eq.decl.json"
        path.write_text(json.dumps(decl))

        code, _, err = _run(capsys, "build", path)
        assert code == 1
        assert "numbering-without-engine" in err

        code, out, _ = _run(capsys, "build", "--numbering", path)
        assert code == 0
        assert json.loads(out)["nodes"][0]["numbering"] == {
            "value": "(1)",
            "name": "Eq.",
        }

    def test_yaml_without_pyyaml_names_the_extra(
        self, capsys, monkeypatch,
    ) -> None:
        import builtins

        real_import = builtins.__import__

        def _no_yaml(name, *args, **kwargs):
            if name == "yaml":
                raise ImportError("No module named 'yaml'")
            return real_import(name, *args, **kwargs)

        monkeypatch.setattr(builtins, "__import__", _no_yaml)

        code, _, err = _run(capsys, "build", self.DECL)

        assert code == 1
        assert "cnd-sdk[yaml]" in err


class TestInspect:
    def test_the_whole_corpus_inspects(self, capsys) -> None:
        """Terminal inspection is a conformance verb (ADR 0020): every
        0.5 node type is displayed, none falls through."""
        code, out, _ = _run(capsys, "inspect", *_corpus())

        assert code == 0
        assert "ADMONITION" in out.upper() and "LAYOUT" in out.upper()

    def test_an_unreadable_file_fails_without_crashing(
        self, capsys, tmp_path: Path,
    ) -> None:
        code, _, err = _run(capsys, "inspect", tmp_path / "absent.cnd")

        assert code == 1
        assert "cannot read" in err
