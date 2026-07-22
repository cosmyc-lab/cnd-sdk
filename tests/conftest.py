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
