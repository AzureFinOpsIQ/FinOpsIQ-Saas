from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from shared_lib.domain.models import AzureSubscription, ServerSession, Tenant
from shared_lib.security import SESSION_COOKIE, SessionTokenService
from shared_lib.storage.factory import create_storage_provider
from src.auth_service.application import AuthApplicationService


class _Events:
    def publish(self, event):
        self.event = event


def _app(test_settings):
    test_settings.auth_mode = "entra"
    test_settings.entra_client_id = "client-a"
    test_settings.entra_client_secret = "secret-a"
    test_settings.api_session_secret = "a-secure-test-secret-with-enough-length"
    test_settings.storage_provider = "file"
    storage = create_storage_provider(test_settings)
    return SimpleNamespace(
        state=SimpleNamespace(settings=test_settings, storage=storage, events=_Events())
    )


def _request(app, token: str | None = None, sid: str | None = None):
    cookies = {}
    if token:
        cookies[SESSION_COOKIE] = token
    if sid:
        cookies["finops_sid"] = sid
    return SimpleNamespace(
        app=app,
        cookies=cookies,
        headers={},
        query_params={},
    )


def _session_token(settings, roles=("tenant_admin",)):
    return SessionTokenService(settings).issue(
        {
            "tid": "tenant-a",
            "oid": "user-a",
            "email": "user@example.com",
            "name": "Test User",
            "roles": list(roles),
        }
    )


def test_me_and_tenant_scoped_lists_return_current_session_identity(test_settings):
    app = _app(test_settings)
    service = AuthApplicationService(app)
    token = _session_token(test_settings)
    request = _request(app, token=token)

    app.state.storage.tenants.upsert(
        "tenant-a",
        Tenant(tenantId="tenant-a", displayName="Tenant A", correlationId="corr-1"),
    )
    app.state.storage.subscriptions.upsert(
        "tenant-a",
        AzureSubscription(
            tenantId="tenant-a",
            subscriptionId="sub-a",
            displayName="Sub A",
            selected=True,
            correlationId="corr-1",
        ),
    )

    assert service.me(request)["user_id"] == "user-a"
    assert service.tenants(request)[0]["tenantId"] == "tenant-a"
    assert service.subscriptions(request)[0]["subscriptionId"] == "sub-a"


def test_logout_request_deletes_server_side_session(test_settings):
    app = _app(test_settings)
    service = AuthApplicationService(app)
    server_session = ServerSession(
        sessionId="sid-a",
        tenantId="tenant-a",
        userId="user-a",
        authSession={},
        expiresAt=datetime.now(timezone.utc) + timedelta(hours=1),
    )
    app.state.storage.sessions.upsert(server_session)

    response = service.logout_request(_request(app, sid="sid-a"))

    assert response.status_code == 303
    assert app.state.storage.sessions.get("sid-a") is None


def test_entra_session_loader_rejects_missing_invalid_and_expired_sessions(test_settings):
    app = _app(test_settings)
    service = AuthApplicationService(app)

    with pytest.raises(HTTPException, match="Missing Entra session"):
        service._get_entra_session(_request(app))

    expired = ServerSession(
        sessionId="sid-expired",
        tenantId="tenant-a",
        userId="user-a",
        authSession={},
        expiresAt=datetime.now(timezone.utc) - timedelta(minutes=1),
    )
    app.state.storage.sessions.upsert(expired)

    with pytest.raises(HTTPException, match="Entra session expired"):
        service._get_entra_session(_request(app, sid="sid-expired"))
    assert app.state.storage.sessions.get("sid-expired") is None


def test_onboarding_state_reports_collection_failure_and_ready(test_settings):
    app = _app(test_settings)
    service = AuthApplicationService(app)
    app.state.storage.tenants.upsert(
        "tenant-a",
        Tenant(
            tenantId="tenant-a",
            displayName="Tenant A",
            onboardingStatus="completed",
            correlationId="corr-1",
        ),
    )
    app.state.storage.subscriptions.upsert(
        "tenant-a",
        AzureSubscription(
            tenantId="tenant-a",
            subscriptionId="sub-a",
            displayName="Sub A",
            selected=True,
            onboardingStatus="validated",
            correlationId="corr-1",
        ),
    )
    app.state.storage.processing_metadata.upsert(
        "tenant-a",
        {
            "tenantId": "tenant-a",
            "subscriptionId": "sub-a",
            "collectionRunId": "collection-failed",
            "processingRunId": "processing-a",
            "metadataType": "collectionRun",
            "status": "failed",
            "startedAt": "2026-06-24T10:00:00Z",
            "errors": ["collector could not start"],
        },
    )

    failed = service._onboarding_state("tenant-a")

    assert failed["status"] == "collection_failed"
    assert failed["errors"] == ["collector could not start"]

    app.state.storage.processing_metadata.upsert(
        "tenant-a",
        {
            "tenantId": "tenant-a",
            "subscriptionId": "sub-a",
            "collectionRunId": "collection-ok",
            "processingRunId": "processing-ok",
            "metadataType": "collectionRun",
            "status": "completed",
            "startedAt": "2026-06-24T11:00:00Z",
            "completedAt": "2026-06-24T11:05:00Z",
        },
    )
    app.state.storage.processing_metadata.upsert(
        "tenant-a",
        {
            "tenantId": "tenant-a",
            "subscriptionId": "sub-a",
            "collectionRunId": "collection-ok",
            "processingRunId": "processing-ok",
            "metadataType": "processingRun",
            "status": "completed",
            "startedAt": "2026-06-24T11:06:00Z",
            "completedAt": "2026-06-24T11:10:00Z",
        },
    )

    ready = service._onboarding_state("tenant-a")

    assert ready["status"] == "ready"


def test_retry_collection_requires_validated_selected_subscription(test_settings):
    app = _app(test_settings)
    service = AuthApplicationService(app)
    token = _session_token(test_settings)
    request = _request(app, token=token)
    app.state.storage.tenants.upsert(
        "tenant-a",
        Tenant(tenantId="tenant-a", displayName="Tenant A", correlationId="corr-1"),
    )

    with pytest.raises(HTTPException, match="No validated selected subscriptions"):
        import asyncio

        asyncio.run(service.retry_collection(request))
