# FinOpsIQ SaaS Application

FinOpsIQ is an AI-powered Azure FinOps platform. This repository contains the application source code for the frontend, backend microservices, shared Python library, tests, and local development assets.

Infrastructure and deployment assets live in separate repositories:

```text
AzureFinOpsIQ/FinOpsIQ-Infra
AzureFinOpsIQ/FinOpsIQ-Helm
```

## What This Application Does

- Authenticates users with Microsoft Entra ID.
- Discovers tenants and Azure subscriptions.
- Collects live Azure cost, resource, Advisor, Monitor, and AKS data.
- Processes raw collection output into cost facts, resource inventory, savings opportunities, anomalies, and recommendations.
- Uses Azure OpenAI and Azure AI Search for AI-assisted FinOps recommendations.
- Displays dashboards, cost analytics, resource inventory, recommendations, onboarding, and assistant views.

## Repository Layout

| Path | Purpose |
| --- | --- |
| [frontend](frontend/README.md) | Next.js web application and user interface. |
| [api-gateway](api-gateway/README.md) | Public backend entry point and API router. |
| [auth-service](auth-service/README.md) | Microsoft Entra login, sessions, tenants, subscriptions, and onboarding. |
| [collection-service](collection-service/README.md) | Azure cost, inventory, Advisor, Monitor, and AKS collectors. |
| [processing-service](processing-service/README.md) | Data normalization, savings, anomalies, reports, and dashboard APIs. |
| [ai-service](ai-service/README.md) | AI assistant, RAG, live inventory, and AI recommendation generation. |
| [notification-service](notification-service/README.md) | Platform event and scheduled report notification handling. |
| [shared-lib](shared-lib/README.md) | Shared configuration, security, domain models, storage, events, and observability. |
| `requirements/` | Shared Python dependency sets. |
| `data/` | Local raw, processed, and embedding data folders. |
| `observability/` | KQL queries and observability assets. |
| `docs/` | Additional application and CI/CD documentation. |
| `docker-compose.yml` | Local multi-service runtime. |

## Service Communication

Runtime request flow:

```text
Browser
  -> Frontend
  -> API Gateway
  -> Auth Service / Processing Service / AI Service
```

Data and event flow:

```text
Auth Service
  -> Collection Service
  -> Azure APIs
  -> Raw payload storage
  -> Service Bus events
  -> Processing Service / AI Service / Notification Service
```

Shared behavior such as configuration, identity, tenant and subscription scope, health endpoints, event contracts, storage repositories, and observability is provided by [shared-lib](shared-lib/README.md).

## Main Public API Areas

| API area | Primary owner |
| --- | --- |
| `/api/auth/*` | [Auth Service](auth-service/README.md) |
| `/api/tenants` | [Auth Service](auth-service/README.md) |
| `/api/subscriptions` | [Auth Service](auth-service/README.md) |
| `/api/onboarding/*` | [Auth Service](auth-service/README.md) |
| `/api/costs/*` | [Processing Service](processing-service/README.md) |
| `/api/resources*` | [Processing Service](processing-service/README.md) |
| `/api/recommendations` | [Processing Service](processing-service/README.md) |
| `/api/chat` | [AI Service](ai-service/README.md) |
| `/api/inventory/{kind}` | [AI Service](ai-service/README.md) |

See [api-gateway](api-gateway/README.md) for the full public-to-internal route map.

## Container Standards

Each backend microservice has its own Dockerfile under `<service>/Dockerfile`.

Backend service images are built to:

- use Python slim runtime images;
- run as a non-root user;
- expose service health endpoints;
- keep service source and shared library dependencies inside the image.

The frontend Dockerfile builds the Next.js application and runs it as a non-root runtime user.

## Local Development

Create a local environment file:

```bash
cp .env.example .env
```

Start the local stack:

```bash
docker compose up -d --build
```

Open the application:

```text
http://localhost:3000
```

## Tests

Install dependencies and run the Python test suite:

```bash
pip install -r requirements.txt
pytest
```

Frontend tests are located under `frontend/tests` and run with the frontend test tooling.

## Security

Do not commit:

- `.env`
- access tokens
- client secrets
- API keys
- connection strings
- generated logs
- local state or cache files

Use environment variables, Azure Key Vault, GitHub Secrets, Kubernetes Secrets, and managed identity based authentication for sensitive configuration.

## Service READMEs

Start here for service-specific details:

- [Frontend](frontend/README.md)
- [API Gateway](api-gateway/README.md)
- [Auth Service](auth-service/README.md)
- [Collection Service](collection-service/README.md)
- [Processing Service](processing-service/README.md)
- [AI Service](ai-service/README.md)
- [Notification Service](notification-service/README.md)
- [Shared Library](shared-lib/README.md)
