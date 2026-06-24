from __future__ import annotations

import sys
import types
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from fastapi import HTTPException

from shared_lib.configuration import Settings
from shared_lib.events.contracts import EventType, PlatformEvent
from src.notification_service.application import NotificationApplicationService
from src.microservices.notification_service import notify, scheduled_report


def _service(settings: Settings | None = None) -> NotificationApplicationService:
    app = SimpleNamespace(
        state=SimpleNamespace(settings=settings or Settings(AUTH_MODE="legacy"))
    )
    return NotificationApplicationService(app)


def _event(event_type: EventType, **payload) -> PlatformEvent:
    return PlatformEvent(
        eventType=event_type,
        tenantId="tenant-1",
        subscriptionId="subscription-1",
        correlationId="correlation-1",
        producer="pytest",
        payload=payload,
    )


def test_process_event_ignores_unhandled_events():
    service = _service()

    result = service.process_event(_event(EventType.COLLECTION_STARTED))

    assert result == {"status": "ignored"}


def test_process_event_logs_supported_event_when_email_not_configured():
    service = _service()

    result = service.process_event(
        _event(EventType.PROCESSING_COMPLETED, recipient="finops@example.com")
    )

    assert result == {"status": "logged", "reason": "email_not_configured"}


def test_scheduled_report_creates_processing_completed_notification():
    service = _service()

    result = service.scheduled_report(
        {
            "tenantId": "tenant-1",
            "subscriptionId": "subscription-1",
            "recipient": "finops@example.com",
            "reportType": "monthly-finops",
        },
        "correlation-2",
    )

    assert result == {"status": "logged", "reason": "email_not_configured"}


def test_process_event_sends_email_when_configured():
    settings = Settings(
        AUTH_MODE="legacy",
        AZURE_COMMUNICATION_EMAIL_CONNECTION_STRING="endpoint=https://example/",
        NOTIFICATION_EMAIL_SENDER="noreply@example.com",
    )
    service = _service(settings)
    poller = Mock()
    poller.result.return_value = {"id": "message-1"}
    client = Mock()
    client.begin_send.return_value = poller

    email_client = SimpleNamespace(
        from_connection_string=Mock(return_value=client)
    )
    monkey_modules = {
        "azure": types.ModuleType("azure"),
        "azure.communication": types.ModuleType("azure.communication"),
        "azure.communication.email": types.ModuleType("azure.communication.email"),
    }
    monkey_modules["azure.communication.email"].EmailClient = email_client
    original_modules = {
        name: sys.modules.get(name) for name in monkey_modules
    }
    sys.modules.update(monkey_modules)
    try:
        result = service.process_event(
            _event(EventType.RECOMMENDATION_GENERATED, recipient="finops@example.com")
        )
    finally:
        for name, module in original_modules.items():
            if module is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = module

    assert result == {"status": "sent", "messageId": "message-1"}
    email_client.from_connection_string.assert_called_once_with("endpoint=https://example/")
    message = client.begin_send.call_args.args[0]
    assert message["senderAddress"] == "noreply@example.com"
    assert message["recipients"]["to"][0]["address"] == "finops@example.com"


def test_http_entrypoints_require_internal_authorization():
    request = SimpleNamespace(
        app=SimpleNamespace(
            state=SimpleNamespace(settings=Settings(AUTH_MODE="entra"))
        ),
        headers={},
        state=SimpleNamespace(correlation_id="corr-1"),
    )

    with pytest.raises(HTTPException):
        notify(request, _event(EventType.PROCESSING_COMPLETED).model_dump(by_alias=True))

    with pytest.raises(HTTPException):
        scheduled_report(
            request,
            {"tenantId": "tenant-1", "subscriptionId": "sub-1"},
        )
