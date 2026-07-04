from pathlib import Path

import pytest

FIXTURES_DIR = Path(__file__).parent.parent / "fixtures"


@pytest.fixture
def minimal_manifest_path() -> Path:
    return FIXTURES_DIR / "minimal_manifest.json"


@pytest.fixture
def structured_manifest_path() -> Path:
    return FIXTURES_DIR / "structured_manifest.json"


@pytest.fixture
def comprehensive_manifest_path() -> Path:
    return FIXTURES_DIR / "comprehensive_manifest.json"
