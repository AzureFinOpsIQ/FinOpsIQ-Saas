import pytest
from unittest.mock import MagicMock, patch

from shared_lib.configuration import Settings
from src.ai.advisor import FinOpsAdvisor
from src.ai.rag import RAGError

@pytest.fixture
def advisor_no_openai():
    settings = Settings(openai_api_key="", ai_search_endpoint="")
    settings.ai_debug_mode = True
    advisor = FinOpsAdvisor(settings=settings, tenant_id="tenant-1", subscription_ids=["sub-1"])
    return advisor

@pytest.fixture
def advisor_with_openai():
    settings = Settings(openai_api_key="secret", ai_search_endpoint="https://search")
    settings.ai_debug_mode = True
    advisor = FinOpsAdvisor(settings=settings, tenant_id="tenant-1", subscription_ids=["sub-1"])
    advisor.rag = MagicMock()
    return advisor

def test_build_index_no_openai(advisor_no_openai):
    assert advisor_no_openai.build_index() == 0

def test_ask_live_inventory_failure(advisor_no_openai, monkeypatch):
    monkeypatch.setattr("src.ai.advisor.classify_intent", lambda q: MagicMock(route="live_inventory"))
    advisor_no_openai._handle_live_inventory = MagicMock(side_effect=RuntimeError("inventory down"))
    
    result = advisor_no_openai.ask("list all vms")
    assert "Live Azure inventory query failed" in result
    assert "inventory down" in result

def test_generate_recommendations_no_openai(advisor_no_openai):
    advisor_no_openai._rule_based_recommendations = MagicMock(return_value={"rule": "based"})
    res = advisor_no_openai.generate_recommendations()
    assert res == {"rule": "based"}

def test_generate_recommendations_rag_error(advisor_with_openai):
    advisor_with_openai.rag.generate_recommendations.side_effect = RAGError("rag failed")
    advisor_with_openai._rule_based_recommendations = MagicMock(return_value={"rule": "based"})
    res = advisor_with_openai.generate_recommendations()
    assert res == {"rule": "based"}

def test_try_generate_recommendation_narrative_exception(advisor_with_openai):
    advisor_with_openai.rag._get_llm = MagicMock(side_effect=Exception("llm offline"))
    res = advisor_with_openai._try_generate_recommendation_narrative("question", MagicMock(), {"source": "test"})
    assert res is None

def test_try_generate_recommendation_narrative_success(advisor_with_openai):
    llm_mock = MagicMock()
    llm_mock.invoke.return_value = MagicMock(content="here is your narrative")
    advisor_with_openai.rag._get_llm = MagicMock(return_value=llm_mock)
    
    res = advisor_with_openai._try_generate_recommendation_narrative("question", MagicMock(intent="test", route="rec"), {"source": "test"})
    assert "here is your narrative" in res
    assert "Debug Details" in res

def test_format_recommendation_analysis_with_debug(advisor_no_openai):
    analysis = {
        "top_spend_categories": [{"service_name": "VMs", "cost": 100, "currency": "USD"}],
        "root_causes": [{"cause": "Orphaned", "count": 2}],
        "opportunities": [{
            "cost": 50,
            "currency": "USD",
            "utilization": "Low",
            "advisor_evidence": "none",
            "waste_level": "High",
            "priority": "P1",
            "resource_name": "vm1",
            "resource_type": "Virtual Machine",
            "action": "Delete",
            "savings": 25,
            "savings_currency": "USD",
            "root_cause": "Orphaned"
        }],
        "estimated_savings_totals": {"USD": 25.0},
        "source": "test",
        "record_counts": "1"
    }
    
    res = advisor_no_openai._format_recommendation_analysis(MagicMock(intent="test", route="rec"), analysis)
    assert "Executive Summary" in res
    assert "vm1" in res

def test_with_debug_empty(advisor_no_openai):
    res = advisor_no_openai._with_debug("answer", [None, ""])
    assert res == "answer"
    
def test_answer_utilization_query_no_resources(advisor_no_openai):
    advisor_no_openai._load_repository_context = MagicMock(return_value={"resources": []})
    res = advisor_no_openai._answer_utilization_query("q", MagicMock(intent="test", route="util"))
    assert "no resource inventory facts are available" in res

def test_answer_cost_analysis_no_facts(advisor_no_openai):
    advisor_no_openai._load_repository_context = MagicMock(return_value={"costFacts": [], "resources": [], "recommendations": []})
    res = advisor_no_openai._answer_cost_analysis("cost", MagicMock(intent="test", route="cost"))
    assert "Cost analysis could not run because no costFacts are available" in res

def test_structured_advisory_fallback_no_facts(advisor_no_openai):
    advisor_no_openai._structured_facts_for_question = MagicMock(return_value="   ")
    res = advisor_no_openai._structured_advisory_fallback("q", {})
    assert "I do not have enough collected subscription facts" in res
