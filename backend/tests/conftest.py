"""Pytest configuration ensuring repository root and packages are importable."""

import sys
import os
from pathlib import Path
import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
os.environ["ROVER_MODE"] = "simulator"
os.environ["MISSION_DB_PATH"] = ":memory:"
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


@pytest.fixture
def anyio_backend():
    """The application runtime is asyncio-based; no Trio dependency is required."""
    return "asyncio"
