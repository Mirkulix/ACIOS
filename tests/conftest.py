"""Shared fixtures for AICOS tests."""

import os
import sys
from pathlib import Path

import pytest

# Ensure project root is on sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

os.chdir(PROJECT_ROOT)


@pytest.fixture(autouse=True)
def reset_shared_state():
    """Reset the SharedState singleton between tests."""
    from core.state import SharedState
    SharedState.reset()
    yield
    SharedState.reset()
