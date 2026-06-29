# AI Service

The AI Service provides the FinOps assistant, live inventory answers, RAG-based recommendations, and AI-enriched optimization output.

## Purpose

- Answer FinOps questions from the frontend assistant.
- Use Azure OpenAI for generated responses and recommendation narratives.
- Use Azure AI Search or local search providers for retrieval augmented generation.
- Query live inventory context when the question requires Azure resource data.
- Generate recommendations from processed cost, resource, advisor, and utilization context.
- Consume platform events and enrich recommendations after collection and processing.
- Persist AI execution and recommendation outputs through shared storage.

## API Calls

The AI Service exposes internal APIs. The [API Gateway](../api-gateway/README.md) maps selected public `/api/*` routes to these internal routes.

| Public route | Internal route | Purpose |
| --- | --- | --- |
| `POST /api/chat` | `POST /internal/chat` | Answer a user question from the AI assistant. |
| `GET /api/inventory/{kind}` | `GET /internal/inventory/{kind}` | Return live inventory results for a requested inventory kind. |
| Internal only | `POST /internal/recommendations/generate` | Generate AI-assisted recommendations for the current scope. |
| Internal only | `POST /internal/events` | Process a Service Bus platform event payload. |

All internal routes require internal service authorization.

## AI And RAG Flow

```text
Frontend assistant question
  -> API Gateway
  -> AI Service
  -> Scope-aware context loading
  -> Azure AI Search retrieval
  -> Azure OpenAI generation
  -> Structured fallback when needed
  -> Answer returned to frontend
```

Recommendation flow:

```text
Collection / processing event
  -> Service Bus
  -> AI Service
  -> Load cost, resource, advisor, and utilization context
  -> Generate recommendation narratives
  -> Persist recommendations
```

## Communication

The AI Service communicates with:

- [API Gateway](../api-gateway/README.md) for chat and inventory requests.
- [Processing Service](../processing-service/README.md) indirectly through shared processed data.
- [Collection Service](../collection-service/README.md) through platform events and collected context.
- Azure OpenAI for language generation and embeddings.
- Azure AI Search for retrieval.
- Azure Resource Graph for live inventory style queries.
- Shared storage repositories from [Shared Library](../shared-lib/README.md).
- Service Bus as an event consumer.

## Runtime Scope

Requests are scope-aware and use:

- `X-Tenant-ID`
- `X-Subscription-ID`
- `X-Correlation-ID`

The service uses `DefaultAzureCredential` through the platform identity configuration for Azure SDK access.

## Health

The shared web service layer provides:

- `GET /health/live`
- `GET /health/ready`

## Related READMEs

- [Frontend](../frontend/README.md) - assistant and live inventory UI.
- [API Gateway](../api-gateway/README.md) - public route mapping to AI APIs.
- [Collection Service](../collection-service/README.md) - produces source data and events.
- [Processing Service](../processing-service/README.md) - produces processed facts used by recommendations.
- [Shared Library](../shared-lib/README.md) - shared configuration, identity, events, storage, and domain models.
