# Shared Library

The shared library is the common Python package used by the FinOpsIQ backend services. It contains shared configuration, web service setup, security helpers, domain models, repository interfaces, storage adapters, event contracts, and observability utilities.

## Purpose

- Provide common service bootstrapping for FastAPI microservices.
- Centralize configuration loading and validation.
- Define domain models and operation scope objects.
- Provide security helpers for identity, tenant scope, subscription scope, and internal service authorization.
- Define event contracts and Service Bus helpers.
- Provide repository interfaces and storage provider factories.
- Provide Cosmos DB, Blob Storage, and filesystem storage adapters.
- Provide observability helpers such as audit event writing and correlation support.
- Provide utility functions for reliability and money formatting.

## Main Areas

| Area | Purpose |
| --- | --- |
| `configuration` | Runtime settings, environment variables, data paths, provider selection, and service URLs. |
| `web` | Common FastAPI service setup, health endpoints, middleware, and internal auth enforcement. |
| `security` | Request identity, tenant/subscription scope, customer credentials, and Azure credential helpers. |
| `domain` | Shared domain models, IDs, and request context objects. |
| `repositories` | Repository contracts, results, and shared error types. |
| `storage` | Storage provider factory and adapters for Cosmos DB, Blob Storage, and filesystem storage. |
| `events` | Platform event contracts, service contracts, and event bus helpers. |
| `observability` | Audit events and logging-related helpers. |
| `utilities` | Reliability helpers, circuit breakers, retries, and money utilities. |

## Communication Role

The shared library does not expose its own HTTP API. It supports communication between services by standardizing:

- Health endpoints.
- Correlation IDs.
- Internal service authorization.
- Event contracts.
- Repository interfaces.
- Tenant and subscription scope propagation.
- Azure credential creation.

## Used By

- [API Gateway](../api-gateway/README.md)
- [Auth Service](../auth-service/README.md)
- [Collection Service](../collection-service/README.md)
- [Processing Service](../processing-service/README.md)
- [AI Service](../ai-service/README.md)
- [Notification Service](../notification-service/README.md)

## Health Endpoints Provided To Services

Services using the shared web bootstrap expose:

- `GET /health/live`
- `GET /health/ready`

## Storage And Events

The library abstracts:

- Cosmos DB repositories for structured application data.
- Blob Storage for raw payloads.
- Filesystem storage for local or test execution.
- Service Bus event publishing and subscription workers.

## Security And Identity

The library helps services use:

- Microsoft Entra authenticated identity from incoming requests.
- Tenant and subscription scope headers.
- Internal service tokens.
- Azure SDK credentials through the configured managed identity or workload identity setup.

## Related READMEs

- [API Gateway](../api-gateway/README.md) - uses routing, security, reliability, and observability helpers.
- [Collection Service](../collection-service/README.md) - uses Azure credentials, storage, and events.
- [Processing Service](../processing-service/README.md) - uses repositories, domain models, and events.
- [AI Service](../ai-service/README.md) - uses storage, scope, identity, and event contracts.
