# API Gateway

The API Gateway is the public backend entry point for FinOpsIQ. It receives browser API requests, applies shared gateway policies, validates identity and scope, and forwards traffic to the correct internal service.

## Purpose

- Expose the public `/api/*` backend surface to the frontend.
- Route requests to Auth, Processing, and AI services.
- Enforce authenticated identity on protected routes.
- Resolve tenant and subscription scope from request headers and identity.
- Add correlation IDs and audit events.
- Apply per-subject rate limiting.
- Protect upstream calls with circuit breakers.
- Attach internal service authorization when calling internal services.

## Public API Surface

The gateway accepts these methods:

- `GET /api/{path}`
- `POST /api/{path}`
- `PUT /api/{path}`
- `DELETE /api/{path}`

It also handles `//api/{path}` for compatibility with duplicate-slash requests.

## Route Map

| Public route prefix | Upstream service | Upstream prefix | Subscription required |
| --- | --- | --- | --- |
| `/api/auth/*` | [Auth Service](../auth-service/README.md) | `/api` | No |
| `/api/tenants` | [Auth Service](../auth-service/README.md) | `/api` | No |
| `/api/subscriptions` | [Auth Service](../auth-service/README.md) | `/api` | No |
| `/api/tenant-health` | [Auth Service](../auth-service/README.md) | `/api` | No |
| `/api/onboarding/*` | [Auth Service](../auth-service/README.md) | `/api` | No |
| `/api/costs/*` | [Processing Service](../processing-service/README.md) | `/internal` | Yes |
| `/api/resources*` | [Processing Service](../processing-service/README.md) | `/internal` | Yes |
| `/api/recommendations` | [Processing Service](../processing-service/README.md) | `/internal` | Yes |
| `/api/chat` | [AI Service](../ai-service/README.md) | `/internal` | Yes |
| `/api/inventory/{kind}` | [AI Service](../ai-service/README.md) | `/internal` | Yes |

Public auth paths:

- `/api/auth/login`
- `/api/auth/callback`

These are allowed before an application session exists.

## Communication

Request flow:

```text
Frontend -> API Gateway -> Auth Service
Frontend -> API Gateway -> Processing Service
Frontend -> API Gateway -> AI Service
```

For internal service calls, the gateway forwards:

- `X-Correlation-ID`
- `X-Tenant-ID`
- `X-Subscription-ID`
- `Content-Type`
- `Authorization` for internal service authentication when Entra auth is enabled

For Auth Service calls, the gateway also forwards:

- Browser cookies
- Existing `Authorization` header when present

## Authentication And Authorization

- Public auth paths are anonymous.
- Protected paths require identity from the shared security layer.
- Subscription-scoped routes require tenant and subscription context.
- Internal service calls use either managed identity tokens or the configured internal token strategy.

## Health

The shared web service layer provides standard health endpoints:

- `GET /health/live`
- `GET /health/ready`

## Related READMEs

- [Frontend](../frontend/README.md) - browser API caller.
- [Auth Service](../auth-service/README.md) - login and onboarding routes.
- [Processing Service](../processing-service/README.md) - cost, resource, and recommendation routes.
- [AI Service](../ai-service/README.md) - chat and inventory routes.
- [Shared Library](../shared-lib/README.md) - gateway security, routing contracts, observability, and settings.
