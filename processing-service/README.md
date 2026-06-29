# Processing Service

The Processing Service turns collected Azure payloads into dashboard-ready cost facts, resource inventory, trends, recommendations, anomaly signals, and savings summaries.

## Purpose

- Consume collection events from Service Bus.
- Normalize raw cost, inventory, advisor, VM metric, and AKS metric payloads.
- Reconcile cost data with resource inventory.
- Detect waste and idle resources.
- Estimate savings opportunities.
- Detect cost anomalies.
- Generate report artifacts and persisted facts.
- Serve processed cost, resource, and recommendation APIs to the API Gateway.

## API Calls

The Processing Service exposes internal APIs. The [API Gateway](../api-gateway/README.md) maps public `/api/*` routes to these internal routes.

| Public route | Internal route | Purpose |
| --- | --- | --- |
| `GET /api/costs/summary` | `GET /internal/costs/summary` | Return total cost, savings, counts, and dashboard summary data. |
| `GET /api/costs/trends` | `GET /internal/costs/trends` | Return daily or monthly cost trend data. |
| `GET /api/costs/services` | `GET /internal/costs/services` | Return costs grouped by service name. |
| `GET /api/costs/resource-groups` | `GET /internal/costs/resource-groups` | Return costs grouped by resource group. |
| `GET /api/resources` | `GET /internal/resources` | Return processed resource inventory. |
| `GET /api/resources/{resource_id}` | `GET /internal/resources/{resource_id}` | Return one processed resource record. |
| `GET /api/recommendations` | `GET /internal/recommendations` | Return persisted optimization recommendations. |
| Internal only | `POST /internal/events` | Process a Service Bus platform event payload. |

All internal routes require internal service authorization.

## Processing Pipeline

```text
Collection event
  -> Load raw payloads
  -> Normalize cost and resource data
  -> Reconcile resource costs
  -> Detect waste and anomalies
  -> Estimate savings
  -> Persist facts and recommendations
  -> Serve dashboard APIs
```

## Communication

The Processing Service communicates with:

- [Collection Service](../collection-service/README.md) through Service Bus events and raw payload outputs.
- [API Gateway](../api-gateway/README.md) for dashboard API reads.
- Shared storage repositories from [Shared Library](../shared-lib/README.md) for Cosmos DB and Blob Storage access.
- Service Bus as an event consumer.

## Data Inputs

- Cost Management payloads.
- Resource Graph inventory payloads.
- Advisor recommendation payloads.
- VM metrics payloads.
- AKS metrics payloads.
- Tenant and subscription scope from internal headers.

## Data Outputs

- Cost summaries.
- Cost trends.
- Costs by service and resource group.
- Processed resources.
- Recommendations.
- Processing metadata and report outputs.

## Health

The shared web service layer provides:

- `GET /health/live`
- `GET /health/ready`

## Related READMEs

- [Frontend](../frontend/README.md) - consumes dashboard, costs, resources, and recommendations.
- [API Gateway](../api-gateway/README.md) - routes public API calls to this service.
- [Collection Service](../collection-service/README.md) - produces the raw data processed here.
- [AI Service](../ai-service/README.md) - enriches and generates recommendations using processed context.
- [Shared Library](../shared-lib/README.md) - repository, storage, events, models, and security primitives.
