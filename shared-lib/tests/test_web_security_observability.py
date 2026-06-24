from __future__ import annotations

import base64
import json
from types import SimpleNamespace

import jwt
import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from shared_lib.configuration import Settings
from shared_lib.observability import configure_observability, measure
from shared_lib.observability.audit import write_audit_event
from shared_lib.security import (
    RequestIdentity,
    SessionTokenService,
    get_identity,
    subscription_scope,
    tenant_scope,
)
from shared_lib.web.middleware import ApiMetrics
from shared_lib.web.service import (
    _entra_tenant_for_key_discovery,
    _jwt_claims_for_key_discovery,
    require_internal,
    service_app,
)


def unsigned_token(payload) -> str:
    encoded = base64.urlsafe_b64encode(json.dumps(payload).encode("utf-8")).decode("ascii").rstrip("=")
    return f"header.{encoded}.signature"


def test_jwt_key_discovery_rejects_invalid_payload_shapes():
    with pytest.raises(jwt.InvalidTokenError, match="payload must be an object"):
        _jwt_claims_for_key_discovery(unsigned_token(["not", "an", "object"]))

    with pytest.raises(jwt.InvalidTokenError, match="Invalid Entra tenant"):
        _entra_tenant_for_key_discovery(unsigned_token({"tid": "../bad"}))


def test_require_internal_accepts_local_mode_and_fallback_audience():
    local_request = SimpleNamespace(
        app=SimpleNamespace(state=SimpleNamespace(settings=Settings(AUTH_MODE="legacy"))),
        headers={},
    )
    assert require_internal(local_request) == {"appid": "local-development"}

    settings = Settings(AUTH_MODE="entra", API_SESSION_SECRET="a-secure-test-secret-with-enough-length")
    token = jwt.encode(
        {
            "iss": "azure-cost-advisor",
            "aud": "azure-cost-advisor-api",
            "appid": "legacy-audience-client",
        },
        settings.api_session_secret,
        algorithm="HS256",
    )
    request = SimpleNamespace(
        app=SimpleNamespace(state=SimpleNamespace(settings=settings)),
        headers={"Authorization": f"Bearer {token}"},
    )

    assert require_internal(request)["appid"] == "legacy-audience-client"


def test_require_internal_rejects_invalid_signed_token():
    settings = Settings(AUTH_MODE="entra", API_SESSION_SECRET="a-secure-test-secret-with-enough-length")
    token = jwt.encode(
        {"iss": "wrong", "aud": settings.internal_api_audience, "appid": "client"},
        "different-secret",
        algorithm="HS256",
    )
    request = SimpleNamespace(
        app=SimpleNamespace(state=SimpleNamespace(settings=settings)),
        headers={"Authorization": f"Bearer {token}"},
    )

    with pytest.raises(HTTPException) as exc_info:
        require_internal(request)

    assert exc_info.value.status_code == 401


def test_identity_scopes_authorize_tenant_and_selected_subscription():
    identity = RequestIdentity("tenant-1", "user-1", "u@example.com", "User", ("tenant_admin",))
    request = SimpleNamespace(headers={"X-Tenant-ID": "tenant-1"}, app=SimpleNamespace(state=SimpleNamespace(settings=Settings())))
    assert tenant_scope(request, identity) == "tenant-1"

    with pytest.raises(HTTPException) as tenant_error:
        tenant_scope(SimpleNamespace(headers={"X-Tenant-ID": "tenant-2"}), identity)
    assert tenant_error.value.status_code == 403

    platform_admin = RequestIdentity("tenant-1", "admin", "", "Admin", ("platform_admin",))
    assert tenant_scope(SimpleNamespace(headers={"X-Tenant-ID": "tenant-2"}), platform_admin) == "tenant-2"

    selected = SimpleNamespace(subscription_id="sub-1", selected=True)
    unselected = SimpleNamespace(subscription_id="sub-2", selected=False)
    storage = SimpleNamespace(subscriptions=SimpleNamespace(list=lambda tenant_id: [selected, unselected]))
    scoped_request = SimpleNamespace(
        headers={"X-Subscription-ID": "sub-1"},
        app=SimpleNamespace(state=SimpleNamespace(settings=Settings(DEFAULT_SUBSCRIPTION_ID="sub-default"), storage=storage)),
    )
    assert subscription_scope(scoped_request, identity, "tenant-1") == "sub-1"

    denied_request = SimpleNamespace(headers={"X-Subscription-ID": "sub-2"}, app=scoped_request.app)
    with pytest.raises(HTTPException) as sub_error:
        subscription_scope(denied_request, identity, "tenant-1")
    assert sub_error.value.status_code == 403


def test_get_identity_requires_session_when_entra_enabled():
    request = SimpleNamespace(
        app=SimpleNamespace(state=SimpleNamespace(settings=Settings(AUTH_MODE="entra"))),
        cookies={},
        headers={},
    )

    with pytest.raises(HTTPException) as exc_info:
        get_identity(request)

    assert exc_info.value.status_code == 401


def test_session_decode_rejects_missing_identity_claims():
    settings = Settings(API_SESSION_SECRET="a-secure-test-secret-with-enough-length")
    token = jwt.encode(
        {
            "iss": "azure-cost-advisor",
            "aud": "azure-cost-advisor-api",
            "iat": 1,
            "exp": 4102444800,
        },
        settings.api_session_secret,
        algorithm="HS256",
    )

    with pytest.raises(HTTPException) as exc_info:
        SessionTokenService(settings).decode(token)

    assert exc_info.value.status_code == 401


def test_api_metrics_snapshot_and_service_app_health_routes(monkeypatch):
    class FakeTenants:
        def __init__(self) -> None:
            self.fail = False

        def list(self):
            if self.fail:
                raise RuntimeError("cosmos unavailable")
            return []

    storage = SimpleNamespace(tenants=FakeTenants())
    settings = Settings(STORAGE_PROVIDER="cosmos")
    monkeypatch.setattr("shared_lib.web.service.get_settings", lambda: settings)
    monkeypatch.setattr("shared_lib.web.service.configure_observability", lambda settings: None)

    app = service_app("unit-test-service", storage=storage)
    client = TestClient(app)

    live = client.get("/health/live", headers={"X-Correlation-ID": "corr-1"})
    ready = client.get("/health/ready")
    storage.tenants.fail = True
    failed = client.get("/health/ready")

    assert live.json() == {"status": "alive", "service": "unit-test-service"}
    assert live.headers["X-Correlation-ID"] == "corr-1"
    assert ready.status_code == 200
    assert failed.status_code == 503
    assert app.state.metrics.snapshot()["requests"] == 3
    assert app.state.metrics.snapshot()["errors"] == 1

    metrics = ApiMetrics()
    assert metrics.snapshot()["averageLatencyMs"] == 0


def test_observability_helpers_configure_logging_and_write_audit_events(caplog):
    caplog.set_level("INFO", logger="finops.telemetry")
    writes = []
    storage = SimpleNamespace(processing_metadata=SimpleNamespace(upsert=lambda tenant_id, document: writes.append((tenant_id, document))))

    configure_observability(Settings(SERVICE_NAME="shared-lib-test"))
    write_audit_event(
        storage,
        tenant_id="tenant-1",
        subscription_id="",
        user_id="user-1",
        action="tenant_onboarded",
        correlation_id="corr-1",
        outcome="success",
        details={"source": "unit-test"},
    )
    with measure("unit_operation", tenant_id="tenant-1"):
        pass

    assert writes[0][0] == "tenant-1"
    assert writes[0][1]["subscriptionId"] == "tenant-scope"
    assert writes[0][1]["details"] == {"source": "unit-test"}
    assert any("operation_duration operation=unit_operation" in record.message for record in caplog.records)
