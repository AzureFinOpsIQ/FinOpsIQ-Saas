# Auth Service

The Auth Service owns user authentication, application session handling, tenant discovery, subscription discovery, onboarding state, and subscription validation.

## Purpose

- Start and complete Microsoft Entra ID OAuth login.
- Create, read, and clear application sessions.
- Return the current authenticated user.
- Discover tenants and Azure subscriptions available to the signed-in user.
- Persist selected subscriptions for onboarding.
- Trigger or retry collection for selected subscriptions.
- Track tenant health and onboarding status.
- Support tenant offboarding lifecycle actions.

## API Calls

These routes are exposed through the [API Gateway](../api-gateway/README.md) under the same public `/api/*` paths.

| Method | Path | Purpose |
| --- | --- | --- |
| `GET` | `/api/auth/login` | Begin Microsoft Entra login and redirect the browser to Entra ID. |
| `GET` | `/api/auth/callback` | Complete OAuth callback and create the application session. |
| `GET` | `/api/auth/logout` | End the application session and redirect through the logout flow. |
| `GET` | `/api/auth/me` | Return the current authenticated user. |
| `GET` | `/api/tenants` | Return known or available tenants for the user. |
| `GET` | `/api/subscriptions` | Return subscriptions available to the current user and tenant scope. |
| `GET` | `/api/tenant-health` | Return tenant health and collection status. |
| `POST` | `/api/tenants/{tenant_id}/offboarding` | Start tenant offboarding or deletion lifecycle work. |
| `GET` | `/api/onboarding/status` | Return onboarding state for the current user and tenant. |
| `GET` | `/api/onboarding/subscriptions/discover` | Discover subscriptions from Azure for onboarding. |
| `POST` | `/api/onboarding/subscriptions/select` | Persist selected subscriptions and trigger collection. |
| `POST` | `/api/onboarding/collection/retry` | Retry collection after a failed onboarding attempt. |

## Communication

Request flow:

```text
Frontend -> API Gateway -> Auth Service
Auth Service -> Microsoft Entra ID
Auth Service -> Azure subscription APIs
Auth Service -> Collection Service
Auth Service -> Cosmos DB / storage repositories
Auth Service -> Service Bus events
```

The Auth Service communicates with:

- Microsoft Entra ID for OAuth login and logout.
- Azure Resource Manager subscription APIs for discovery and validation.
- [Collection Service](../collection-service/README.md) to start collection after subscription selection or retry.
- Shared storage repositories from [Shared Library](../shared-lib/README.md) to persist sessions, tenants, subscriptions, tenant users, health, and audit data.
- Service Bus event publisher from the shared event layer.

## Important Headers And Cookies

- Browser cookies carry the application session.
- `X-Tenant-ID` may be supplied for tenant-scoped operations.
- `X-Correlation-ID` is forwarded by the gateway for traceability.

## Security

- Login uses Microsoft Entra ID.
- Session data is protected by the configured session secret.
- Azure API access uses the authenticated user's token or managed identity based on the service flow.
- Secrets are supplied through the platform secret mechanism, not hardcoded in the service.

## Health

The shared web service layer provides:

- `GET /health/live`
- `GET /health/ready`

## Related READMEs

- [Frontend](../frontend/README.md) - login, onboarding, admin, and session consumers.
- [API Gateway](../api-gateway/README.md) - public routing and authentication policy.
- [Collection Service](../collection-service/README.md) - collection execution triggered by onboarding.
- [Shared Library](../shared-lib/README.md) - sessions, domain models, repository interfaces, storage, security, events, and observability.
