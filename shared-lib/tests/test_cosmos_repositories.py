from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

import pytest

from shared_lib.domain.models import (
    AzureSubscription,
    CostFact,
    ServerSession,
    Tenant,
    TenantHealth,
    TenantUser,
)
from shared_lib.repositories.errors import RepositoryError, TenantScopeError
from shared_lib.storage.adapters.cosmos.repositories import (
    CosmosEntityRepository,
    CosmosProcessingMetadataRepository,
    CosmosSessionRepository,
    CosmosSubscriptionRepository,
    CosmosTenantHealthRepository,
    CosmosTenantRepository,
    CosmosTenantUserRepository,
    _query,
)


class NotFound(Exception):
    status_code = 404


class FakeContainer:
    def __init__(self, rows: list[dict] | None = None, *, fail_write: bool = False) -> None:
        self.rows = rows or []
        self.fail_write = fail_write
        self.upserts: list[dict] = []
        self.deleted: list[tuple[str, str]] = []
        self.queries: list[dict] = []

    def upsert_item(self, document: dict) -> None:
        if self.fail_write:
            raise RuntimeError("write unavailable")
        self.upserts.append(document)
        self.rows = [row for row in self.rows if row.get("id") != document.get("id")]
        self.rows.append(document)

    def read_item(self, item: str, partition_key: str) -> dict:
        for row in self.rows:
            if row.get("id") == item and row.get("tenantId") == partition_key:
                return row
        raise NotFound("not found")

    def query_items(self, **kwargs):
        self.queries.append(kwargs)
        query = kwargs["query"]
        if "SELECT c.id" in query:
            return [{"id": row["id"]} for row in self.rows if row.get("tenantId") == kwargs["partition_key"]]
        if kwargs.get("enable_cross_partition_query"):
            return list(self.rows)
        parameters = {item["name"]: item["value"] for item in kwargs.get("parameters", [])}
        result = [row for row in self.rows if row.get("tenantId") == parameters.get("@tenantId")]
        if "@subscriptionId" in parameters:
            result = [row for row in result if row.get("subscriptionId") == parameters["@subscriptionId"]]
        if "@processingRunId" in parameters:
            result = [row for row in result if row.get("processingRunId") == parameters["@processingRunId"]]
        return result

    def delete_item(self, item: str, partition_key: str) -> None:
        self.deleted.append((item, partition_key))
        self.rows = [row for row in self.rows if row.get("id") != item]


def cost_fact(run_id: str = "run-1", *, amount: float = 12.0, timestamp: str = "2026-06-24T10:00:00Z") -> CostFact:
    return CostFact(
        tenantId="tenant-1",
        subscriptionId="sub-1",
        collectionRunId="collection-1",
        processingRunId=run_id,
        correlationId="corr-1",
        date=date(2026, 6, 24),
        costAmount=amount,
        currency="usd",
        sourceSystem="costManagement",
        sourceTimestamp=timestamp,
    )


def test_cosmos_entity_repository_enforces_tenant_scope_and_wraps_write_errors():
    repo = CosmosEntityRepository(FakeContainer(), CostFact, "factId")

    result = repo.upsert_many("tenant-1", [cost_fact()])

    assert result.updated == 1
    assert repo.container.upserts[0]["tenantId"] == "tenant-1"
    assert repo.container.upserts[0]["id"] == repo.container.upserts[0]["factId"]

    with pytest.raises(TenantScopeError):
        repo.upsert_many("tenant-2", [cost_fact()])

    failing_repo = CosmosEntityRepository(FakeContainer(fail_write=True), CostFact, "factId")
    with pytest.raises(RepositoryError, match="Cosmos NoSQL write failed"):
        failing_repo.upsert_many("tenant-1", [cost_fact()])


def test_cosmos_entity_repository_lists_latest_processing_run_only():
    old = cost_fact("run-old", amount=1, timestamp="2026-06-23T10:00:00Z").model_dump(by_alias=True, mode="json")
    new = cost_fact("run-new", amount=2, timestamp="2026-06-24T10:00:00Z").model_dump(by_alias=True, mode="json")
    other_subscription = {**new, "subscriptionId": "sub-2", "processingRunId": "run-other"}
    rows = [{**row, "id": row["factId"]} for row in (old, new, other_subscription)]
    repo = CosmosEntityRepository(FakeContainer(rows), CostFact, "factId")

    latest = repo.list_latest("tenant-1", "sub-1")

    assert [item.processing_run_id for item in latest] == ["run-new"]
    assert latest[0].cost_amount == 2


def test_tenant_subscription_user_and_health_repositories_round_trip_models():
    tenant_container = FakeContainer()
    tenant_repo = CosmosTenantRepository(tenant_container)
    tenant = Tenant(tenantId="tenant-1", displayName="Tenant One", correlationId="corr-1")

    assert tenant_repo.upsert("tenant-1", tenant).updated == 1
    assert tenant_repo.get("tenant-1").display_name == "Tenant One"
    assert tenant_repo.get("missing") is None
    assert tenant_repo.list()[0].tenant_id == "tenant-1"

    sub_container = FakeContainer()
    sub_repo = CosmosSubscriptionRepository(sub_container)
    subscription = AzureSubscription(
        tenantId="tenant-1",
        subscriptionId="sub-1",
        displayName="Sub One",
        correlationId="corr-1",
    )
    assert sub_repo.upsert("tenant-1", subscription).updated == 1
    assert sub_repo.list("tenant-1")[0].subscription_id == "sub-1"

    user_repo = CosmosTenantUserRepository(FakeContainer())
    user = TenantUser(tenantId="tenant-1", userId="user-1", email="u@example.com", correlationId="corr-1")
    assert user_repo.upsert("tenant-1", user).updated == 1
    assert user_repo.list("tenant-1")[0].email == "u@example.com"

    health_repo = CosmosTenantHealthRepository(FakeContainer())
    health = TenantHealth(
        tenantId="tenant-1",
        subscriptionId="sub-1",
        validationStatus="passed",
        correlationId="corr-1",
    )
    assert health_repo.upsert("tenant-1", health).updated == 1
    assert health_repo.get("tenant-1", "sub-1").validation_status == "passed"
    assert health_repo.list("tenant-1")[0].subscription_id == "sub-1"


def test_processing_metadata_repository_scopes_reads_and_strips_cosmos_fields():
    container = FakeContainer()
    repo = CosmosProcessingMetadataRepository(container)

    result = repo.upsert(
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

    assert result.updated == 1
    metadata_id = container.upserts[0]["metadataId"]
    container.rows[0]["_etag"] = "opaque"
    metadata = repo.get("tenant-1", "sub-1", metadata_id)
    assert metadata["metadataType"] == "summary"
    assert "_etag" not in metadata
    assert repo.get("tenant-1", "other-sub", metadata_id) is None
    assert repo.list_latest("tenant-1", "sub-1")[0]["metadataType"] == "summary"

    with pytest.raises(TenantScopeError):
        repo.upsert("tenant-1", {"tenantId": "tenant-2"})


def test_session_repository_uses_cross_partition_lookup_and_safe_delete():
    expires_at = datetime.now(timezone.utc) + timedelta(hours=1)
    session = ServerSession(
        sessionId="sid-1",
        tenantId="tenant-1",
        userId="user-1",
        authSession={"accessToken": "redacted"},
        expiresAt=expires_at,
    )
    container = FakeContainer()
    repo = CosmosSessionRepository(container)

    assert repo.upsert(session).updated == 1
    assert repo.get("sid-1").user_id == "user-1"
    repo.delete("sid-1")
    assert container.deleted == [("sid-1", "tenant-1")]
    repo.delete("sid-missing")


def test_base_delete_tenant_and_query_require_tenant():
    container = FakeContainer(
        [
            {"id": "a", "tenantId": "tenant-1"},
            {"id": "b", "tenantId": "tenant-1"},
            {"id": "c", "tenantId": "tenant-2"},
        ]
    )
    repo = CosmosTenantRepository(container)

    assert repo.delete_tenant("tenant-1") == 2
    assert container.deleted == [("a", "tenant-1"), ("b", "tenant-1")]

    with pytest.raises(TenantScopeError):
        _query(container, "", "SELECT * FROM c WHERE c.tenantId = @tenantId")
