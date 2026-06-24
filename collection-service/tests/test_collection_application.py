from __future__ import annotations

from types import SimpleNamespace

import pytest

from shared_lib.configuration import Settings
from shared_lib.domain.models import AzureSubscription, Tenant
from shared_lib.storage.factory import create_storage_provider
from src.collection_service.application import CollectionApplicationService, scheduler_loop
from src.collector.base import IngestionResult
from src.collector.run import OrchestrationReport


class Events:
    def __init__(self) -> None:
        self.published = []

    def publish(self, event) -> None:
        self.published.append(event)


class CredentialFactory:
    def __init__(self) -> None:
        self.calls = []

    def for_subscription(self, tenant_id, subscription_id):
        self.calls.append((tenant_id, subscription_id))
        return "credential"


def app(test_settings):
    test_settings.storage_provider = "file"
    test_settings.event_provider = "memory"
    test_settings.processing_service_url = "http://processing-service:8000"
    test_settings.api_session_secret = "a-secure-test-secret-with-enough-length"
    storage = create_storage_provider(test_settings)
    return SimpleNamespace(
        state=SimpleNamespace(
            settings=test_settings,
            storage=storage,
            events=Events(),
            credential_factory=CredentialFactory(),
        )
    )


def report(*, errors=None):
    return OrchestrationReport(
        started_at="2026-06-24T10:00:00Z",
        tenant_id="tenant-a",
        subscription_id="sub-a",
        collection_run_id="collection-a",
        completed_at="2026-06-24T10:05:00Z",
        results=[
            IngestionResult(
                collector="cost",
                source_file="cost.json",
                ingestion_id="ingestion-a",
                ingested_at="2026-06-24T10:01:00Z",
                record_count=3,
                output_path="out.json",
                latest_path="latest.json",
            )
        ],
        errors=errors or [],
    )


def test_collect_subscription_publishes_started_completed_and_forwards_success(test_settings, monkeypatch):
    application = app(test_settings)
    forwarded = []
    monkeypatch.setattr(
        "src.collection_service.application.httpx.post",
        lambda url, **kwargs: forwarded.append((url, kwargs)) or SimpleNamespace(status_code=200, text="ok"),
    )

    def run_all_func(**kwargs):
        assert kwargs["credential"] == "credential"
        assert kwargs["continue_on_error"] is False
        return report()

    result = CollectionApplicationService(application, run_all_func=run_all_func).collect_subscription(
        {"tenantId": "tenant-a", "subscriptionId": "sub-a", "continueOnError": False}
    )

    assert result["results"][0].record_count == 3
    assert [event.event_type.value for event in application.state.events.published] == [
        "CollectionStarted",
        "CollectionCompleted",
    ]
    assert application.state.events.published[-1].payload["recordsCollected"] == 3
    assert forwarded[0][0].endswith("/internal/events")


def test_collect_subscription_records_failure_and_partial_results_do_not_forward(test_settings, monkeypatch):
    application = app(test_settings)
    monkeypatch.setattr(
        "src.collection_service.application.httpx.post",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("partial results must not forward")),
    )
    partial = CollectionApplicationService(application, run_all_func=lambda **kwargs: report(errors=["advisor failed"]))
    result = partial.collect_subscription({"tenantId": "tenant-a", "subscriptionId": "sub-a"})

    assert result["errors"] == ["advisor failed"]
    assert application.state.events.published[-1].payload["status"] == "partial"

    failing = CollectionApplicationService(application, run_all_func=lambda **kwargs: (_ for _ in ()).throw(RuntimeError("boom")))
    with pytest.raises(RuntimeError, match="boom"):
        failing.collect_subscription({"tenantId": "tenant-a", "subscriptionId": "sub-a"})

    metadata = application.state.storage.processing_metadata.list_latest("tenant-a", "sub-a")
    assert metadata[0]["status"] == "failed"
    assert application.state.events.published[-1].event_type.value == "HealthCheckFailed"


def test_forward_event_skips_service_bus_and_logs_http_failures(test_settings, monkeypatch):
    application = app(test_settings)
    service = CollectionApplicationService(application, run_all_func=lambda **kwargs: report())
    event = application.state.events.published[0] if application.state.events.published else None

    application.state.settings.event_provider = "service_bus"
    service._forward_event_for_local_compose(SimpleNamespace(model_dump=lambda **kwargs: {}))

    application.state.settings.event_provider = "memory"
    def raise_request_error(*args, **kwargs):
        raise __import__("httpx").RequestError("network")

    responses = [
        lambda *args, **kwargs: SimpleNamespace(status_code=500, text="failed"),
        raise_request_error,
    ]
    monkeypatch.setattr("src.collection_service.application.httpx.post", lambda *args, **kwargs: responses.pop(0)(*args, **kwargs))
    service._forward_event_for_local_compose(SimpleNamespace(model_dump=lambda **kwargs: {}))
    service._forward_event_for_local_compose(SimpleNamespace(model_dump=lambda **kwargs: {}))


def test_scheduled_cycle_filters_subscriptions_and_reports_failures(test_settings):
    application = app(test_settings)
    storage = application.state.storage
    storage.tenants.upsert("tenant-a", Tenant(tenantId="tenant-a", displayName="Tenant A", correlationId="corr-1"))
    for subscription_id, selected, status in [
        ("sub-a", True, "active"),
        ("sub-disabled", True, "disabled"),
        ("sub-unselected", False, "active"),
    ]:
        storage.subscriptions.upsert(
            "tenant-a",
            AzureSubscription(
                tenantId="tenant-a",
                subscriptionId=subscription_id,
                selected=selected,
                status=status,
                onboardingStatus="validated",
                correlationId="corr-1",
            ),
        )

    service = CollectionApplicationService(application, run_all_func=lambda **kwargs: (_ for _ in ()).throw(RuntimeError("collector down")))
    assert service.run_scheduled_cycle() == {"subscriptionsAttempted": 1, "failures": 1}
    assert application.state.events.published[-1].event_type.value == "HealthCheckFailed"


def test_collection_routes_and_scheduler_delegate(monkeypatch):
    import src.microservices.collection_service as routes

    class AppService:
        app = routes.app

        def __init__(self) -> None:
            self.ran = False

        def collect_subscription(self, body):
            return {"body": body}

        def run_scheduled_cycle(self):
            self.ran = True
            return {"subscriptionsAttempted": 0, "failures": 0}

    routes.app.state.application = AppService()
    request = SimpleNamespace(app=routes.app, headers={})
    monkeypatch.setattr("src.microservices.collection_service.require_internal", lambda request: {"appid": "test"})
    assert routes.collect(request, {"tenantId": "tenant-a", "subscriptionId": "sub-a"})["body"]["tenantId"] == "tenant-a"
    assert routes.run_scheduled_cycle() == {"subscriptionsAttempted": 0, "failures": 0}

    routes.app.state.settings.collection_scheduler_enabled = False
    routes.start_scheduler()
    routes.stop_scheduler()

    stop = SimpleNamespace(calls=0, is_set=lambda: stop.calls > 0, wait=lambda interval: setattr(stop, "calls", stop.calls + 1))
    scheduler_loop(routes.app.state.application, stop)
    assert routes.app.state.application.ran is True
