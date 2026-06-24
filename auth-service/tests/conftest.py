"""Service-local pytest fixtures."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

_SERVICE_ROOT = Path(__file__).resolve().parent.parent
for path in (_SERVICE_ROOT / "src", _SERVICE_ROOT / "shared-lib"):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from shared_lib.configuration import Settings  # noqa: E402


@pytest.fixture
def test_settings(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Settings:
    monkeypatch.setattr(Settings, "project_root", property(lambda self: _SERVICE_ROOT))
    return Settings(
        _env_file=None,
        AZURE_SUBSCRIPTION_ID="",
        AZURE_TENANT_ID="",
        AZURE_CLIENT_ID="",
        AZURE_CLIENT_SECRET="",
        AZURE_OPENAI_ENDPOINT="",
        AZURE_OPENAI_API_KEY="",
        DATA_RAW_DIR=str(tmp_path / "raw"),
        DATA_PROCESSED_DIR=str(tmp_path / "processed"),
        DATA_EMBEDDINGS_DIR=str(tmp_path / "embeddings"),
        COST_LOOKBACK_DAYS=14,
        ANOMALY_ZSCORE_THRESHOLD=2.0,
        WASTE_IDLE_CPU_THRESHOLD=5.0,
        WASTE_MIN_MONTHLY_COST=5.0,
    )



