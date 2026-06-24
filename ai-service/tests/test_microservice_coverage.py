import pytest
from unittest.mock import MagicMock, patch
from fastapi.testclient import TestClient

@pytest.fixture(autouse=True)
def mock_dependencies():
    with patch("src.microservices.ai_service.create_event_publisher"), \
         patch("src.microservices.ai_service.start_subscription_worker"), \
         patch("src.microservices.ai_service.require_internal"):
        yield

@pytest.fixture
def client(mock_dependencies):
    from src.microservices.ai_service import app
    app.state.application = MagicMock()
    return TestClient(app)

def test_process_event_handler():
    from src.microservices.ai_service import process_event
    from shared_lib.events.contracts import PlatformEvent, EventType
    event = PlatformEvent(eventType=EventType.PROCESSING_COMPLETED, tenantId="t", subscriptionId="s", correlationId="c", producer="p")
    mock_app = MagicMock()
    mock_app.state.application.process_event.return_value = "ok"
    assert process_event(event, mock_app) == "ok"

def test_event_handler_route(client):
    from src.microservices.ai_service import app
    from shared_lib.events.contracts import EventType
    app.state.application.process_event.return_value = "processed"
    res = client.post("/internal/events", json={"eventType": EventType.PROCESSING_COMPLETED.value, "tenantId": "t", "subscriptionId": "s", "correlationId": "c", "producer": "p"})
    assert res.status_code == 200
    assert res.json() == "processed"

def test_chat_route(client):
    from src.microservices.ai_service import app
    app.state.application.chat.return_value = "chat_response"
    res = client.post("/internal/chat", json={"message": "hello"}, headers={"x-tenant-id": "t1", "x-subscription-id": "s1"})
    assert res.status_code == 200
    assert res.json() == "chat_response"

def test_generate_recommendations_route(client):
    from src.microservices.ai_service import app
    app.state.application.generate_recommendations.return_value = "recs"
    res = client.post("/internal/recommendations/generate", headers={"x-tenant-id": "t1", "x-subscription-id": "s1"})
    assert res.status_code == 200
    assert res.json() == "recs"

def test_inventory_route(client):
    from src.microservices.ai_service import app
    app.state.application.inventory.return_value = "inv"
    res = client.get("/internal/inventory/vms", headers={"x-tenant-id": "t1", "x-subscription-id": "s1"})
    assert res.status_code == 200
    assert res.json() == "inv"

def test_start_worker():
    from src.microservices.ai_service import start_worker, app
    with patch("src.microservices.ai_service.start_subscription_worker") as mock_start:
        mock_start.return_value = "worker"
        start_worker()
        assert app.state.worker == "worker"
