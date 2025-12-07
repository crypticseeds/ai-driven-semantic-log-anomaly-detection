"""Unit tests for LLM reasoning service."""

import os
from unittest.mock import MagicMock, patch

from app.config import get_settings
from app.services.llm_reasoning_service import LLMReasoningService


class TestLLMReasoningService:
    """Unit tests for LLM reasoning service functionality."""

    def test_init_without_api_key(self):
        """Test initialization without OpenAI API key."""
        get_settings.cache_clear()
        with patch.dict(os.environ, {}, clear=True):
            service = LLMReasoningService()
            assert service.client is None
            assert service.model == "gpt-4o-mini"

    def test_init_with_api_key(self):
        """Test initialization with OpenAI API key."""
        get_settings.cache_clear()
        with (
            patch.dict(os.environ, {"OPENAI_API_KEY": "test-key"}),
            patch("app.services.llm_reasoning_service.OpenAI") as mock_openai,
        ):
            service = LLMReasoningService()
            assert service.client is not None
            mock_openai.assert_called_once_with(api_key="test-key")

    @patch("app.services.llm_reasoning_service.OpenAI")
    def test_analyze_anomaly_success(self, mock_openai_class):
        """Test successful anomaly analysis."""
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_choice = MagicMock()
        mock_message = MagicMock()
        mock_message.content = "This log is anomalous because..."
        mock_choice.message = mock_message
        mock_response.choices = [mock_choice]
        mock_client.chat.completions.create.return_value = mock_response
        mock_openai_class.return_value = mock_client

        get_settings.cache_clear()
        with patch.dict(os.environ, {"OPENAI_API_KEY": "test-key"}):
            service = LLMReasoningService()
            result = service.analyze_anomaly(
                log_message="Error: Database connection failed",
                log_level="ERROR",
                log_service="database",
            )

            assert result is not None
            assert "anomalous" in result.lower()
            mock_client.chat.completions.create.assert_called_once()

    def test_analyze_anomaly_without_client(self):
        """Test anomaly analysis without client."""
        get_settings.cache_clear()
        with patch.dict(os.environ, {}, clear=True):
            service = LLMReasoningService()
            result = service.analyze_anomaly("test message")
            assert result is None

    @patch("app.services.llm_reasoning_service.OpenAI")
    def test_analyze_anomaly_with_context(self, mock_openai_class):
        """Test anomaly analysis with context logs."""
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_choice = MagicMock()
        mock_message = MagicMock()
        mock_message.content = "Analysis with context"
        mock_choice.message = mock_message
        mock_response.choices = [mock_choice]
        mock_client.chat.completions.create.return_value = mock_response
        mock_openai_class.return_value = mock_client

        get_settings.cache_clear()
        with patch.dict(os.environ, {"OPENAI_API_KEY": "test-key"}):
            service = LLMReasoningService()
            context_logs = [
                {"level": "INFO", "message": "Normal log 1"},
                {"level": "INFO", "message": "Normal log 2"},
            ]
            result = service.analyze_anomaly(
                log_message="Anomalous log",
                context_logs=context_logs,
            )

            assert result is not None
            # Verify context was included in the call
            call_args = mock_client.chat.completions.create.call_args
            assert call_args is not None

    @patch("app.services.llm_reasoning_service.OpenAI")
    def test_analyze_anomalies_batch(self, mock_openai_class):
        """Test batch anomaly analysis."""
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_choice = MagicMock()
        mock_message = MagicMock()
        mock_message.content = "Batch analysis result"
        mock_choice.message = mock_message
        mock_response.choices = [mock_choice]
        mock_client.chat.completions.create.return_value = mock_response
        mock_openai_class.return_value = mock_client

        get_settings.cache_clear()
        with patch.dict(os.environ, {"OPENAI_API_KEY": "test-key"}):
            service = LLMReasoningService()
            anomalies = [
                {"log_id": "1", "log_message": "Anomaly 1", "log_level": "ERROR"},
                {"log_id": "2", "log_message": "Anomaly 2", "log_level": "WARN"},
            ]
            results = service.analyze_anomalies_batch(anomalies, max_analyses=2)

            assert len(results) == 2
            assert "1" in results
            assert "2" in results
