"""Kitchen-sink fixture coverage: every node type/variant, link family,
and pool feature of format 0.2.0, exercised through the public SDK surface.

The generic rendering sweep (all fixtures x all verbosity modes) lives in
test_render.py and picks this fixture up automatically; the tests here pin
the behaviors the fixture was built to exercise."""

from pathlib import Path

from ids import (
    FULL_BARE_IMAGE_ID,
    FULL_BIB_FULL_ID,
    FULL_BIB_MINIMAL_ID,
    FULL_FIG_ATOM_ID,
    FULL_FIG_CODE_ID,
    FULL_FIG_OUTER_ID,
    FULL_FIG_RAW_ONLY_ID,
    FULL_FIG_SUB_A_ID,
    FULL_FIG_SUB_B_ID,
    FULL_FIG_TABLE_ID,
    FULL_FOOTNOTE_PROTO_ID,
    FULL_FOOTNOTE_UNIT_ID,
    FULL_GRID_ID,
    FULL_PARA_INTRO_ID,
    FULL_PARA_REFS_ID,
    FULL_PATHLESS_IMAGE_ID,
    FULL_SUB_A_IMAGE_ID,
    FULL_TABLE_CONTENT_ID,
    FULL_WRAPPED_CODE_ID,
)

from cnd.core.manifest import CndManifest
from cnd.core.nodes import CndNode, FigureNode, ImageNode, ListNode, TableNode
from cnd.core.render import MarkdownRenderer

FIXTURE_PATH = Path(__file__).parent.parent / "fixtures" / "full_coverage_manifest.json"


def _load() -> CndManifest:
    return CndManifest.model_validate_json(FIXTURE_PATH.read_text())


def _node(manifest: CndManifest, node_id) -> CndNode:
    return next(v.node for v in manifest.iter() if v.node.id == node_id)


class TestFixtureShape:
    def test_ids_are_globally_unique_across_nodes_and_pools(self) -> None:
        manifest = _load()
        ids = [v.node.id for v in manifest.iter()]
        ids += [entry.id for entry in manifest.bibliography]
        ids += [note.id for note in manifest.footnotes]
        assert len(ids) == len(set(ids))

    def test_covers_every_node_type(self) -> None:
        manifest = _load()
        seen = {v.node.type for v in manifest.iter()}
        assert seen == {
            "heading",
            "paragraph",
            "table",
            "quote",
            "code",
            "math",
            "figure",
            "image",
            "list",
            "terms",
        }

    def test_covers_table_and_list_variants(self) -> None:
        manifest = _load()
        tables = [v.node for v in manifest.iter() if isinstance(v.node, TableNode)]
        assert {t.kind for t in tables} == {"table", "grid"}
        assert {t.content_kind for t in tables} == {"content", "data"}
        grid = _node(manifest, FULL_GRID_ID)
        assert any(c.rowspan > 1 for c in grid.cells)
        assert any(c.colspan > 1 for c in grid.cells)
        assert any(c.is_header for c in grid.cells)

        lists = [v.node for v in manifest.iter() if isinstance(v.node, ListNode)]
        assert {lst.ordered for lst in lists} == {True, False}
        assert {lst.tight for lst in lists} == {True, False}
        assert any(item.children for lst in lists for item in lst.items)

    def test_covers_cite_form_variants(self) -> None:
        manifest = _load()
        forms = {
            cite.form for v in manifest.iter() for cite in v.node.cites
        }
        assert forms == {"normal", "prose", "full", "author", "year", "none"}
        supplements = [
            cite.supplement
            for v in manifest.iter()
            for cite in v.node.cites
            if cite.supplement
        ]
        assert supplements == ["p. 42"]

    def test_refs_with_and_without_span(self) -> None:
        manifest = _load()
        spans = [ref.text_span for v in manifest.iter() for ref in v.node.refs]
        assert any(span is not None for span in spans)
        assert any(span is None for span in spans)


class TestIncomingResolution:
    def test_incoming_resolves_a_node_target(self) -> None:
        manifest = _load()
        sources = manifest.incoming(FULL_FIG_TABLE_ID)
        assert [n.id for n in sources] == [FULL_PARA_INTRO_ID]

    def test_incoming_resolves_a_bibliography_target_via_cites(self) -> None:
        manifest = _load()
        sources = manifest.incoming(FULL_BIB_FULL_ID)
        assert {n.id for n in sources} == {FULL_PARA_INTRO_ID, FULL_PARA_REFS_ID}
        # para-intro cites this entry twice; incoming() returns it once.
        assert len(sources) == 2

    def test_incoming_resolves_a_footnote_target(self) -> None:
        manifest = _load()
        assert [n.id for n in manifest.incoming(FULL_FOOTNOTE_UNIT_ID)] == [
            FULL_PARA_INTRO_ID
        ]
        assert [n.id for n in manifest.incoming(FULL_FOOTNOTE_PROTO_ID)] == [
            FULL_PARA_REFS_ID
        ]

    def test_form_none_cite_has_no_span_and_still_resolves(self) -> None:
        manifest = _load()
        para = _node(manifest, FULL_PARA_REFS_ID)

        [none_cite] = [c for c in para.cites if c.form == "none"]
        assert none_cite.text_span is None
        assert none_cite.id == FULL_BIB_MINIMAL_ID
        assert FULL_PARA_REFS_ID in {n.id for n in manifest.incoming(FULL_BIB_MINIMAL_ID)}

    def test_pool_entries_resolve_by_id(self) -> None:
        manifest = _load()
        full = next(e for e in manifest.bibliography if e.id == FULL_BIB_FULL_ID)
        minimal = next(e for e in manifest.bibliography if e.id == FULL_BIB_MINIMAL_ID)
        assert full.raw["parent"]["volume"] == 8
        assert minimal.type is None and minimal.authors == [] and minimal.raw == {}
        assert len(manifest.footnotes) == 2


class TestFigureTraversal:
    def test_figure_children_are_traversed_by_default(self) -> None:
        manifest = _load()
        ids = {v.node.id for v in manifest.iter()}
        # Wrapped content, including a nested subfigure's image, is reached.
        assert FULL_TABLE_CONTENT_ID in ids
        assert FULL_WRAPPED_CODE_ID in ids
        assert FULL_FIG_SUB_A_ID in ids
        assert FULL_SUB_A_IMAGE_ID in ids

    def test_stop_predicate_makes_figures_atomic(self) -> None:
        manifest = _load()
        ids = {
            v.node.id
            for v in manifest.iter(
                stop_predicate=lambda node, _ctx: node.type == "figure"
            )
        }
        # The wrappers themselves are still visited...
        assert {FULL_FIG_TABLE_ID, FULL_FIG_OUTER_ID, FULL_FIG_ATOM_ID} <= ids
        # ...but nothing inside any figure is.
        assert FULL_TABLE_CONTENT_ID not in ids
        assert FULL_WRAPPED_CODE_ID not in ids
        assert FULL_FIG_SUB_A_ID not in ids
        assert FULL_SUB_A_IMAGE_ID not in ids
        # Bare in-tree content outside figures is unaffected.
        assert FULL_GRID_ID in ids
        assert FULL_BARE_IMAGE_ID in ids


class TestRendering:
    def test_null_path_image_renders_bracket_placeholder(self) -> None:
        manifest = _load()
        image = _node(manifest, FULL_PATHLESS_IMAGE_ID)
        assert isinstance(image, ImageNode)
        rendered = MarkdownRenderer().render(image)
        assert rendered == (
            f'[[image:{FULL_PATHLESS_IMAGE_ID} alt="Image incorporée sans chemin extrait"]]'
        )

    def test_figure_wrapping_code_renders_in_both_modes(self) -> None:
        manifest = _load()
        figure = _node(manifest, FULL_FIG_CODE_ID)
        placeholder = MarkdownRenderer().render(figure)
        assert placeholder.startswith(f"[[figure:{figure.id} ")
        assert 'kind="listing"' in placeholder
        assert 'summary="code (json)"' in placeholder

        inline = MarkdownRenderer(figures="inline").render(figure)
        assert inline.startswith("```json\n")
        assert inline.endswith("*Listing 1: Configuration de l'acquisition.*")

    def test_nested_figures_render_inline_recursively(self) -> None:
        manifest = _load()
        outer = _node(manifest, FULL_FIG_OUTER_ID)
        assert isinstance(outer, FigureNode)
        assert all(isinstance(child, FigureNode) for child in outer.children)
        assert {child.id for child in outer.children} == {
            FULL_FIG_SUB_A_ID,
            FULL_FIG_SUB_B_ID,
        }

        rendered = MarkdownRenderer(figures="inline").render(outer)
        assert "![Courbe avant étalonnage](figures/avant.png)" in rendered
        assert "*(a) Avant étalonnage.*" in rendered
        assert "![Courbe après étalonnage](figures/apres.png)" in rendered
        assert "*(b) Après étalonnage.*" in rendered
        assert rendered.endswith("*Figure 2: Comparaison avant/après étalonnage.*")

    def test_unconvertible_figure_renders_placeholder_even_inline(self) -> None:
        manifest = _load()
        figure = _node(manifest, FULL_FIG_RAW_ONLY_ID)
        assert isinstance(figure, FigureNode)
        assert figure.children == []
        assert figure.raw_typst is not None

        for renderer in (MarkdownRenderer(), MarkdownRenderer(figures="inline")):
            rendered = renderer.render(figure)
            assert rendered.startswith(f"[[figure:{figure.id} ")
            assert 'kind="canvas"' in rendered
