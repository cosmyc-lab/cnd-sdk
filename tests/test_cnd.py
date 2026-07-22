from pathlib import Path
from uuid import uuid4

from ids import (
    HEADING002_ID,
    PARA001_ID,
    RICH_BIB_ENTRY_ID,
    RICH_FIG_CODE_ID,
    RICH_FOOTNOTE_ID,
    RICH_PARA_ID,
    TABLE001_ID,
)

from cnd.core.cnd import Cnd


def _load(path: Path) -> Cnd:
    return Cnd.model_validate_json(path.read_text())


class TestIncoming:
    def test_incoming_lists_nodes_whose_refs_target_the_id(
        self, structured_cnd_path: Path,
    ) -> None:
        cnd = _load(structured_cnd_path)

        sources = cnd.incoming(TABLE001_ID)

        assert [node.id for node in sources] == [HEADING002_ID, PARA001_ID]

    def test_incoming_is_empty_for_untargeted_node(
        self, structured_cnd_path: Path,
    ) -> None:
        cnd = _load(structured_cnd_path)

        assert cnd.incoming(HEADING002_ID) == []
        assert cnd.incoming(uuid4()) == []

    def test_incoming_covers_cites_and_footnotes_pools(
        self, rich_content_cnd_path: Path,
    ) -> None:
        cnd = _load(rich_content_cnd_path)

        assert [n.id for n in cnd.incoming(RICH_BIB_ENTRY_ID)] == [RICH_PARA_ID]
        assert [n.id for n in cnd.incoming(RICH_FOOTNOTE_ID)] == [RICH_PARA_ID]
        assert [n.id for n in cnd.incoming(RICH_FIG_CODE_ID)] == [RICH_PARA_ID]

    def test_incoming_index_is_cached_on_the_instance(
        self, structured_cnd_path: Path,
    ) -> None:
        cnd = _load(structured_cnd_path)

        assert cnd._incoming_index is None
        cnd.incoming(TABLE001_ID)
        first = cnd._incoming_index
        assert first is not None
        cnd.incoming(PARA001_ID)
        assert cnd._incoming_index is first


class TestPools:
    def test_pools_default_to_empty_lists(self, minimal_cnd_path: Path) -> None:
        cnd = _load(minimal_cnd_path)

        assert cnd.bibliography == []
        assert cnd.footnotes == []

    def test_bibliography_entry_round_trips(
        self, rich_content_cnd_path: Path,
    ) -> None:
        cnd = _load(rich_content_cnd_path)

        [entry] = cnd.bibliography
        assert entry.id == RICH_BIB_ENTRY_ID
        assert entry.label == "smith2024"
        assert entry.rendered.startswith("Smith, J., & Doe, A. (2024).")
        assert entry.year == 2024
        assert entry.raw["parent"]["title"] == "Journal of Systems Integration"

    def test_footnote_entry_round_trips(
        self, rich_content_cnd_path: Path,
    ) -> None:
        cnd = _load(rich_content_cnd_path)

        [footnote] = cnd.footnotes
        assert footnote.id == RICH_FOOTNOTE_ID
        assert footnote.label == "fn-rest"
        assert footnote.text == "REST : Representational State Transfer."

    def test_link_families_and_spans_parse(
        self, rich_content_cnd_path: Path,
    ) -> None:
        cnd = _load(rich_content_cnd_path)
        para = next(v.node for v in cnd.iter() if v.node.id == RICH_PARA_ID)

        [ref] = para.refs
        assert ref.id == RICH_FIG_CODE_ID
        assert ref.text_span == [77, 88]

        [cite] = para.cites
        assert cite.id == RICH_BIB_ENTRY_ID
        assert cite.form == "prose"
        assert cite.supplement == "p. 12"
        assert cite.text_span == [6, 18]

        [footnote_ref] = para.footnotes
        assert footnote_ref.id == RICH_FOOTNOTE_ID
        assert footnote_ref.text_span == [57, 61]

    def test_link_label_mirrors_target_label(
        self, rich_content_cnd_path: Path,
    ) -> None:
        cnd = _load(rich_content_cnd_path)
        para = next(v.node for v in cnd.iter() if v.node.id == RICH_PARA_ID)
        figure = next(v.node for v in cnd.iter() if v.node.id == RICH_FIG_CODE_ID)

        assert para.refs[0].label == figure.label == "lst-api"
        assert para.cites[0].label == cnd.bibliography[0].label
        assert para.footnotes[0].label == cnd.footnotes[0].label
