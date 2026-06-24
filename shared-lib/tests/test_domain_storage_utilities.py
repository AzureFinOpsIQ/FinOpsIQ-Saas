from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

import pytest

from shared_lib.configuration import Settings
from shared_lib.domain.context import OperationContext
from shared_lib.domain.ids import deterministic_id
from shared_lib.domain.models import (
    AzureSubscription,
    CostFact,
    Recommendation,
    ResourceFact,
    ServerSession,
    Tenant,
    TenantHealth,
    TenantUser,
)
from shared_lib.repositories.errors import StorageConfigurationError, TenantScopeError
from shared_lib.storage.factory import create_storage_provider
from shared_lib.utilities.money import format_money, format_money_totals
from shared_lib.utilities.reliability import CircuitBreaker, CircuitOpenError


def test_operation_context_and_deterministic_ids_are_stable():
    context = OperationContext.create("tenant-1", "sub-1")

    assert context.tenant_id == "tenant-1"
    assert context.subscription_id == "sub-1"
    assert context.document_fields()["tenantId"] == "tenant-1"
    assert deterministic_id("Tenant-1", " Sub-1 ") == deterministic_id("tenant-1", "sub-1")


def test_domain_models_normalize_ids_and_generate_stable_document_ids():
    cost = CostFact(
        tenantId="tenant-1",
        subscriptionId="sub-1",
        collectionRunId="collection-1",
        processingRunId="processing-1",
        correlationId="corr-1",
        date=date(2026, 6, 24),
        resourceId="/SUBSCRIPTIONS/SUB-1/RESOURCEGROUPS/RG/PROVIDERS/MICROSOFT.COMPUTE/VM1/",
        resourceGroup="rg",
        serviceName="Virtual Machines",
        location="eastus",
        costAmount=42.5,
        currency="inr",
        sourceSystem="costManagement",
        sourceTimestamp="2026-06-24T10:00:00Z",
    )
    resource = ResourceFact(
        tenantId="tenant-1",
        subscriptionId="sub-1",
        collectionRunId="collection-1",
        processingRunId="processing-1",
        correlationId="corr-1",
        resourceId="/subscriptions/sub-1/resourceGroups/rg/providers/Microsoft.Compute/virtualMachines/vm1/",
        resourceName="vm1",
        resourceType="Microsoft.Compute/virtualMachines",
        sourceSystem="resourceGraph",
        sourceTimestamp="2026-06-24T10:00:00Z",
    )
    recommendation = Recommendation(
        tenantId="tenant-1",
        subscriptionId="sub-1",
        collectionRunId="collection-1",
        processingRunId="processing-1",
        correlationId="corr-1",
        resourceId="/subscriptions/sub-1/resourceGroups/rg/providers/Microsoft.Network/publicIPAddresses/pip1/",
        category="idle_public_ip",
        title="Unused Public IP",
        content="Delete unused public IP",
        currency="usd",
        sourceSystem="advisor",
        sourceTimestamp="2026-06-24T10:00:00Z",
    )

    assert cost.currency == "INR"
    assert cost.resource_id.endswith("/vm1")
    assert cost.fact_id
    assert resource.resource_fact_id
    assert recommendation.currency == "USD"
    assert recommendation.recommendation_id


def test_file_storage_provider_persists_tenant_scoped_documents(tmp_path):
    settings = Settings(
        STORAGE_PROVIDER="file",
        STORAGE_DATA_DIR=str(tmp_path / "store"),
        DATA_RAW_DIR=str(tmp_path / "raw"),
    )
    storage = create_storage_provider(settings)

    tenant = Tenant(tenantId="tenant-1", displayName="Tenant One", correlationId="corr-1")
    subscription = AzureSubscription(
        tenantId="tenant-1",
        subscriptionId="sub-1",
        displayName="Azure Sub",
        correlationId="corr-1",
        selected=True,
    )
    user = TenantUser(
        tenantId="tenant-1",
        userId="user-1",
        email="user@example.com",
        displayName="User One",
        roles=["tenant_admin"],
        correlationId="corr-1",
    )
    health = TenantHealth(
        tenantId="tenant-1",
        subscriptionId="sub-1",
        validationStatus="passed",
        validationResults={"reader": {"status": "passed"}},
        correlationId="corr-1",
    )

    assert storage.tenants.upsert("tenant-1", tenant).inserted == 1
    assert storage.subscriptions.upsert("tenant-1", subscription).inserted == 1
    assert storage.tenant_users.upsert("tenant-1", user).inserted == 1
    assert storage.tenant_health.upsert("tenant-1", health).inserted == 1

    assert storage.tenants.get("tenant-1") == tenant
    assert storage.subscriptions.list("tenant-1")[0].subscription_id == "sub-1"
    assert storage.tenant_users.list("tenant-1")[0].user_id == "user-1"
    assert storage.tenant_health.get("tenant-1", "sub-1").validation_status == "passed"


def test_file_storage_rejects_cross_tenant_writes_and_supports_sessions(tmp_path):
    storage = create_storage_provider(
        Settings(STORAGE_PROVIDER="file", STORAGE_DATA_DIR=str(tmp_path / "store"))
    )
    tenant = Tenant(tenantId="tenant-1", displayName="Tenant One", correlationId="corr-1")

    with pytest.raises(TenantScopeError):
      storage.tenants.upsert("tenant-2", tenant)

    session = ServerSession(
        sessionId="sid-1",
        tenantId="tenant-1",
        userId="user-1",
        authSession={"accessToken": "redacted"},
        expiresAt=datetime.now(timezone.utc) + timedelta(hours=1),
    )
    storage.sessions.upsert(session)
    assert storage.sessions.get("sid-1").user_id == "user-1"
    storage.sessions.delete("sid-1")
    assert storage.sessions.get("sid-1") is None


def test_file_storage_entities_raw_payloads_and_processing_metadata(tmp_path):
    storage = create_storage_provider(
        Settings(
            STORAGE_PROVIDER="file",
            STORAGE_DATA_DIR=str(tmp_path / "store"),
            DATA_RAW_DIR=str(tmp_path / "raw"),
        )
    )
    cost = CostFact(
        tenantId="tenant-1",
        subscriptionId="sub-1",
        collectionRunId="collection-1",
        processingRunId="processing-1",
        correlationId="corr-1",
        date=date(2026, 6, 24),
        costAmount=12,
        currency="INR",
        sourceSystem="costManagement",
        sourceTimestamp="2026-06-24T10:00:00Z",
    )
    resource = ResourceFact(
        tenantId="tenant-1",
        subscriptionId="sub-1",
        collectionRunId="collection-1",
        processingRunId="processing-1",
        correlationId="corr-1",
        resourceId="/subscriptions/sub-1/resourceGroups/rg/providers/Microsoft.Compute/virtualMachines/vm1",
        resourceName="vm1",
        resourceType="Microsoft.Compute/virtualMachines",
        sourceSystem="resourceGraph",
        sourceTimestamp="2026-06-24T10:00:00Z",
    )
    recommendation = Recommendation(
        tenantId="tenant-1",
        subscriptionId="sub-1",
        collectionRunId="collection-1",
        processingRunId="processing-1",
        correlationId="corr-1",
        content="Delete unused public IP",
        sourceSystem="advisor",
        sourceTimestamp="2026-06-24T10:00:00Z",
    )

    assert storage.cost_facts.upsert_many("tenant-1", [cost]).inserted == 1
    assert storage.resources.upsert_many("tenant-1", [resource]).inserted == 1
    assert storage.recommendations.upsert_many("tenant-1", [recommendation]).inserted == 1
    assert storage.cost_facts.list_latest("tenant-1", "sub-1")[0].cost_amount == 12
    assert storage.resources.list_for_run("tenant-1", "sub-1", "processing-1")[0].resource_name == "vm1"
    assert storage.recommendations.list_latest("tenant-1", "sub-1")[0].content.startswith("Delete")

    path = storage.raw_payloads.save(
        "tenant-1",
        "sub-1",
        "collection-1",
        "resourceGraph",
        {"context": {"tenantId": "tenant-1"}, "records": [{"name": "vm1"}]},
    )
    assert path.endswith("resourceGraph.json")
    assert storage.raw_payloads.load_latest("tenant-1", "sub-1", "resourceGraph")["records"][0]["name"] == "vm1"

    result = storage.processing_metadata.upsert(
        "tenant-1",
        {
            "tenantId": "tenant-1",
            "subscriptionId": "sub-1",
            "collectionRunId": "collection-1",
            "processingRunId": "processing-1",
            "metadataType": "summary",
            "startedAt": "2026-06-24T10:00:00Z",
        },
    )
    assert result.inserted == 1
    latest = storage.processing_metadata.list_latest("tenant-1", "sub-1")
    assert latest[0]["metadataType"] == "summary"


def test_storage_factory_validates_provider_configuration():
    with pytest.raises(StorageConfigurationError):
        create_storage_provider(Settings(STORAGE_PROVIDER="unknown"))

    with pytest.raises(StorageConfigurationError):
        create_storage_provider(Settings(STORAGE_PROVIDER="cosmos"))


def test_money_helpers_and_circuit_breaker_behaviour():
    assert format_money(float("nan"), "nan") == "UNKNOWN 0.00"
    assert format_money_totals({"USD": 2, "INR": 1}) == "INR 1.00 | USD 2.00"

    breaker = CircuitBreaker(failure_threshold=2, recovery_seconds=60)

    def fail():
        raise RuntimeError("boom")

    with pytest.raises(RuntimeError):
        breaker.call(fail)
    with pytest.raises(RuntimeError):
        breaker.call(fail)
    with pytest.raises(CircuitOpenError):
        breaker.call(lambda: "not reached")

    healthy = CircuitBreaker(failure_threshold=2)
    assert healthy.call(lambda value: value + 1, 41) == 42
