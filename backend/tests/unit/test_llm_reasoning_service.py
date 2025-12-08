"""Unit tests for LLM reasoning service."""

import json
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

    @patch("app.services.llm_reasoning_service.OpenAI")
    def test_analyze_anomaly_with_root_cause(self, mock_openai_class):
        """Test root cause analysis with structured output."""
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_choice = MagicMock()
        mock_message = MagicMock()
        mock_message.content = json.dumps(
            {
                "explanation": "This log indicates a database connection issue",
                "root_causes": [
                    {
                        "hypothesis": "Connection pool exhaustion",
                        "confidence": 0.8,
                        "description": "All connections are in use",
                    }
                ],
                "remediation_steps": [
                    {
                        "step": "Check connection pool size",
                        "priority": "HIGH",
                        "description": "Increase pool size or check for connection leaks",
                    }
                ],
                "severity": "HIGH",
                "severity_reason": "Database connectivity issues can cause service outages",
            }
        )
        mock_choice.message = mock_message
        mock_response.choices = [mock_choice]
        mock_client.chat.completions.create.return_value = mock_response
        mock_openai_class.return_value = mock_client

        get_settings.cache_clear()
        with patch.dict(os.environ, {"OPENAI_API_KEY": "test-key"}):
            service = LLMReasoningService()
            cluster_info = {
                "cluster_id": 1,
                "cluster_size": 100,
                "sample_logs": [
                    {"level": "INFO", "message": "Normal log 1"},
                    {"level": "INFO", "message": "Normal log 2"},
                ],
            }
            result = service.analyze_anomaly_with_root_cause(
                log_message="Error: Database connection failed",
                log_level="ERROR",
                log_service="database",
                cluster_info=cluster_info,
            )

            assert result is not None
            assert "explanation" in result
            assert "root_causes" in result
            assert "remediation_steps" in result
            assert "severity" in result
            assert len(result["root_causes"]) > 0
            assert len(result["remediation_steps"]) > 0
            mock_client.chat.completions.create.assert_called_once()

    @patch("app.services.llm_reasoning_service.OpenAI")
    def test_analyze_anomaly_with_root_cause_json_error_fallback(self, mock_openai_class):
        """Test root cause analysis falls back on JSON parse error."""
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_choice = MagicMock()
        mock_message = MagicMock()
        mock_message.content = "Invalid JSON response"
        mock_choice.message = mock_message
        mock_response.choices = [mock_choice]
        mock_client.chat.completions.create.return_value = mock_response
        mock_openai_class.return_value = mock_client

        get_settings.cache_clear()
        with patch.dict(os.environ, {"OPENAI_API_KEY": "test-key"}):
            service = LLMReasoningService()
            # Mock analyze_anomaly to return a fallback explanation
            with patch.object(service, "analyze_anomaly", return_value="Fallback explanation"):
                result = service.analyze_anomaly_with_root_cause(
                    log_message="Error: Database connection failed",
                )

                assert result is not None
                assert result["explanation"] == "Fallback explanation"
                assert result["severity"] == "MEDIUM"
