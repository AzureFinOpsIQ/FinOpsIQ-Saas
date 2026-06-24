from __future__ import annotations

from datetime import date
from types import SimpleNamespace

import pandas as pd
import pytest
from fastapi import HTTPException

from shared_lib.domain.context import OperationContext
from shared_lib.domain.models import CostFact, Recommendation, ResourceFact
from shared_lib.events.contracts import EventType, PlatformEvent
from shared_lib.events.service_contracts.internal import SUBSCRIPTION_HEADER, TENANT_HEADER, ServiceScope
from shared_lib.storage.factory import create_storage_provider
from src.dashboard.data_loader import DashboardData, DashboardDataLoader
from src.processing_service.application import ProcessingApplicationService
from src.processor.run import ProcessingReport


class Events:
    def __init__(self) -> None:
        self.published = []

    def publish(self, event) -> None:
        self.published.append(event)


def app(test_settings):
    test_settings.storage_provider = "file"
    storage = create_storage_provider(test_settings)
    return SimpleNamespace(state=SimpleNamespace(settings=test_settings, storage=storage, events=Events()))


def context():
    return OperationContext.create("tenant-a", "sub-a")


def cost(**extra):
    payload = {
        **context().document_fields(),
        "date": date(2026, 6, 24),
        "resourceId": "/subscriptions/sub-a/resourceGroups/rg/providers/Microsoft.Compute/virtualMachines/vm-a",
        "resourceGroup": "rg",
        "serviceName": "Virtual Machines",
        "location": "eastus",
        "costAmount": 10,
        "currency": "INR",
        "sourceSystem": "cost",
        "sourceTimestamp": "2026-06-24T10:00:00Z",
    }
    payload.update(extra)
    return CostFact(**payload)


def resource(**extra):
    payload = {
        **context().document_fields(),
        "resourceId": "/subscriptions/sub-a/resourceGroups/rg/providers/Microsoft.Compute/virtualMachines/vm-a",
        "resourceName": "vm-a",
        "resourceType": "Virtual Machine",
        "resourceGroup": "rg",
        "estimatedMonthlyCost": 10,
        "estimatedCostCurrency": "INR",
        "sourceSystem": "graph",
        "sourceTimestamp": "2026-06-24T10:00:00Z",
    }
    payload.update(extra)
    return ResourceFact(**payload)


def recommendation():
    return Recommendation(
        **context().document_fields(),
        resourceId="/subscriptions/sub-a/resourceGroups/rg/providers/Microsoft.Compute/virtualMachines/vm-a",
        content="Rightsize VM",
        estimatedSavings=5,
        currency="INR",
        sourceSystem="rules",
        sourceTimestamp="2026-06-24T10:00:00Z",
    )


def test_process_event_publishes_processing_lifecycle(test_settings):
    application = app(test_settings)

    def run_processing_func(**kwargs):
        assert kwargs["context"].tenant_id == "tenant-a"
        return pd.DataFrame(), ProcessingReport(
            started_at="2026-06-24T10:00:00Z",
            tenant_id="tenant-a",
            subscription_id="sub-a",
            collection_run_id="collection-a",
            processing_run_id="processing-a",
            cost_fact_count=2,
            resource_fact_count=1,
            reconciliation_status="passed",
        )

    service = ProcessingApplicationService(application, run_processing_func=run_processing_func)
    ignored = service.process_event(
        PlatformEvent(eventType=EventType.AI_CHAT_EXECUTED, tenantId="tenant-a", correlationId="corr-1", producer="ai")
    )
    assert ignored["status"] == "ignored"

    result = service.process_event(
        PlatformEvent(
            eventType=EventType.COLLECTION_COMPLETED,
            **context().document_fields(),
            producer="collection-service",
        )
    )

    assert result["cost_fact_count"] == 2
    assert [event.event_type.value for event in application.state.events.published] == [
        "ProcessingStarted",
        "ProcessingCompleted",
    ]


def test_processing_read_models_group_and_find_repository_data(test_settings):
    application = app(test_settings)
    storage = application.state.storage
    scope = ServiceScope("tenant-a", "sub-a")
    storage.cost_facts.upsert_many(
        "tenant-a",
        [
            cost(costAmount=10),
            cost(
                costAmount=5,
                serviceName="Storage",
                resourceId="/subscriptions/sub-a/resourceGroups/rg/providers/Microsoft.Storage/storageAccounts/sa-a",
            ),
        ],
    )
    storage.resources.upsert_many("tenant-a", [resource()])
    storage.recommendations.upsert_many("tenant-a", [recommendation()])
    service = ProcessingApplicationService(application)

    assert service.cost_summary(scope)["recordCount"] == 1
    assert service.cost_trends(scope, "monthly")[0]["period"] == "2026-06"
    assert service.group_costs(service.cost_facts(scope), "service_name")[0]["costAmount"] > 0
    assert service.resources(scope)[0]["resourceName"] == "vm-a"
    assert service.resource(scope, "/subscriptions/sub-a/resourceGroups/rg/providers/Microsoft.Compute/virtualMachines/vm-a")["resourceName"] == "vm-a"
    assert service.recommendations(scope)[0]["content"] == "Rightsize VM"

    with pytest.raises(HTTPException):
        service.resource(scope, "/missing")


def test_processing_read_models_fallback_to_dashboard_files(test_settings, tmp_path):
    test_settings.default_tenant_id = "tenant-a"
    test_settings.default_subscription_id = "sub-a"
    processed = test_settings.processed_path
    processed.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(
        [
            {
                "date": "2026-06-24",
                "resource_id": "/subscriptions/sub-a/resourceGroups/rg/providers/Microsoft.Compute/virtualMachines/vm-a",
                "resource_name": "vm-a",
                "resource_type": "Virtual Machine",
                "resource_group": "rg",
                "service_name": "Virtual Machines",
                "cost_amount": 10,
                "currency": "INR",
                "monthly_cost": 10,
            }
        ]
    ).to_csv(processed / "cost_facts_latest.csv", index=False)
    pd.DataFrame(
        [
            {
                "resource_id": "/subscriptions/sub-a/resourceGroups/rg/providers/Microsoft.Compute/virtualMachines/vm-a",
                "resource_name": "vm-a",
                "resource_type": "Virtual Machine",
                "resource_group": "rg",
                "monthly_cost": 10,
                "estimated_savings": 2,
                "savings_currency": "INR",
            }
        ]
    ).to_csv(processed / "resources_latest.csv", index=False)

    service = ProcessingApplicationService(app(test_settings))
    scope = ServiceScope("tenant-a", "sub-a")

    assert service.cost_facts(scope)[0].cost_amount == 10
    assert service.resources(scope)[0]["resource_name"] == "vm-a"
    assert service.resource(scope, "/subscriptions/sub-a/resourceGroups/rg/providers/Microsoft.Compute/virtualMachines/vm-a")["resource_name"] == "vm-a"


def test_dashboard_loader_file_fallbacks_and_properties(test_settings):
    raw = test_settings.raw_path
    processed = test_settings.processed_path
    embeddings = test_settings.embeddings_path
    raw.mkdir(parents=True, exist_ok=True)
    processed.mkdir(parents=True, exist_ok=True)
    embeddings.mkdir(parents=True, exist_ok=True)
    (processed / "summary_latest.json").write_text(
        '{"total_cost": {"INR": 15}, "daily_trend": [{"date": "2026-06-24", "currency": "INR", "cost_amount": 15}], "top_services": [{"service_name": "Compute", "currency": "INR", "cost_amount": 15}]}',
        encoding="utf-8",
    )
    (processed / "waste_findings_latest.json").write_text('{"total_estimated_savings": {"INR": 3}, "findings": [{"resource_name": "vm-a"}]}', encoding="utf-8")
    (processed / "anomalies_latest.json").write_text('{"anomaly_count": 1}', encoding="utf-8")
    (embeddings / "manifest.json").write_text('{"chunk_count": 4}', encoding="utf-8")
    (processed / "bad.json").write_text("{bad", encoding="utf-8")

    data = DashboardDataLoader(test_settings).load()

    assert data.data_available is True
    assert data.total_costs == {"INR": 15.0}
    assert data.savings_totals == {"INR": 3.0}
    assert data.anomaly_count == 1
    assert data.faiss_ready is True
    assert DashboardDataLoader(test_settings)._load_json(processed / "bad.json") == {}

    empty = DashboardData(cost_facts=pd.DataFrame([{"cost_amount": 2, "currency": "USD"}]))
    assert empty.total_monthly_cost == 2
    assert DashboardData(cost_facts=pd.DataFrame([{"cost_amount": 1, "currency": "USD"}, {"cost_amount": 2, "currency": "INR"}])).total_monthly_cost == 0


def test_processing_routes_delegate_to_application(monkeypatch):
    import src.microservices.processing_service as routes

    class AppService:
        def process_event(self, event):
            return {"eventType": event.event_type.value}

        def cost_summary(self, scope):
            return {"summary": scope.tenant_id}

        def cost_trends(self, scope, granularity="daily"):
            return [{"granularity": granularity}]

        def cost_facts(self, scope):
            return [SimpleNamespace(service_name="Compute", resource_group="rg", currency="INR", cost_amount=1)]

        def group_costs(self, facts, attribute):
            return [{attribute: getattr(facts[0], attribute)}]

        def resources(self, scope):
            return ["resource"]

        def resource(self, scope, resource_id):
            return {"resourceId": resource_id}

        def recommendations(self, scope):
            return ["rec"]

    routes.app.state.application = AppService()
    monkeypatch.setattr("src.microservices.processing_service.require_internal", lambda request: {"appid": "test"})
    monkeypatch.setattr("src.microservices.processing_service.start_subscription_worker", lambda *args, **kwargs: "worker")
    req = SimpleNamespace(app=routes.app, headers={TENANT_HEADER: "tenant-a", SUBSCRIPTION_HEADER: "sub-a"})
    body = PlatformEvent(eventType=EventType.COLLECTION_COMPLETED, **context().document_fields(), producer="collection").model_dump(by_alias=True, mode="json")

    assert routes.event_handler(req, body)["eventType"] == "CollectionCompleted"
    assert routes.costs(req)["summary"] == "tenant-a"
    assert routes.cost_trends(req, "monthly") == [{"granularity": "monthly"}]
    assert routes.cost_services(req)[0]["service_name"] == "Compute"
    assert routes.cost_resource_groups(req)[0]["resource_group"] == "rg"
    assert routes.resources(req) == ["resource"]
    assert routes.resource("rid", req) == {"resourceId": "rid"}
    assert routes.recommendations(req) == ["rec"]
    routes.start_worker()
    assert routes.app.state.worker == "worker"
