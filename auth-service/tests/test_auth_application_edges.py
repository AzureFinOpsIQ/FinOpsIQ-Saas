from __future__ import annotations

import asyncio
import json
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from shared_lib.domain.models import AzureSubscription, ServerSession, Tenant, TenantHealth, TenantUser
from shared_lib.security import SESSION_COOKIE, SessionTokenService
from shared_lib.storage.factory import create_storage_provider
from src.auth.entra import AuthSession, UserProfile
from src.auth_service.application import FLOW_COOKIE, AuthApplicationService
from src.compliance.lifecycle import TenantLifecycleService
from src.onboarding.azure_access import DiscoveredSubscription, ValidationCheck


class Events:
    def __init__(self) -> None:
        self.published = []

    def publish(self, event) -> None:
        self.published.append(event)


def make_app(test_settings):
    test_settings.auth_mode = "entra"
    test_settings.frontend_url = "https://frontend.example"
    test_settings.api_session_secret = "a-secure-test-secret-with-enough-length"
    test_settings.storage_provider = "file"
    return SimpleNamespace(
        state=SimpleNamespace(
            settings=test_settings,
            storage=create_storage_provider(test_settings),
            events=Events(),
        )
    )


def request(app, *, token: str | None = None, sid: str | None = None, flow: str | None = None, headers=None, query=None):
    cookies = {}
    if token:
        cookies[SESSION_COOKIE] = token
    if sid:
        cookies["finops_sid"] = sid
    if flow:
        cookies[FLOW_COOKIE] = flow
    return SimpleNamespace(
        app=app,
        cookies=cookies,
        headers=headers or {},
        query_params=query or {},
    )


def session() -> AuthSession:
    return AuthSession(
        profile=UserProfile(
            tenantId="tenant-a",
            userId="user-a",
            email="user@example.com",
            displayName="User A",
        ),
        accessToken="arm-token",
        expiresAt=datetime.now(timezone.utc) + timedelta(hours=1),
    )


def token(settings, *, roles=("tenant_admin",), tenant_id="tenant-a"):
    return SessionTokenService(settings).issue(
        {
            "tid": tenant_id,
            "oid": "user-a",
            "email": "user@example.com",
            "name": "User A",
            "roles": list(roles),
        }
    )


def test_login_sets_encrypted_flow_cookie_and_legacy_login_redirects(test_settings, monkeypatch):
    app = make_app(test_settings)
    service = AuthApplicationService(app)

    class FakeEntra:
        def __init__(self, settings) -> None:
            pass

        def begin_login(self):
            return {"auth_uri": "https://login.example/authorize", "state": "state-a"}

    monkeypatch.setattr("src.auth_service.application.EntraAuthService", FakeEntra)
    response = service.login()

    assert response.status_code == 307
    assert response.headers["location"] == "https://login.example/authorize"
    cookie = response.headers["set-cookie"]
    encrypted = cookie.split(f"{FLOW_COOKIE}=")[1].split(";")[0]
    assert json.loads(service.cipher().decrypt(encrypted.encode()).decode())["state"] == "state-a"

    app.state.settings.auth_mode = "legacy"
    assert service.login().headers["location"] == "https://frontend.example/dashboard"


def test_callback_registers_user_publishes_event_and_redirects_by_onboarding_state(test_settings, monkeypatch):
    app = make_app(test_settings)
    service = AuthApplicationService(app)
    flow = {"auth_uri": "https://login.example/authorize", "state": "state-a"}
    encrypted_flow = service.cipher().encrypt(json.dumps(flow).encode()).decode()

    class FakeEntra:
        def __init__(self, settings) -> None:
            pass

        def complete_login(self, flow, params):
            assert params == {"code": "code-a", "state": "state-a"}
            return session()

    class FakeOnboarding:
        def __init__(self, settings, storage=None) -> None:
            self.storage = storage

        def register_authenticated_user(self, auth_session):
            self.storage.tenants.upsert(
                "tenant-a",
                Tenant(tenantId="tenant-a", displayName="Tenant A", onboardingStatus="not_started", correlationId="corr-1"),
            )
            self.storage.tenant_users.upsert(
                "tenant-a",
                TenantUser(
                    tenantId="tenant-a",
                    userId=auth_session.profile.user_id,
                    email=auth_session.profile.email,
                    displayName=auth_session.profile.display_name,
                    roles=["tenant_admin"],
                    correlationId="corr-1",
                ),
            )

    monkeypatch.setattr("src.auth_service.application.EntraAuthService", FakeEntra)
    monkeypatch.setattr("src.auth_service.application.TenantOnboardingService", FakeOnboarding)

    response = service.callback(request(app, flow=encrypted_flow, query={"code": "code-a", "state": "state-a"}))

    set_cookies = [
        value.decode()
        for name, value in response.raw_headers
        if name.decode().lower() == "set-cookie"
    ]
    sid_cookie = next(item for item in set_cookies if item.startswith("finops_sid="))
    session_id = sid_cookie.split("finops_sid=")[1].split(";")[0]

    assert response.headers["location"] == "https://frontend.example/onboarding"
    assert app.state.events.published[0].tenant_id == "tenant-a"
    assert app.state.storage.sessions.get(session_id)

    with pytest.raises(HTTPException) as exc_info:
        service.callback(request(app, flow="not-valid"))
    assert exc_info.value.status_code == 400


def test_onboarding_state_covers_permission_pending_collecting_and_processing(test_settings):
    app = make_app(test_settings)
    service = AuthApplicationService(app)
    storage = app.state.storage

    assert service._onboarding_state("missing") == {"status": "unknown"}

    storage.tenants.upsert("tenant-a", Tenant(tenantId="tenant-a", displayName="Tenant A", onboardingStatus="started", correlationId="corr-1"))
    storage.subscriptions.upsert(
        "tenant-a",
        AzureSubscription(
            tenantId="tenant-a",
            subscriptionId="sub-a",
            selected=True,
            onboardingStatus="validation_pending",
            correlationId="corr-1",
        ),
    )
    assert service._onboarding_state("tenant-a")["status"] == "permission_validation_required"

    storage.tenant_health.upsert(
        "tenant-a",
        TenantHealth(tenantId="tenant-a", subscriptionId="sub-a", validationStatus="failed", correlationId="corr-1"),
    )
    assert service._onboarding_state("tenant-a")["status"] == "permission_validation_failed"

    storage.tenants.upsert("tenant-a", Tenant(tenantId="tenant-a", displayName="Tenant A", onboardingStatus="completed", correlationId="corr-1"))
    storage.subscriptions.upsert(
        "tenant-a",
        AzureSubscription(
            tenantId="tenant-a",
            subscriptionId="sub-a",
            selected=True,
            onboardingStatus="validated",
            correlationId="corr-1",
        ),
    )
    assert service._onboarding_state("tenant-a")["status"] == "pending_collection"
    storage.processing_metadata.upsert(
        "tenant-a",
        {
            "tenantId": "tenant-a",
            "subscriptionId": "sub-a",
            "metadataType": "collectionRun",
            "collectionRunId": "collection-a",
            "processingRunId": "processing-a",
            "correlationId": "corr-1",
            "status": "running",
            "startedAt": datetime.now(timezone.utc).isoformat(),
        },
    )
    assert service._onboarding_state("tenant-a")["status"] == "collecting"


def test_discover_select_and_retry_subscription_workflows(test_settings, monkeypatch):
    app = make_app(test_settings)
    service = AuthApplicationService(app)
    storage = app.state.storage
    storage.tenants.upsert("tenant-a", Tenant(tenantId="tenant-a", displayName="Tenant A", correlationId="corr-1"))
    storage.sessions.upsert(
        ServerSession(
            sessionId="sid-a",
            tenantId="tenant-a",
            userId="user-a",
            authSession=session().model_dump(by_alias=True, mode="json"),
            expiresAt=datetime.now(timezone.utc) + timedelta(hours=1),
        )
    )

    created_tasks = []
    monkeypatch.setattr("asyncio.create_task", lambda coro: created_tasks.append(coro) or SimpleNamespace())

    class FakeOnboarding:
        def __init__(self, settings, storage=None) -> None:
            self.storage = storage

        def discover_subscriptions(self, auth_session):
            return [
                DiscoveredSubscription(subscriptionId="sub-a", displayName="Sub A", state="Enabled", tenantId="tenant-a"),
                DiscoveredSubscription(subscriptionId="sub-disabled", displayName="Disabled", state="Disabled", tenantId="tenant-a"),
            ]

        def persist_selected_subscriptions(self, auth_session, discovered, subscription_ids):
            for subscription_id in subscription_ids:
                self.storage.subscriptions.upsert(
                    "tenant-a",
                    AzureSubscription(
                        tenantId="tenant-a",
                        subscriptionId=subscription_id,
                        selected=True,
                        onboardingStatus="validated",
                        correlationId="corr-1",
                    ),
                )

        def validate_subscriptions(self, auth_session, subscription_ids):
            return [
                TenantHealth(tenantId="tenant-a", subscriptionId=item, validationStatus="passed", correlationId="corr-1")
                for item in subscription_ids
            ]

        def complete_onboarding(self, auth_session, subscription_ids):
            self.storage.tenants.upsert(
                "tenant-a",
                Tenant(tenantId="tenant-a", displayName="Tenant A", onboardingStatus="completed", correlationId="corr-1"),
            )

    monkeypatch.setattr("src.auth_service.application.TenantOnboardingService", FakeOnboarding)
    req = request(app, token=token(test_settings), sid="sid-a")

    assert [item["subscriptionId"] for item in service.discover_subscriptions(req)] == ["sub-a"]
    selected = asyncio.run(service.select_subscriptions(req, {"subscriptionIds": ["sub-a"]}))
    assert selected["success"] is True
    assert created_tasks
    for task in created_tasks:
        task.close()

    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(service.select_subscriptions(req, {"subscriptionIds": []}))
    assert exc_info.value.status_code == 400

    retry = asyncio.run(service.retry_collection(req))
    assert retry["subscriptionIds"] == ["sub-a"]
    for task in created_tasks:
        task.close()


def test_collection_trigger_failure_records_metadata_once(test_settings):
    app = make_app(test_settings)
    service = AuthApplicationService(app)
    started = datetime.now(timezone.utc)

    service._record_collection_trigger_failure_if_missing(
        "tenant-a",
        "sub-a",
        "failed",
        started,
    )
    first = app.state.storage.processing_metadata.list_latest("tenant-a", "sub-a")
    assert first[0]["status"] == "failed"

    app.state.storage.processing_metadata.upsert(
        "tenant-a",
        {
            "tenantId": "tenant-a",
            "subscriptionId": "sub-a",
            "metadataType": "collectionRun",
            "collectionRunId": "newer",
            "processingRunId": "processing",
            "correlationId": "corr-1",
            "status": "running",
            "startedAt": (started + timedelta(seconds=1)).isoformat(),
        },
    )
    service._record_collection_trigger_failure_if_missing("tenant-a", "sub-a", "failed again", started)
    assert len(app.state.storage.processing_metadata.list_latest("tenant-a", "sub-a")) == 2


def test_cleanup_expired_sessions_and_tenant_lifecycle_deletion(test_settings, tmp_path):
    app = make_app(test_settings)
    service = AuthApplicationService(app)
    assert service._cleanup_expired_sessions() == 0

    class Container:
        def __init__(self) -> None:
            self.deleted = []

        def query_items(self, **kwargs):
            return [
                {"id": "expired", "tenantId": "tenant-a", "expiresAt": (datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat()},
                {"id": "valid", "tenantId": "tenant-a", "expiresAt": (datetime.now(timezone.utc) + timedelta(minutes=1)).isoformat()},
            ]

        def delete_item(self, item, partition_key):
            self.deleted.append((item, partition_key))

    container = Container()
    app.state.storage.sessions.container = container
    assert service._cleanup_expired_sessions() == 1
    assert container.deleted == [("expired", "tenant-a")]

    raw_payloads = SimpleNamespace(delete_tenant=lambda tenant_id: 2)
    search = SimpleNamespace(delete_tenant=lambda tenant_id: 3)
    storage = SimpleNamespace(
        raw_payloads=raw_payloads,
        processing_metadata=SimpleNamespace(upsert=lambda tenant_id, document: None),
    )
    result = TenantLifecycleService(test_settings, storage, search_provider=search).execute_deletion("tenant-a")
    assert result["deletedBlobs"] == 2
    assert result["deletedSearchDocuments"] == 3
