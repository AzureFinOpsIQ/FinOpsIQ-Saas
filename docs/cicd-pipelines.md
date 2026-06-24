# FinsOpsIQ Application CI/CD Pipelines

This repository owns the application workflow triggers only. Implementation lives in `AzureFinOpsIQ/FinOPsIQ-Workflows` as reusable `workflow_call` workflows.

The App repository workflows are thin callers and pass named inputs/secrets explicitly. They do not use `secrets: inherit`.

## Pipeline 1: CI Scan

Workflow:

```text
.github/workflows/ci-scan.yml
```

Reusable implementation:

```text
AzureFinOpsIQ/FinOPsIQ-Workflows/.github/workflows/app-ci-scan.yml@main
```

Trigger:

- `pull_request`
- actions: `opened`, `reopened`, `synchronize`
- target branch: `dev`

Flow:

1. Detect changed services with `dorny/paths-filter`.
2. Run service lint/tests for changed services, then run one repository-level SonarCloud scan.
3. Enforce SonarCloud Quality Gate.
4. Run Snyk only if SonarCloud passes.
5. No Docker image build in this pipeline.

## Pipeline 2: CI Build

Workflow:

```text
.github/workflows/ci-build.yml
```

Reusable implementation:

```text
AzureFinOpsIQ/FinOPsIQ-Workflows/.github/workflows/app-ci-build.yml@main
```

Trigger:

- `pull_request_target`
- type: `closed`
- target branch: `main`
- runs only when the PR was merged
- runs only when the PR has label `build`

Flow:

1. Detect changed services.
2. Build only changed services.
3. Scan each built image with Trivy.
4. Push to ACR only if Trivy passes.
5. Update only changed service image tags in `FinOpsIQ-Helm/charts/finopsiq/dev-values.yaml`.

Image tag format:

```text
<service>:<first6-merge-commit-sha>
```

Example:

```text
ai-service:a453bd
```

## Pipeline 3: Release Promotion

Workflow:

```text
.github/workflows/release.yml
```

Reusable implementation:

```text
AzureFinOpsIQ/FinOPsIQ-Workflows/.github/workflows/app-release-promote.yml@main
```

Trigger:

- `release`
- type: `published`

Flow:

1. Read GitHub Release tag, for example `v1.0.0`.
2. Resolve the commit associated with the release tag.
3. Find existing SHA-tagged images in ACR.
4. Pull the existing SHA image.
5. Retag it with the release version.
6. Push the release tag.
7. Update release metadata.

Release promotion does not rebuild images.

## Path Filter Configuration

| Filter | Paths | Services |
|---|---|---|
| `frontend` | `frontend/**` | frontend |
| `api_gateway` | `api-gateway/**` | api-gateway |
| `auth` | `auth-service/**` | auth-service |
| `collection` | `collection-service/**` | collection-service |
| `processing` | `processing-service/**` | processing-service |
| `ai` | `ai-service/**` | ai-service |
| `notification` | `notification-service/**` | notification-service |
| `shared` | `shared-lib/**, requirements/**` | all backend services |

## Service Build Matrix

| Service | Dockerfile | Context | Helm key |
|---|---|---|---|
| frontend | `frontend/Dockerfile` | `frontend` | `frontend` |
| api-gateway | `api-gateway/Dockerfile` | `.` | `apiGateway` |
| auth-service | `auth-service/Dockerfile` | `.` | `auth` |
| collection-service | `collection-service/Dockerfile` | `.` | `collection` |
| processing-service | `processing-service/Dockerfile` | `.` | `processing` |
| ai-service | `ai-service/Dockerfile` | `.` | `ai` |
| notification-service | `notification-service/Dockerfile` | `.` | `notification` |

## Helm Update Strategy

The CI Build pipeline updates:

```text
FinOpsIQ-Helm/charts/finopsiq/dev-values.yaml
```

Only services that were rebuilt are changed.

Example:

```yaml
services:
  ai:
    image:
      tag: a453bd
```

## Required GitHub Secrets

- `AZURE_CLIENT_ID`
- `AZURE_TENANT_ID`
- `AZURE_SUBSCRIPTION_ID`
- `SONAR_TOKEN`
- `SNYK_TOKEN`
- `SLACK_WEBHOOK_URL`
- `HELM_REPO_TOKEN`

## Required GitHub Variables

- `ACR_LOGIN_SERVER`
- `SONAR_ORGANIZATION`
- `SONAR_PROJECT_KEY` optional; defaults to `<owner>_<repo>` when omitted
- `HELM_REPOSITORY`
