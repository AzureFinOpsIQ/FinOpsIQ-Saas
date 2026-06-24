from __future__ import annotations

import gzip
import json
import sys
import types
from types import SimpleNamespace

import pytest

from shared_lib.configuration import Settings
from shared_lib.domain.models import AzureSubscription
from shared_lib.events.bus import (
    AzureServiceBusPublisher,
    InMemoryEventBus,
    create_event_publisher,
    process_message,
)
from shared_lib.events.contracts import EventType, PlatformEvent
from shared_lib.events.service_contracts.internal import (
    CORRELATION_HEADER,
    SUBSCRIPTION_HEADER,
    TENANT_HEADER,
    RouteTarget,
    ServiceScope,
)
from shared_lib.repositories.errors import StorageConfigurationError, TenantScopeError
from shared_lib.security.customer_credentials import CustomerTenantCredentialFactory
from shared_lib.storage.adapters.blob.raw_payloads import BlobRawPayloadRepository


class FakeSubscriptionRepository:
    def __init__(self, subscriptions: list[AzureSubscription]) -> None:
        self._subscriptions = subscriptions

    def list(self, tenant_id: str) -> list[AzureSubscription]:
        assert tenant_id == "tenant-1"
        return self._subscriptions


def subscription(**extra) -> AzureSubscription:
    return AzureSubscription(
        tenantId="tenant-1",
        subscriptionId="sub-1",
        displayName="Sub One",
        correlationId="corr-1",
        **extra,
    )


def event() -> PlatformEvent:
    return PlatformEvent(
        eventType=EventType.COLLECTION_COMPLETED,
        tenantId="tenant-1",
        subscriptionId="sub-1",
        correlationId="corr-1",
        producer="collection-service",
        payload={"records": 3},
    )


def test_customer_credential_factory_uses_cached_workload_identity_builder():
    built: list[dict] = []

    def builder(**kwargs):
        built.append(kwargs)
        return {"credential": kwargs}

    factory = CustomerTenantCredentialFactory(
        Settings(AUTH_MODE="entra", USE_MANAGED_IDENTITY=True, COLLECTION_ENTRA_CLIENT_ID="collector-app"),
        SimpleNamespace(subscriptions=FakeSubscriptionRepository([subscription(sourceTenantId="customer-tenant")])),
        assertion_provider=lambda: "assertion-token",
        credential_builder=builder,
    )

    first = factory.for_subscription("tenant-1", "sub-1")
    second = factory.for_subscription("tenant-1", "sub-1")

    assert first is second
    assert built == [
        {
            "tenant_id": "customer-tenant",
            "client_id": "collector-app",
            "func": factory.assertion_provider,
        }
    ]


def test_customer_credential_factory_validates_scope_and_configuration():
    storage = SimpleNamespace(subscriptions=FakeSubscriptionRepository([]))
    factory = CustomerTenantCredentialFactory(Settings(AUTH_MODE="entra"), storage)

    with pytest.raises(TenantScopeError, match="tenantId and subscriptionId"):
        factory.for_subscription("", "sub-1")

    with pytest.raises(TenantScopeError, match="not registered"):
        factory.for_subscription("tenant-1", "sub-1")

    storage = SimpleNamespace(subscriptions=FakeSubscriptionRepository([subscription()]))
    factory = CustomerTenantCredentialFactory(Settings(AUTH_MODE="entra", USE_MANAGED_IDENTITY=True), storage)
    with pytest.raises(StorageConfigurationError, match="COLLECTION_ENTRA_CLIENT_ID"):
        factory.for_subscription("tenant-1", "sub-1")


def test_customer_credential_factory_local_and_legacy_modes(monkeypatch):
    built_secret: list[dict] = []
    built_default: list[dict] = []

    class FakeClientSecretCredential:
        def __init__(self, **kwargs) -> None:
            built_secret.append(kwargs)

    class FakeDefaultAzureCredential:
        def __init__(self, **kwargs) -> None:
            built_default.append(kwargs)

    azure_identity = types.ModuleType("azure.identity")
    azure_identity.ClientSecretCredential = FakeClientSecretCredential
    azure_identity.DefaultAzureCredential = FakeDefaultAzureCredential
    monkeypatch.setitem(sys.modules, "azure.identity", azure_identity)

    storage = SimpleNamespace(subscriptions=FakeSubscriptionRepository([subscription()]))
    secret_factory = CustomerTenantCredentialFactory(
        Settings(
            AUTH_MODE="entra",
            AZURE_CLIENT_ID="client-id",
            AZURE_CLIENT_SECRET="client-secret",
            COLLECTION_ENTRA_CLIENT_ID="collector-app",
        ),
        storage,
    )
    assert secret_factory.for_subscription("tenant-1", "sub-1") is secret_factory.for_subscription("tenant-1", "sub-1")
    assert built_secret[0]["client_secret"] == "client-secret"

    default_factory = CustomerTenantCredentialFactory(Settings(AUTH_MODE="entra", COLLECTION_ENTRA_CLIENT_ID="collector-app"), storage)
    default_factory.for_subscription("tenant-1", "sub-1")
    assert built_default[-1] == {
        "exclude_workload_identity_credential": True,
        "exclude_managed_identity_credential": True,
    }

    legacy_factory = CustomerTenantCredentialFactory(
        Settings(
            AUTH_MODE="legacy",
            COLLECTION_MODE="live",
            USE_MANAGED_IDENTITY=True,
            AZURE_CLIENT_ID="managed-id",
        ),
        storage,
    )
    legacy_factory.for_subscription("tenant-1", "sub-1")
    assert built_default[-1] == {"managed_identity_client_id": "managed-id"}

    disabled_factory = CustomerTenantCredentialFactory(Settings(AUTH_MODE="legacy", COLLECTION_MODE="mock"), storage)
    assert disabled_factory.for_subscription("tenant-1", "sub-1") is None


def test_customer_credential_factory_reads_workload_identity_token(tmp_path):
    token_file = tmp_path / "token"
    token_file.write_text(" token-value \n", encoding="utf-8")
    factory = CustomerTenantCredentialFactory(Settings(AZURE_FEDERATED_TOKEN_FILE=str(token_file)), storage=None)

    assert factory._read_assertion() == "token-value"

    with pytest.raises(StorageConfigurationError, match="required"):
        CustomerTenantCredentialFactory(Settings(), storage=None)._read_assertion()

    empty_file = tmp_path / "empty"
    empty_file.write_text("", encoding="utf-8")
    with pytest.raises(StorageConfigurationError, match="empty"):
        CustomerTenantCredentialFactory(Settings(AZURE_FEDERATED_TOKEN_FILE=str(empty_file)), storage=None)._read_assertion()


def test_in_memory_bus_routes_events_to_matching_subscribers_only():
    bus = InMemoryEventBus()
    handled: list[PlatformEvent] = []
    bus.subscribe(EventType.COLLECTION_COMPLETED.value, handled.append)

    bus.publish(event())

    assert bus.events[0].payload == {"records": 3}
    assert handled == [bus.events[0]]


def test_service_bus_publisher_builds_message_and_uses_retry(monkeypatch):
    attempts = {"count": 0}
    sent_messages = []

    class FakeMessage:
        def __init__(self, body, **kwargs) -> None:
            self.body = body
            self.kwargs = kwargs

    class FakeSender:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def send_messages(self, message) -> None:
            attempts["count"] += 1
            if attempts["count"] == 1:
                raise RuntimeError("transient")
            sent_messages.append(message)

    class FakeClient:
        def get_topic_sender(self, topic):
            assert topic == "finops-events"
            return FakeSender()

    azure_servicebus = types.ModuleType("azure.servicebus")
    azure_servicebus.ServiceBusMessage = FakeMessage
    monkeypatch.setitem(sys.modules, "azure.servicebus", azure_servicebus)
    monkeypatch.setattr("shared_lib.events.bus.wait_exponential", lambda **kwargs: None)

    publisher = AzureServiceBusPublisher(Settings(SERVICE_BUS_NAMESPACE="bus.servicebus.windows.net"), client=FakeClient())
    publisher.publish(event())

    assert attempts["count"] == 2
    assert sent_messages[0].kwargs["subject"] == EventType.COLLECTION_COMPLETED.value
    assert sent_messages[0].kwargs["application_properties"]["tenantId"] == "tenant-1"


def test_event_publisher_factory_and_message_processing_paths():
    assert isinstance(create_event_publisher(Settings(EVENT_PROVIDER="memory")), InMemoryEventBus)

    with pytest.raises(ValueError):
        create_event_publisher(Settings(EVENT_PROVIDER="service_bus"))

    receiver = SimpleNamespace(
        completed=[],
        abandoned=[],
        dead=[],
        complete_message=lambda message: receiver.completed.append(message),
        abandon_message=lambda message: receiver.abandoned.append(message),
        dead_letter_message=lambda message, **kwargs: receiver.dead.append((message, kwargs)),
    )
    message = SimpleNamespace(delivery_count=1, __str__=lambda self: event().model_dump_json(by_alias=True))
    valid_message = event().model_dump_json(by_alias=True)
    process_message(receiver, valid_message, lambda parsed: receiver.completed.append(parsed.event_type))
    assert receiver.completed[-1] == valid_message

    process_message(receiver, "not-json", lambda parsed: None, max_attempts=5)
    assert receiver.abandoned[-1] == "not-json"

    poison = SimpleNamespace(delivery_count=5, __str__=lambda self: "not-json")
    process_message(receiver, poison, lambda parsed: None, max_attempts=5)
    assert receiver.dead[-1][1]["reason"] == "MaxDeliveryCountExceeded"


class FakeBlobClient:
    def __init__(self, data: bytes | None = None, error: Exception | None = None) -> None:
        self.data = data
        self.error = error

    def readall(self) -> bytes:
        if self.error:
            raise self.error
        return self.data or b""


class FakeBlobContainer:
    def __init__(self) -> None:
        self.uploads: dict[str, dict] = {}
        self.blobs = ["raw/tenants/tenant-1/a.json", "raw/tenants/tenant-1/b.json"]
        self.deleted: tuple[str, ...] = ()

    def upload_blob(self, name, data, **kwargs) -> None:
        self.uploads[name] = {"data": data, **kwargs}

    def download_blob(self, name):
        if name not in self.uploads:
            raise RuntimeError("BlobNotFound")
        return FakeBlobClient(self.uploads[name]["data"])

    def list_blobs(self, name_starts_with):
        return [SimpleNamespace(name=name) for name in self.blobs if name.startswith(name_starts_with)]

    def delete_blobs(self, *names) -> None:
        self.deleted = names


def test_blob_raw_payload_repository_saves_manifest_latest_and_deletes_tenant(monkeypatch):
    container = FakeBlobContainer()
    repo = object.__new__(BlobRawPayloadRepository)
    repo.container = container
    monkeypatch.setattr(BlobRawPayloadRepository, "_content_settings", staticmethod(lambda: "gzip-json"))

    name = repo.save(
        "tenant-1",
        "sub-1",
        "collection-1",
        "resourceGraph",
        {"context": {"tenantId": "tenant-1", "correlationId": "corr-1"}, "records": [{"name": "vm1"}]},
    )

    assert name.endswith("resourceGraph/payload.json.gz")
    payload_upload = container.uploads[name]
    assert json.loads(gzip.decompress(payload_upload["data"]).decode("utf-8"))["records"][0]["name"] == "vm1"
    assert payload_upload["metadata"]["sha256"]
    assert container.uploads[name]["content_settings"] == "gzip-json"
    assert repo.load_latest("tenant-1", "sub-1", "resourceGraph")["records"][0]["name"] == "vm1"
    assert repo.load_latest("tenant-1", "sub-1", "missing") is None
    assert repo.delete_tenant("tenant-1") == 2
    assert container.deleted == tuple(container.blobs)

    with pytest.raises(TenantScopeError):
        repo.save("tenant-2", "sub-1", "collection-1", "resourceGraph", {"context": {"tenantId": "tenant-1"}})

    with pytest.raises(TenantScopeError):
        repo.load_latest("", "sub-1", "resourceGraph")


def test_internal_service_contract_helpers_validate_headers():
    scope = ServiceScope.from_headers({TENANT_HEADER: "tenant-1", SUBSCRIPTION_HEADER: "sub-1", CORRELATION_HEADER: "corr-1"})

    assert scope.headers() == {TENANT_HEADER: "tenant-1", SUBSCRIPTION_HEADER: "sub-1"}
    assert RouteTarget("COLLECTION_SERVICE_URL", "/collection").requires_subscription is True

    with pytest.raises(ValueError):
        ServiceScope.from_headers({TENANT_HEADER: "tenant-1"})
