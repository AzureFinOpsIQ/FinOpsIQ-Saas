# FinsOpsIQ Application

This repository contains only the FinsOpsIQ application source code.

Infrastructure code lives in:

```text
AzureFinOpsIQ/FinOpsIQ-Infra
```

Helm deployment assets live in:

```text
AzureFinOpsIQ/FinOpsIQ-Helm
```

## Repository layout

```text
frontend/                 Next.js web application
src/                      Python application source and shared libraries
services/
  api-gateway/            API gateway container definition
  auth-service/           Authentication service container definition
  collection-service/     Azure collection service container definition
  processing-service/     Processing and recommendation service container definition
  ai-service/             FinOps AI assistant service container definition
  notification-service/   Notification service container definition
requirements/services/    Python dependency sets per microservice
tests/                    Unit and integration tests
observability/            Query examples and observability assets
docker-compose.yml        Local Docker Compose runtime
```

## Container standards

Each backend microservice has its own Dockerfile under `services/<service>/Dockerfile`.

All backend service Dockerfiles are:

- multi-stage builds;
- based on Python slim runtime images;
- configured with `PYTHONUNBUFFERED` and `PYTHONDONTWRITEBYTECODE`;
- run as a non-root user with UID `1000`;
- expose health checks on `/health/live`.

The frontend Dockerfile is also multi-stage and runs as non-root using the Node image runtime user.

## Local development

Create a local environment file from the example:

```bash
cp .env.example .env
```

Start the full local stack:

```bash
docker compose up -d --build
```

Open:

```text
http://localhost:3000
```

## Tests

```bash
pip install -r requirements.txt
pytest
```

## Security

Do not commit:

- `.env`
- access tokens
- client secrets
- API keys
- connection strings
- generated logs
- local state or cache files

Use environment variables, Azure Key Vault, GitHub Secrets, or Kubernetes secrets for sensitive configuration.
