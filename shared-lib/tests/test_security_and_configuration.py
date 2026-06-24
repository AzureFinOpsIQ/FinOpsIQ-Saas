from __future__ import annotations

from types import SimpleNamespace

import jwt
import pytest
from fastapi import HTTPException

from shared_lib.configuration import Settings
from shared_lib.security import SessionTokenService, get_identity
from shared_lib.web.service import _entra_tenant_for_key_discovery, require_internal


def test_key_discovery_reads_tenant_without_accepting_identity_claims():
    token = jwt.encode(
        {"tid": "22dc2419-3ab3-4f27-905a-945315d19d95", "oid": "untrusted"},
        "not-used-for-authentication-test-key",
        algorithm="HS256",
    )

    tenant_id = _entra_tenant_for_key_discovery(token)

    assert tenant_id == "22dc2419-3ab3-4f27-905a-945315d19d95"


def test_key_discovery_rejects_malformed_tokens():
    with pytest.raises(jwt.InvalidTokenError):
        _entra_tenant_for_key_discovery("not-a-jwt")


def test_internal_hs_token_is_verified_before_acceptance():
    settings = Settings(
        AUTH_MODE="entra",
        API_SESSION_SECRET="a-secure-test-secret-with-enough-length",
        INTERNAL_API_AUDIENCE="api://finopsiq-services",
    )
    token = jwt.encode(
        {
            "iss": "azure-cost-advisor",
            "aud": "api://finopsiq-services",
            "appid": "api-gateway",
        },
        settings.api_session_secret,
        algorithm="HS256",
    )
    request = SimpleNamespace(
        app=SimpleNamespace(state=SimpleNamespace(settings=settings)),
        headers={"Authorization": f"Bearer {token}"},
    )

    claims = require_internal(request)

    assert claims["appid"] == "api-gateway"


def test_internal_token_rejects_missing_bearer_header():
    settings = Settings(AUTH_MODE="entra")
    request = SimpleNamespace(
        app=SimpleNamespace(state=SimpleNamespace(settings=settings)),
        headers={},
    )

    with pytest.raises(HTTPException) as exc_info:
        require_internal(request)

    assert exc_info.value.status_code == 401


def test_session_token_round_trip_preserves_user_identity():
    settings = Settings(API_SESSION_SECRET="a-secure-test-secret-with-enough-length")
    service = SessionTokenService(settings)

    token = service.issue(
        {
            "tid": "tenant-1",
            "oid": "user-1",
            "email": "user-1@example.com",
            "name": "User One",
            "roles": ["tenant_admin"],
        }
    )

    identity = service.decode(token)

    assert identity.tenant_id == "tenant-1"
    assert identity.user_id == "user-1"
    assert identity.email == "user-1@example.com"
    assert identity.display_name == "User One"
    assert identity.roles == ("tenant_admin",)


def test_get_identity_uses_legacy_identity_when_entra_disabled():
    settings = Settings(
        AUTH_MODE="legacy",
        DEFAULT_TENANT_ID="tenant-local",
        DEFAULT_SUBSCRIPTION_ID="subscription-local",
    )
    request = SimpleNamespace(
        app=SimpleNamespace(state=SimpleNamespace(settings=settings)),
        cookies={},
        headers={},
    )

    identity = get_identity(request)

    assert identity.tenant_id == "tenant-local"
    assert identity.user_id == "legacy-user"
    assert identity.roles == ("tenant_admin",)
