from unittest.mock import MagicMock, patch

from src.ai.service import AIService
from src.ai_service.application import AIApplicationService
from shared_lib.events.contracts import EventType, PlatformEvent
from shared_lib.events.service_contracts.internal import ServiceScope


def test_ai_service_initialization():
    settings = MagicMock()
    service = AIService(settings, storage=MagicMock(), search_provider=MagicMock())
    assert service.settings == settings
    assert service.storage is not None
    assert service.search_provider is not None


@patch("src.ai.service.KnowledgeService")
def test_ai_service_index_subscription(mock_knowledge_class):
    mock_knowledge = MagicMock()
    mock_knowledge_class.return_value = mock_knowledge
    mock_knowledge.index_subscription.return_value = 5
    
    service = AIService(MagicMock(), storage=MagicMock(), search_provider=MagicMock())
    res = service.index_subscription("tenant1", "sub1")
    assert res == 5
    mock_knowledge.index_subscription.assert_called_with("tenant1", "sub1")


def test_ai_service_executive_summary():
    service = AIService(MagicMock(), storage=MagicMock(), search_provider=MagicMock())
    service.rag = MagicMock()
    service.rag.generate_executive_summary.return_value = "summary"
    assert service.executive_summary("t1", "s1") == "summary"


def test_ai_service_cost_optimization_insights():
    service = AIService(MagicMock(), storage=MagicMock(), search_provider=MagicMock())
    service.rag = MagicMock()
    service.rag.invoke.return_value = "insights"
    assert service.cost_optimization_insights("t1", "s1") == "insights"
    service.rag.invoke.assert_called_once()


def test_ai_application_service_init():
    app = MagicMock()
    app.state.credential_factory = None
    del app.state.credential_factory # to trigger hasattr check
    
    with patch("src.ai_service.application.CustomerTenantCredentialFactory") as mock_factory:
        mock_factory.return_value = "factory"
        ai_app = AIApplicationService(app)
        assert ai_app.app.state.credential_factory == "factory"


@patch("src.ai_service.application.measure")
@patch("src.ai_service.application.AIService")
def test_ai_application_service_process_event(mock_ai_service_class, mock_measure):
    app = MagicMock()
    ai_app = AIApplicationService(app)
    
    mock_ai_service = MagicMock()
    mock_ai_service.index_subscription.return_value = 10
    mock_ai_service_class.return_value = mock_ai_service
    
    mock_measure.return_value.__enter__ = MagicMock()
    mock_measure.return_value.__exit__ = MagicMock()
    
    # Ignore non processing completed
    event1 = PlatformEvent(eventType=EventType.RECOMMENDATION_GENERATED, tenantId="t1", subscriptionId="s1", correlationId="c1", producer="p")
    assert ai_app.process_event(event1) == {"status": "ignored"}
    
    # Process
    event2 = PlatformEvent(eventType=EventType.PROCESSING_COMPLETED, tenantId="t1", subscriptionId="s1", correlationId="c2", producer="p")
    res = ai_app.process_event(event2)
    assert res == {"status": "indexed", "documents": 10}


@patch("src.ai_service.application.measure")
@patch("src.ai_service.application.FinOpsAdvisor")
def test_ai_application_service_chat(mock_advisor_class, mock_measure):
    app = MagicMock()
    ai_app = AIApplicationService(app)
    ai_app._credential = MagicMock(return_value="cred")
    
    mock_advisor = MagicMock()
    mock_advisor.ask.return_value = "answer"
    mock_advisor_class.return_value = mock_advisor
    
    mock_measure.return_value.__enter__ = MagicMock()
    mock_measure.return_value.__exit__ = MagicMock()
    
    scope = ServiceScope(tenant_id="t1", subscription_id="s1")
    body = {"message": "hello", "history": "hi"}
    
    res = ai_app.chat(scope, body, "corr")
    assert res["answer"] == "answer"
    assert res["tenantId"] == "t1"
    assert res["subscriptionId"] == "s1"
    app.state.events.publish.assert_called_once()


@patch("src.ai_service.application.FinOpsAdvisor")
def test_ai_application_service_generate_recommendations(mock_advisor_class):
    app = MagicMock()
    ai_app = AIApplicationService(app)
    
    mock_advisor = MagicMock()
    mock_advisor.generate_recommendations.return_value = {"source": "test"}
    mock_advisor_class.return_value = mock_advisor
    
    scope = ServiceScope(tenant_id="t1", subscription_id="s1")
    res = ai_app.generate_recommendations(scope, "corr")
    
    assert res == {"source": "test"}
    app.state.events.publish.assert_called_once()


@patch("src.ai_service.application.ResourceGraphInventoryService")
def test_ai_application_service_inventory(mock_inventory_class):
    app = MagicMock()
    ai_app = AIApplicationService(app)
    ai_app._credential = MagicMock(return_value="cred")
    
    mock_inventory = MagicMock()
    mock_inventory.query.return_value = "vms"
    mock_inventory_class.return_value = mock_inventory
    
    scope = ServiceScope(tenant_id="t1", subscription_id="s1")
    res = ai_app.inventory(scope, "vms")
    
    assert res == "vms"
    mock_inventory.query.assert_called_once_with("What VMs exist?")
