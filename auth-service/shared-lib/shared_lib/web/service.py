"""Shared service initialization, probes, and internal authorization."""

from __future__ import annotations

import base64
import json

import jwt
from fastapi import FastAPI, HTTPException, Request

from shared_lib.web.middleware import ApiMetrics, ObservabilityMiddleware
from shared_lib.configuration import get_settings
from shared_lib.observability import configure_observability
from shared_lib.storage.factory import create_storage_provider


def _jwt_claims_for_key_discovery(token: str) -> dict:
    """Read JWT payload fields only to discover the Entra signing-key endpoint.

    The returned claims are deliberately not trusted for authentication or
    authorization. The caller must still validate the token signature,
    audience, and required claims before accepting the request.
    """

    parts = token.split(".")
    if len(parts) < 2:
        raise jwt.InvalidTokenError("Malformed JWT")

    payload = parts[1]
    padded_payload = payload + ("=" * (-len(payload) % 4))
    try:
        decoded = base64.urlsafe_b64decode(padded_payload.encode("ascii"))
        claims = json.loads(decoded.decode("utf-8"))
    except (ValueError, UnicodeDecodeError) as exc:
        raise jwt.InvalidTokenError("Invalid JWT payload") from exc

    if not isinstance(claims, dict):
        raise jwt.InvalidTokenError("JWT payload must be an object")
    return claims


def _entra_tenant_for_key_discovery(token: str) -> str:
    claims = _jwt_claims_for_key_discovery(token)
    tenant_id = str(claims.get("tid") or "organizations")
    if not tenant_id.replace("-", "").replace(".", "").isalnum():
        raise jwt.InvalidTokenError("Invalid Entra tenant identifier")
    return tenant_id


def service_app(name: str, *, storage=None) -> FastAPI:
    settings = get_settings().model_copy(update={"service_name": name})
    configure_observability(settings)
    app = FastAPI(title=f"FinsOpsIQ {name}", version="1.0.0")
    app.state.settings = settings
    app.state.storage = storage or create_storage_provider(settings)
    app.state.metrics = ApiMetrics()
    app.add_middleware(ObservabilityMiddleware)

    @app.on_event("startup")
    def log_storage_config() -> None:
        print(
            "service_storage_config "
            f"service={name} "
            f"storage_provider={settings.storage_provider} "
            f"cosmos_endpoint_present={bool(settings.cosmos_endpoint)} "
            f"cosmos_database_present={bool(settings.cosmos_database)} "
            f"azure_storage_account_url_present={bool(settings.azure_storage_account_url)} "
            f"azure_storage_container_present={bool(settings.azure_storage_container)} "
            f"storage_implementation={type(app.state.storage.tenants).__module__}",
            flush=True,
        )

    @app.get("/health/live")
    def live():
        return {"status": "alive", "service": name}

    @app.get("/health/ready")
    def ready():
        try:
            if settings.storage_provider == "cosmos":
                app.state.storage.tenants.list()
            return {"status": "ready", "service": name}
        except Exception as exc:
            raise HTTPException(503, f"Dependency unavailable: {exc}") from exc

    return app


def require_internal(request: Request) -> dict:
    settings = request.app.state.settings
    if not settings.entra_auth_enabled:
        return {"appid": "local-development"}
    authorization = request.headers.get("Authorization", "")
    if not authorization.lower().startswith("bearer "):
        raise HTTPException(401, "Service token required")
    token = authorization[7:].strip()
    try:
        for audience in (settings.internal_api_audience, "azure-cost-advisor-api"):
            try:
                return jwt.decode(
                    token,
                    settings.api_session_secret,
                    algorithms=["HS256"],
                    issuer="azure-cost-advisor",
                    audience=audience,
                )
            except jwt.PyJWTError:
                pass

        tenant_id = _entra_tenant_for_key_discovery(token)
        keys = jwt.PyJWKClient(
            f"https://login.microsoftonline.com/{tenant_id}/discovery/v2.0/keys"
        )
        signing_key = keys.get_signing_key_from_jwt(token)
        valid_audiences = [settings.internal_api_audience]
        if settings.internal_api_client_id:
            valid_audiences.append(settings.internal_api_client_id)
        return jwt.decode(
            token,
            signing_key.key,
            algorithms=["RS256"],
            audience=valid_audiences,
            options={"require": ["exp", "iat", "aud"]},
        )
    except jwt.PyJWTError as exc:
        import logging
        logging.getLogger(__name__).error(f"PyJWTError: {exc}")
        raise HTTPException(401, "Invalid service token") from exc
