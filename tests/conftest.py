"""Shared fixtures for ista_no integration tests."""

from __future__ import annotations

import os
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from dotenv import load_dotenv


def _create_ha_stubs():
    """Create stub modules for homeassistant so the package can be imported."""
    if "homeassistant" not in sys.modules:
        for sub in [
            "homeassistant",
            "homeassistant.config_entries",
            "homeassistant.const",
            "homeassistant.core",
            "homeassistant.exceptions",
            "homeassistant.helpers",
            "homeassistant.helpers.update_coordinator",
            "homeassistant.helpers.entity_platform",
            "homeassistant.components",
            "homeassistant.components.sensor",
            "homeassistant.components.recorder",
            "homeassistant.components.recorder.models",
            "homeassistant.components.recorder.statistics",
        ]:
            sys.modules[sub] = MagicMock()


def pytest_configure(config):
    """Load .env file and set up stubs before tests run."""
    env_path = Path(__file__).parent.parent / ".env"
    load_dotenv(env_path)
    _create_ha_stubs()

    cc_path = str(Path(__file__).parent.parent / "custom_components")
    if cc_path not in sys.path:
        sys.path.insert(0, cc_path)


@pytest.fixture
def ista_credentials() -> dict[str, str]:
    """Return ista credentials from environment variables."""
    username = os.environ.get("ISTA_USERNAME")
    password = os.environ.get("ISTA_PASSWORD")
    if not username or not password:
        pytest.skip(
            "ISTA_USERNAME and ISTA_PASSWORD must be set in .env to run integration tests"
        )
    return {"username": username, "password": password}
