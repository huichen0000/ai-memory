from pathlib import Path

import pytest


@pytest.fixture
def memory_home(tmp_path: Path) -> Path:
    return tmp_path / ".ai-memory"
