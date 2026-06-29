# Collection Service

The Collection Service collects live Azure cost, inventory, advisor, VM metric, and AKS metric data for selected tenant and subscription scopes.

## Purpose

- Run Azure data collectors for a subscription.
- Collect Cost Management data.
- Collect Resource Graph inventory.
- Collect Azure Advisor recommendations.
- Collect Azure Monitor VM metrics.
- Collect AKS metrics.
- Store raw collection payloads.
- Publish events for downstream processing, AI enrichment, and notifications.
- Optionally run scheduled collection cycles.

## API Calls

The Collection Service exposes internal APIs only. It is not called directly by the frontend.

| Method | Path | Caller | Purpose |
| --- | --- | --- | --- |
| `POST` | `/internal/collections` | [Auth Service](../auth-service/README.md) or internal automation | Start collection for a tenant and subscription payload. |

The endpoint requires internal service authorization through the shared web security layer.

## Collectors

| Collector | Azure source | Output purpose |
| --- | --- | --- |
| Cost collector | Azure Cost Management | Cost facts and cost trend source data. |
| Resource Graph collector | Azure Resource Graph | Subscription inventory, disks, public IPs, and AKS/resource metadata. |
| Advisor collector | Azure Advisor | Azure-native optimization recommendations. |
| Metrics collector | Azure Monitor metrics | VM utilization and performance context. |
| AKS collector | Azure Monitor and AKS resource data | Cluster and node pool metric context. |

## Communication

Collection flow:

```text
Auth Service -> Collection Service -> Azure APIs
Collection Service -> Blob Storage / repository storage
Collection Service -> Service Bus
Service Bus -> Processing Service
Service Bus -> AI Service
Service Bus -> Notification Service
```

The service uses:

- Azure SDK clients for live collection.
- `DefaultAzureCredential` through the platform identity configuration.
- Shared repository and storage abstractions from [Shared Library](../shared-lib/README.md).
- Service Bus event publishing for downstream services.

## Inputs

Collection requests include tenant and subscription context. Runtime scope is also propagated with:

- `X-Tenant-ID`
- `X-Subscription-ID`
- `X-Correlation-ID`

## Outputs

- Raw payloads for cost, resource graph, advisor, metrics, and AKS data.
- Collection run status and errors.
- Service Bus events that tell downstream services new data is ready.

## Health

The shared web service layer provides:

- `GET /health/live`
- `GET /health/ready`

## Related READMEs

- [Auth Service](../auth-service/README.md) - triggers collection during onboarding and retry.
- [Processing Service](../processing-service/README.md) - consumes collection events and processes raw data.
- [AI Service](../ai-service/README.md) - enriches data and recommendations after collection.
- [Notification Service](../notification-service/README.md) - receives operational events.
- [Shared Library](../shared-lib/README.md) - storage, events, security, domain models, and observability.
