# Notification Service

The Notification Service handles platform events and scheduled report notification workflows for FinOpsIQ.

## Purpose

- Consume platform events from Service Bus.
- Record or prepare notification messages for collection, processing, AI, and operational events.
- Handle scheduled report requests.
- Provide a dedicated service boundary for future email, webhook, Teams, or alert integrations.

## API Calls

The Notification Service exposes internal APIs only. It is not called directly by the frontend.

| Method | Path | Caller | Purpose |
| --- | --- | --- | --- |
| `POST` | `/internal/events` | Service Bus worker or internal service | Process a platform event payload. |
| `POST` | `/internal/reports/scheduled` | Internal automation | Process a scheduled report request. |

All internal routes require internal service authorization.

## Communication

Event flow:

```text
Collection / Processing / AI event
  -> Service Bus
  -> Notification Service
  -> Notification handling or audit-style output
```

Scheduled report flow:

```text
Internal caller -> Notification Service -> Scheduled report handling
```

The service communicates with:

- Service Bus as an event consumer.
- Shared event contracts from [Shared Library](../shared-lib/README.md).
- Shared configuration, storage, and observability helpers.

## Inputs

- `PlatformEvent` payloads from Service Bus or internal HTTP calls.
- Scheduled report request payloads.
- `X-Correlation-ID` for request tracing.

## Health

The shared web service layer provides:

- `GET /health/live`
- `GET /health/ready`

## Related READMEs

- [Collection Service](../collection-service/README.md) - publishes collection events.
- [Processing Service](../processing-service/README.md) - publishes or consumes processing events.
- [AI Service](../ai-service/README.md) - publishes or consumes AI recommendation events.
- [Shared Library](../shared-lib/README.md) - event contracts, event bus helpers, configuration, and observability.
