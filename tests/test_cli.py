"""The conformance CLI (docs/adr/0020).

Exit codes and `--json` shape are the contract here, not the prose: this
tool exists so another implementation can compare itself against it
mechanically, and a caller that cannot branch on the result cannot do
that.
"""

import json
from pathlib import Path

import pytest

from cnd.cli import main

FIXTURES = Path(__file__).parent.parent / "fixtures"


def _run(capsys, *argv) -> tuple[int, str, str]:
    code = main([str(a) for a in argv])
    captured = capsys.readouterr()
    return code, captured.out, captured.err


class TestValidate:
    def test_the_whole_corpus_is_conformant(self, capsys) -> None:
        code, out, _ = _run(capsys, "validate", *sorted(FIXTURES.glob("*.cnd")))

        assert code == 0
        assert out.count(": ok") == len(list(FIXTURES.glob("*.cnd")))

    def test_a_violation_exits_nonzero_and_names_the_rule(
        self, capsys, tmp_path: Path,
    ) -> None:
        broken = json.loads((FIXTURES / "rich_content.cnd").read_text())
        # A cites edge pointing at a figure: the label resolves — labels are
        # unique document-wide — but not in the family's domain.
        broken["nodes"][0]["children"][0]["cites"][0]["label"] = "lst-api"
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
        path.write_text('{"cnd_version": "0.3.0"}')

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
        assert "matching v1" in out

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
