import pytest
from httpx import Response as HttpxResponse
from fastapi import HTTPException
from unittest.mock import MagicMock

from src.gateway_service.application import GatewayApplicationService

@pytest.fixture
def gateway_service():
    app = MagicMock()
    app.state.settings.api_rate_limit_per_minute = 2
    from collections import defaultdict, deque
    app.state.rate_windows = defaultdict(deque)
    return GatewayApplicationService(app)

def test_rate_limit_success(gateway_service):
    request = MagicMock()
    request.app = gateway_service.app
    gateway_service.rate_limit(request, "user1")
    gateway_service.rate_limit(request, "user1")
    
def test_rate_limit_exceeded(gateway_service):
    request = MagicMock()
    request.app = gateway_service.app
    gateway_service.rate_limit(request, "user2")
    gateway_service.rate_limit(request, "user2")
    with pytest.raises(HTTPException) as exc:
        gateway_service.rate_limit(request, "user2")
    assert exc.value.status_code == 429

def test_is_public_auth_path(gateway_service):
    assert gateway_service.is_public_auth_path("auth/login") is True
    assert gateway_service.is_public_auth_path("/auth/callback") is True
    assert gateway_service.is_public_auth_path("costs") is False

def test_upstream_response(gateway_service):
    upstream = HttpxResponse(
        status_code=201,
        content=b"ok",
        headers={"content-type": "text/plain", "location": "/new", "set-cookie": "a=b"}
    )
    res = gateway_service.upstream_response(upstream)
    assert res.status_code == 201
    assert res.headers["Location"] == "/new"

def test_internal_authorization_header_disabled(gateway_service):
    request = MagicMock()
    request.app.state.settings.entra_auth_enabled = False
    assert gateway_service.internal_authorization_header(request) == ""

def test_internal_authorization_header_hs256(gateway_service):
    request = MagicMock()
    request.app.state.settings.entra_auth_enabled = True
    request.app.state.settings.use_managed_identity = False
    request.app.state.settings.api_session_secret = "secret"
    request.app.state.settings.internal_api_audience = "aud"
    res = gateway_service.internal_authorization_header(request)
    assert res.startswith("Bearer ")

def test_internal_authorization_header_managed_identity_success(gateway_service):
    request = MagicMock()
    request.app.state.settings.entra_auth_enabled = True
    request.app.state.settings.use_managed_identity = True
    request.app.state.settings.internal_api_audience = "aud"
    
    cred = MagicMock()
    cred.get_token.return_value = MagicMock(token="mi_token")
    request.app.state.service_credential = cred
    
    res = gateway_service.internal_authorization_header(request)
    assert res == "Bearer mi_token"

def test_internal_authorization_header_managed_identity_failure(gateway_service):
    request = MagicMock()
    request.app.state.settings.entra_auth_enabled = True
    request.app.state.settings.use_managed_identity = True
    request.app.state.settings.internal_api_audience = "aud"
    
    cred = MagicMock()
    cred.get_token.side_effect = Exception("failed")
    request.app.state.service_credential = cred
    
    with pytest.raises(HTTPException) as exc:
        gateway_service.internal_authorization_header(request)
    assert exc.value.status_code == 500

@pytest.mark.anyio
async def test_proxy_route_not_found(gateway_service):
    request = MagicMock()
    with pytest.raises(HTTPException) as exc:
        await gateway_service.proxy("unknown/path", request)
    assert exc.value.status_code == 404
