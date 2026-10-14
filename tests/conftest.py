from pathlib import Path

import pytest

FIXTURES_DIR = Path(__file__).parent.parent / "fixtures"


@pytest.fixture
def minimal_cnd_path() -> Path:
    return FIXTURES_DIR / "minimal.cnd"


@pytest.fixture
def structured_cnd_path() -> Path:
    return FIXTURES_DIR / "structured.cnd"


@pytest.fixture
def comprehensive_cnd_path() -> Path:
    return FIXTURES_DIR / "comprehensive.cnd"


@pytest.fixture
def rich_content_cnd_path() -> Path:
    return FIXTURES_DIR / "rich_content.cnd"


@pytest.fixture
def full_coverage_cnd_path() -> Path:
    return FIXTURES_DIR / "full_coverage.cnd"


@pytest.fixture
def unpaginated_cnd_path() -> Path:
    return FIXTURES_DIR / "unpaginated.cnd"


@pytest.fixture
def elements_cnd_path() -> Path:
    return FIXTURES_DIR / "elements.cnd"


# Test modules not yet ported to format 0.5.0 (docs/proposals/0013). The
# 0.5 series lands plan by plan on one integration branch; each plan
# removes the entries it ports, and the list must be empty before that
# branch merges into main.
collect_ignore = [
    "test_builder.py",
    "test_cli.py",
    "test_node_display_visitor.py",
    "test_reconcile.py",
    "test_visitor.py",
]
