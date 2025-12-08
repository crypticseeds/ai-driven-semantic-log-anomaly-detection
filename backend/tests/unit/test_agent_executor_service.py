"""Unit tests for agent executor service."""

from unittest.mock import MagicMock, patch

from app.services.agent_executor_service import AgentExecutorService


class TestAgentExecutorService:
    """Unit tests for agent executor service."""

    @patch("app.services.agent_executor_service.create_agent")
    @patch("app.services.agent_executor_service.get_agent_tools")
    @patch("app.services.agent_executor_service.ChatOpenAI")
    @patch("app.services.agent_executor_service.get_settings")
    def test_agent_executor_initialization(
        self, mock_get_settings, mock_llm, mock_get_tools, mock_create_agent
    ):
        """Test agent executor service initialization."""
        # Mock settings - must return a mock with openai_api_key attribute
        mock_settings_obj = MagicMock()
        mock_settings_obj.openai_api_key = "test-key"
        mock_get_settings.return_value = mock_settings_obj

        # Mock tools
        mock_get_tools.return_value = []

        # Mock LLM
        mock_llm_instance = MagicMock()
        mock_llm.return_value = mock_llm_instance

        # Mock agent creation (create_agent returns a compiled graph directly)
        mock_executor_instance = MagicMock()
        mock_create_agent.return_value = mock_executor_instance

        service = AgentExecutorService()

        assert service.llm is not None
        assert service.executor is not None
        assert service.is_available() is True

    @patch("app.config.get_settings")
    def test_agent_executor_no_api_key(self, mock_settings):
        """Test agent executor service when API key is not configured."""
        mock_settings.return_value.openai_api_key = None

        service = AgentExecutorService()

        assert service.llm is None
        assert service.executor is None
        assert service.is_available() is False

    @patch("app.services.agent_executor_service.AgentExecutorService.__init__", return_value=None)
    def test_analyze_root_cause(self, _mock_init):
        """Test analyze_root_cause method."""
        from langchain_core.messages import AIMessage

        service = AgentExecutorService()
        service.executor = MagicMock()
        # New LangChain 1.x API returns messages format
        service.executor.invoke.return_value = {
            "messages": [AIMessage(content="Root cause analysis result")],
            "intermediate_steps": [],
        }

        result = service.analyze_root_cause(query="What caused the errors?")

        assert result is not None
        assert "response" in result
        assert result["response"] == "Root cause analysis result"
        assert "query" in result
        service.executor.invoke.assert_called_once()

    @patch("app.services.agent_executor_service.AgentExecutorService.__init__", return_value=None)
    def test_analyze_root_cause_with_context(self, _mock_init):
        """Test analyze_root_cause method with context."""
        from langchain_core.messages import AIMessage

        service = AgentExecutorService()
        service.executor = MagicMock()
        # New LangChain 1.x API returns messages format
        service.executor.invoke.return_value = {
            "messages": [AIMessage(content="Analysis with context")],
            "intermediate_steps": [],
        }

        context = {"service": "auth-service", "time_range": "last_hour"}
        result = service.analyze_root_cause(query="Analyze errors", context=context)

        assert result is not None
        assert "response" in result
        assert result["response"] == "Analysis with context"
        service.executor.invoke.assert_called_once()

    @patch("app.services.agent_executor_service.AgentExecutorService.__init__", return_value=None)
    def test_analyze_root_cause_error_handling(self, _mock_init):
        """Test analyze_root_cause error handling."""
        service = AgentExecutorService()
        service.executor = MagicMock()
        service.executor.invoke.side_effect = Exception("Test error")

        result = service.analyze_root_cause(query="Test query")

        assert result is not None
        assert "error" in result
        assert "response" not in result or result.get("response") is None
