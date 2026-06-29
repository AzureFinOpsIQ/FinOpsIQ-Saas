# Frontend

The frontend is the FinOpsIQ web application. It provides the browser experience for Microsoft Entra login, tenant and subscription selection, dashboards, cost analytics, resource inventory, AI assistant questions, recommendations, onboarding, and admin views.

## Purpose

- Render the user interface for FinOpsIQ.
- Start login and logout through the backend authentication flow.
- Send authenticated API requests to the API Gateway.
- Attach selected tenant and subscription scope headers to scoped API calls.
- Display live cost, resource, recommendation, and onboarding data returned by backend services.

## Main Pages

- `/login` - entry point for sign-in.
- `/dashboard` - cost, savings, resource, recommendation, and onboarding summary.
- `/costs` - cost trends, service costs, resource group costs, resources, and recommendations.
- `/resources` - resource inventory and live inventory lookup.
- `/recommendations` - optimization recommendations.
- `/assistant` - AI assistant chat.
- `/onboarding` - subscription discovery, selection, and collection retry flow.
- `/admin` - subscription, tenant health, and onboarding status views.

## API Calls

The frontend calls the public API Gateway through `NEXT_PUBLIC_API_URL`.

| Frontend call | Routed service | Purpose |
| --- | --- | --- |
| `GET /api/auth/login` | [Auth Service](../auth-service/README.md) | Begin Microsoft Entra login. |
| `GET /api/auth/logout` | [Auth Service](../auth-service/README.md) | End the user session. |
| `GET /api/auth/me` | [Auth Service](../auth-service/README.md) | Load current authenticated user. |
| `GET /api/tenants` | [Auth Service](../auth-service/README.md) | Load available tenants. |
| `GET /api/subscriptions` | [Auth Service](../auth-service/README.md) | Load available subscriptions. |
| `GET /api/tenant-health` | [Auth Service](../auth-service/README.md) | Load tenant health status. |
| `GET /api/onboarding/status` | [Auth Service](../auth-service/README.md) | Check onboarding state. |
| `GET /api/onboarding/subscriptions/discover` | [Auth Service](../auth-service/README.md) | Discover Azure subscriptions. |
| `POST /api/onboarding/subscriptions/select` | [Auth Service](../auth-service/README.md) | Persist selected subscriptions and trigger collection. |
| `POST /api/onboarding/collection/retry` | [Auth Service](../auth-service/README.md) | Retry collection after onboarding failure. |
| `GET /api/costs/summary` | [Processing Service](../processing-service/README.md) | Dashboard cost summary. |
| `GET /api/costs/trends` | [Processing Service](../processing-service/README.md) | Daily or monthly cost trends. |
| `GET /api/costs/services` | [Processing Service](../processing-service/README.md) | Costs grouped by service. |
| `GET /api/costs/resource-groups` | [Processing Service](../processing-service/README.md) | Costs grouped by resource group. |
| `GET /api/resources` | [Processing Service](../processing-service/README.md) | Processed resource inventory. |
| `GET /api/recommendations` | [Processing Service](../processing-service/README.md) | Stored optimization recommendations. |
| `POST /api/chat` | [AI Service](../ai-service/README.md) | Ask the FinOps assistant a question. |
| `GET /api/inventory/{kind}` | [AI Service](../ai-service/README.md) | Query live inventory by kind. |

## Communication

The frontend does not call backend microservices directly. All runtime traffic goes through the [API Gateway](../api-gateway/README.md).

Request flow:

```text
Browser -> Frontend -> API Gateway -> Auth / Processing / AI services
```

For scoped requests, the frontend sends:

- `X-Tenant-ID`
- `X-Subscription-ID`
- Browser cookies for the authenticated session

## Runtime Configuration

- `NEXT_PUBLIC_API_URL` defines the API Gateway base URL.
- Authentication state is maintained through backend-issued cookies.
- The frontend uses `credentials: include` for API requests so cookies are sent to the gateway.

## Related READMEs

- [API Gateway](../api-gateway/README.md) - public API routing and policy enforcement.
- [Auth Service](../auth-service/README.md) - login, session, tenant, subscription, and onboarding APIs.
- [Processing Service](../processing-service/README.md) - dashboard, cost, resource, and recommendation APIs.
- [AI Service](../ai-service/README.md) - assistant chat and live inventory APIs.
