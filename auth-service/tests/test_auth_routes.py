from __future__ import annotations

import asyncio
from types import SimpleNamespace


def test_auth_microservice_routes_delegate_to_application(monkeypatch):
    import src.microservices.auth_service as routes

    calls = []

    class AppService:
        def login(self):
            calls.append(("login",))
            return "login"

        def callback(self, request):
            calls.append(("callback", request))
            return "callback"

        def logout_request(self, request):
            calls.append(("logout", request))
            return "logout"

        def me(self, request):
            calls.append(("me", request))
            return "me"

        def tenants(self, request):
            calls.append(("tenants", request))
            return ["tenant"]

        def subscriptions(self, request):
            calls.append(("subscriptions", request))
            return ["subscription"]

        def tenant_health(self, request):
            calls.append(("tenant_health", request))
            return ["health"]

        def offboard(self, tenant_id, request, body):
            calls.append(("offboard", tenant_id, body))
            return {"tenantId": tenant_id}

        def onboarding_status(self, request):
            calls.append(("onboarding_status", request))
            return {"status": "ready"}

        def discover_subscriptions(self, request):
            calls.append(("discover_subscriptions", request))
            return ["sub-a"]

        async def select_subscriptions(self, request, body):
            calls.append(("select_subscriptions", body))
            return {"success": True}

        async def retry_collection(self, request):
            calls.append(("retry_collection", request))
            return {"success": True}

    routes.app.state.application = AppService()
    request = SimpleNamespace()

    assert routes.login() == "login"
    assert routes.callback(request) == "callback"
    assert routes.logout(request) == "logout"
    assert routes.me(request) == "me"
    assert routes.tenants(request) == ["tenant"]
    assert routes.subscriptions(request) == ["subscription"]
    assert routes.tenant_health(request) == ["health"]
    assert routes.offboard("tenant-a", request, {"requestedBy": "user-a"}) == {"tenantId": "tenant-a"}
    assert routes.onboarding_status(request) == {"status": "ready"}
    assert routes.discover_subscriptions(request) == ["sub-a"]
    assert asyncio.run(routes.select_subscriptions(request, {"subscriptionIds": ["sub-a"]})) == {"success": True}
    assert asyncio.run(routes.retry_collection(request)) == {"success": True}
    asyncio.run(routes.startup_event())

    assert ("login",) in calls
    assert ("offboard", "tenant-a", {"requestedBy": "user-a"}) in calls
