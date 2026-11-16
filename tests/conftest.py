"""Shared pytest fixtures: every test gets its own temporary data folder."""
import pytest

from datapilot import settings
from datapilot.warehouse import seed


@pytest.fixture(autouse=True)
def tmp_data(tmp_path, monkeypatch):
    """Redirect every path in settings to a temp folder (your real data is never touched)."""
    monkeypatch.setattr(settings, "DATA_DIR", tmp_path)
    monkeypatch.setattr(settings, "WAREHOUSE_DB", tmp_path / "warehouse.db")
    monkeypatch.setattr(settings, "METRICS_DB", tmp_path / "metrics.db")
    monkeypatch.setattr(settings, "MEMORY_DB", tmp_path / "memory.db")
    monkeypatch.setattr(settings, "REPORTS_DIR", tmp_path / "reports")
    return tmp_path


@pytest.fixture
def warehouse(tmp_data):
    """A freshly generated warehouse (same data every time: random seed 42)."""
    seed.build()
    return settings.WAREHOUSE_DB