from __future__ import annotations

from types import SimpleNamespace

from shared_lib.configuration import Settings
from shared_lib.events.contracts import EventType, PlatformEvent
from src.notification_service.application import NotificationApplicationService


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
