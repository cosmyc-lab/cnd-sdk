from pathlib import Path

from ids import (
    HEADING002_ID,
    HEADING002_LABEL,
    PARA001_ID,
    RICH_BIB_ENTRY_ID,
    RICH_BIB_ENTRY_LABEL,
    RICH_FIG_CODE_LABEL,
    RICH_FOOTNOTE_ID,
    RICH_FOOTNOTE_LABEL,
    RICH_PARA_ID,
    TABLE001_LABEL,
)

from cnd import BibEntry, Cnd, FigureNode, Footnote


def _load(path: Path) -> Cnd:
    return Cnd.model_validate_json(path.read_text())


class TestIncoming:
    def test_incoming_lists_nodes_whose_refs_target_the_label(
        self, structured_cnd_path: Path,
    ) -> None:
        cnd = _load(structured_cnd_path)

        sources = cnd.incoming(TABLE001_LABEL)

        assert [node.id for node in sources] == [HEADING002_ID, PARA001_ID]

    def test_incoming_is_empty_for_untargeted_node(
        self, structured_cnd_path: Path,
    ) -> None:
        cnd = _load(structured_cnd_path)

        assert cnd.incoming(HEADING002_LABEL) == []
        assert cnd.incoming("no-such-label") == []

    def test_incoming_covers_cites_and_footnotes_pools(
        self, rich_content_cnd_path: Path,
    ) -> None:
        cnd = _load(rich_content_cnd_path)

        assert [n.id for n in cnd.incoming(RICH_BIB_ENTRY_LABEL)] == [RICH_PARA_ID]
        assert [n.id for n in cnd.incoming(RICH_FOOTNOTE_LABEL)] == [RICH_PARA_ID]
        assert [n.id for n in cnd.incoming(RICH_FIG_CODE_LABEL)] == [RICH_PARA_ID]

    def test_incoming_index_is_cached_on_the_instance(
        self, structured_cnd_path: Path,
    ) -> None:
        cnd = _load(structured_cnd_path)

        assert cnd._incoming_index is None
        cnd.incoming(TABLE001_LABEL)
        first = cnd._incoming_index
        assert first is not None
        cnd.incoming(HEADING002_LABEL)
        assert cnd._incoming_index is first


class TestResolve:
    def test_resolve_finds_a_node_by_label(self, structured_cnd_path: Path) -> None:
        cnd = _load(structured_cnd_path)

        target = cnd.resolve(TABLE001_LABEL)

        assert target is not None and target.label == TABLE001_LABEL

    def test_resolve_finds_pool_entries(self, rich_content_cnd_path: Path) -> None:
        cnd = _load(rich_content_cnd_path)

        assert cnd.resolve(RICH_BIB_ENTRY_LABEL).id == RICH_BIB_ENTRY_ID
        assert cnd.resolve(RICH_FOOTNOTE_LABEL) is not None

    def test_resolve_is_none_for_an_unknown_label(
        self, structured_cnd_path: Path,
    ) -> None:
        assert _load(structured_cnd_path).resolve("no-such-label") is None


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
        assert entry.formatted.startswith("Smith, J., & Doe, A. (2024).")
        assert entry.year == 2024
        assert entry.fields["parent"]["title"] == "Journal of Systems Integration"

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
        assert ref.label == RICH_FIG_CODE_LABEL
        assert ref.text_span == [77, 88]

        [cite] = para.cites
        assert cite.label == RICH_BIB_ENTRY_LABEL
        assert cite.form == "prose"
        assert cite.supplement == "p. 12"
        assert cite.text_span == [6, 18]

        [footnote_ref] = para.footnotes
        assert footnote_ref.label == RICH_FOOTNOTE_LABEL
        assert footnote_ref.text_span == [57, 61]

    def test_each_link_family_resolves_in_its_own_domain(
        self, rich_content_cnd_path: Path,
    ) -> None:
        cnd = _load(rich_content_cnd_path)
        para = next(v.node for v in cnd.iter() if v.node.id == RICH_PARA_ID)

        assert isinstance(cnd.resolve(para.refs[0].label), FigureNode)
        assert isinstance(cnd.resolve(para.cites[0].label), BibEntry)
        assert isinstance(cnd.resolve(para.footnotes[0].label), Footnote)


class TestPagination:
    """An unpaginated CND — a markdown or hand-authored source has no pages,
    and forcing ``page: 1`` there fabricates data indistinguishable from a
    real page 1 (docs/proposals/0008)."""

    def test_paginated_is_derived_not_serialized(
        self, unpaginated_cnd_path: Path, minimal_cnd_path: Path,
    ) -> None:
        assert _load(unpaginated_cnd_path).paginated is False
        assert _load(minimal_cnd_path).paginated is True
        assert "paginated" not in unpaginated_cnd_path.read_text()

    def test_no_node_carries_a_location(self, unpaginated_cnd_path: Path) -> None:
        cnd = _load(unpaginated_cnd_path)

        assert all(v.node.location is None for v in cnd.iter())

    def test_page_positions_are_undefined_not_zero(
        self, unpaginated_cnd_path: Path,
    ) -> None:
        cnd = _load(unpaginated_cnd_path)

        for visit in cnd.iter():
            assert visit.ctx.page_index is None
            assert visit.ctx.page_count is None
            # The order-derived positions still hold — they come from the
            # tree, not from pages.
            assert visit.ctx.doc_index >= 1
            assert visit.ctx.doc_count == 4

    def test_links_still_resolve_without_pages(
        self, unpaginated_cnd_path: Path,
    ) -> None:
        cnd = _load(unpaginated_cnd_path)

        assert isinstance(cnd.resolve("lst-open"), FigureNode)
        assert isinstance(cnd.resolve("fn-token"), Footnote)
        assert [n.label for n in cnd.incoming("lst-open")] == [None]

    def test_bib_entry_may_carry_structured_fields_without_formatted(
        self, unpaginated_cnd_path: Path,
    ) -> None:
        [entry] = _load(unpaginated_cnd_path).bibliography

        assert entry.formatted is None
        assert entry.title and entry.year == 1978

    def test_doc_metadata_defaults_are_omittable(
        self, unpaginated_cnd_path: Path,
    ) -> None:
        doc = _load(unpaginated_cnd_path).doc

        assert doc.authors == [] and doc.keywords == []
