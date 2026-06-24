from __future__ import annotations

from collections import defaultdict, deque
from types import SimpleNamespace

import httpx
import pytest
from fastapi import HTTPException

from shared_lib.utilities.reliability import CircuitBreaker
from src.gateway_service.application import GatewayApplicationService


def _app(test_settings):
    test_settings.auth_mode = "legacy"
    test_settings.api_rate_limit_per_minute = 2
    test_settings.auth_service_url = "http://auth-service:8000"
    return SimpleNamespace(
        state=SimpleNamespace(
            settings=test_settings,
            rate_windows=defaultdict(deque),
            breakers=defaultdict(CircuitBreaker),
            service_credential=None,
            storage=SimpleNamespace(),
        )
    )


def test_rate_limit_allows_within_window_and_blocks_over_limit(test_settings):
    app = _app(test_settings)
    service = GatewayApplicationService(app)
    request = SimpleNamespace(app=app)

    service.rate_limit(request, "tenant:user")
    service.rate_limit(request, "tenant:user")

    with pytest.raises(HTTPException) as exc_info:
        service.rate_limit(request, "tenant:user")

    assert exc_info.value.status_code == 429


def test_public_auth_path_and_upstream_response_translation(test_settings):
    service = GatewayApplicationService(_app(test_settings))
    upstream = httpx.Response(
        303,
        content=b"",
        headers={
            "content-type": "text/plain",
            "location": "/dashboard",
            "set-cookie": "finops_session=abc; Path=/",
        },
    )

    response = service.upstream_response(upstream)

    assert service.is_public_auth_path("/auth/login") is True
    assert service.is_public_auth_path("/costs/summary") is False
    assert response.status_code == 303
    assert response.headers["Location"] == "/dashboard"
    assert "finops_session=abc" in response.headers["set-cookie"]


def test_proxy_rejects_unknown_routes(test_settings):
    service = GatewayApplicationService(_app(test_settings))
    request = SimpleNamespace(app=service.app)

    with pytest.raises(HTTPException) as exc_info:
        import asyncio

        asyncio.run(service.proxy("unknown/path", request))

    assert exc_info.value.status_code == 404


def test_proxy_forwards_public_auth_request_to_auth_service(test_settings, monkeypatch):
    app = _app(test_settings)
    service = GatewayApplicationService(app)
    captured: dict[str, object] = {}

    class _Client:
        def __init__(self, timeout):
            self.timeout = timeout

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return None

        async def request(self, method, url, **kwargs):
            captured["method"] = method
            captured["url"] = url
            captured["kwargs"] = kwargs
            return httpx.Response(
                302,
                headers={"location": "https://login.microsoftonline.com/"},
            )

    monkeypatch.setattr("src.gateway_service.application.httpx.AsyncClient", _Client)

    async def body():
        return b""

    request = SimpleNamespace(
        app=app,
        method="GET",
        body=body,
        query_params={"prompt": "select_account"},
        headers={"Authorization": "Bearer delegated", "Cookie": "a=b"},
        client=SimpleNamespace(host="127.0.0.1"),
        state=SimpleNamespace(correlation_id="corr-1"),
    )

    import asyncio

    response = asyncio.run(service.proxy("auth/login", request))

    assert response.status_code == 302
    assert captured["url"] == "http://auth-service:8000/api/auth/login"
    headers = captured["kwargs"]["headers"]
    assert headers["Authorization"] == "Bearer delegated"
    assert headers["Cookie"] == "a=b"
