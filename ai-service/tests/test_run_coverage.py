from unittest.mock import MagicMock, patch
import sys

from src.ai.run import main

@patch("src.ai.run.FinOpsAdvisor")
@patch("src.ai.run.get_settings")
def test_main_build_index(mock_get_settings, mock_advisor_class):
    mock_get_settings.return_value.embeddings_path = MagicMock()
    mock_advisor = MagicMock()
    mock_advisor.build_index.return_value = 10
    mock_advisor_class.return_value = mock_advisor
    
    with patch.object(sys, "argv", ["run.py", "--build-index", "--rebuild"]):
        main()
    
    mock_advisor.build_index.assert_called_once_with(rebuild=True)

@patch("src.ai.run.FinOpsAdvisor")
@patch("src.ai.run.get_settings")
def test_main_recommendations(mock_get_settings, mock_advisor_class):
    mock_advisor = MagicMock()
    mock_advisor.generate_recommendations.return_value = {"source": "test", "recommendations": "recs"}
    mock_advisor_class.return_value = mock_advisor
    
    with patch.object(sys, "argv", ["run.py", "--recommendations"]):
        main()
    
    mock_advisor.generate_recommendations.assert_called_once()

@patch("src.ai.run.FinOpsAdvisor")
@patch("src.ai.run.get_settings")
def test_main_ask(mock_get_settings, mock_advisor_class):
    mock_advisor = MagicMock()
    mock_advisor.ask.return_value = "answer"
    mock_advisor_class.return_value = mock_advisor
    
    with patch.object(sys, "argv", ["run.py", "--ask", "question"]):
        main()
    
    mock_advisor.ask.assert_called_once_with("question")

@patch("src.ai.run.FinOpsAdvisor")
@patch("src.ai.run.get_settings")
def test_main_examples(mock_get_settings, mock_advisor_class):
    mock_advisor = MagicMock()
    mock_advisor.ask.return_value = "answer"
    mock_advisor_class.return_value = mock_advisor
    
    with patch("src.ai.run.EXAMPLE_QUESTIONS", ["q1", "q2"]):
        with patch.object(sys, "argv", ["run.py", "--examples"]):
            main()
    
    assert mock_advisor.ask.call_count == 2

@patch("src.ai.run.FinOpsAdvisor")
@patch("src.ai.run.get_settings")
def test_main_no_args(mock_get_settings, mock_advisor_class, capsys):
    with patch.object(sys, "argv", ["run.py"]):
        main()
    
    captured = capsys.readouterr()
    assert "Quick start:" in captured.out
