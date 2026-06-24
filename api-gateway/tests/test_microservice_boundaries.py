from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import jwt

from shared_lib.web.service import require_internal
from src.gateway_service.application import GatewayApplicationService


def test_microservice_entrypoints_are_http_adapters():
    from src.microservices.gateway_service import app

    assert hasattr(app, "state")
    assert app.state.application.__class__.__module__ == "src.gateway_service.application"


def test_service_dependency_manifests_exist():
    service_root = Path(__file__).resolve().parent.parent
    for path in (
        service_root / "requirements.txt",
        service_root / "base.txt",
        service_root / "Dockerfile",
    ):
        assert path.exists()
        assert path.read_text(encoding="utf-8").strip()


def test_internal_hs_token_accepts_configured_audience(test_settings):
    test_settings.auth_mode = "entra"
    test_settings.api_session_secret = "test-secret"
    test_settings.internal_api_audience = "api://internal-services"
    now = datetime.now(timezone.utc)
    token = jwt.encode(
        {
            "iss": "azure-cost-advisor",
            "aud": test_settings.internal_api_audience,
            "exp": now + timedelta(minutes=5),
        },
        test_settings.api_session_secret,
        algorithm="HS256",
    )
    request = SimpleNamespace(
        app=SimpleNamespace(state=SimpleNamespace(settings=test_settings)),
        headers={"Authorization": f"Bearer {token}"},
    )

    claims = require_internal(request)

    assert claims["aud"] == test_settings.internal_api_audience


def test_gateway_uses_hs_internal_token_without_managed_identity(test_settings):
    test_settings.auth_mode = "entra"
    test_settings.use_managed_identity = False
    test_settings.api_session_secret = "test-secret"
    test_settings.internal_api_audience = "api://internal-services"
    app = SimpleNamespace(
        state=SimpleNamespace(
            settings=test_settings,
            rate_windows={},
            breakers={},
        )
    )
    service = GatewayApplicationService(app)
    request = SimpleNamespace(app=app)

    authorization = service.internal_authorization_header(request)
    internal_request = SimpleNamespace(
        app=app,
        headers={"Authorization": authorization},
    )

    claims = require_internal(internal_request)

    assert authorization.startswith("Bearer ")
    assert claims["aud"] == test_settings.internal_api_audience
