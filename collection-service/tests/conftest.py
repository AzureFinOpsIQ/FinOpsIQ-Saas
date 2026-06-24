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
    settings = Settings(
        _env_file=None,
        AZURE_SUBSCRIPTION_ID="",
        AZURE_TENANT_ID="",
        AZURE_CLIENT_ID="",
        AZURE_CLIENT_SECRET="",
        AZURE_OPENAI_ENDPOINT="",
        AZURE_OPENAI_API_KEY="",
    )
    settings.data_raw_dir = str(tmp_path / "raw")
    settings.data_processed_dir = str(tmp_path / "processed")
    settings.data_embeddings_dir = str(tmp_path / "embeddings")
    settings.cost_lookback_days = 14
    settings.anomaly_zscore_threshold = 2.0
    settings.waste_idle_cpu_threshold = 5.0
    settings.waste_min_monthly_cost = 5.0
    return settings



