"""Unit tests for agent tools."""

from unittest.mock import MagicMock, patch

from app.services.agent_tools import (
    analyze_anomaly_tool,
    analyze_anomaly_with_cluster_context,
    detect_anomaly_tool,
    get_agent_tools,
)


class TestAgentTools:
    """Unit tests for LangChain agent tools."""

    @patch("app.services.agent_tools.llm_reasoning_service")
    @patch("app.services.agent_tools.qdrant_service")
    @patch("app.services.embedding_service.embedding_service")
    def test_analyze_anomaly_tool(self, mock_embedding, mock_qdrant, mock_llm):
        """Test analyze_anomaly_tool."""
        # Mock embedding service
        mock_embedding.generate_embedding.return_value = {
            "embedding": [0.1] * 1536,
        }

        # Mock Qdrant search
        mock_qdrant.search_vectors.return_value = [
            {"level": "INFO", "message": "Normal log", "service": "test"},
        ]

        # Mock LLM reasoning service
        mock_llm.analyze_anomaly_with_root_cause.return_value = {
            "explanation": "Test explanation",
            "root_causes": [{"hypothesis": "Test cause", "confidence": 0.8, "description": "Test"}],
            "remediation_steps": [
                {"step": "Test step", "priority": "HIGH", "description": "Test action"}
            ],
            "severity": "HIGH",
            "severity_reason": "Test reason",
        }

        result = analyze_anomaly_tool.invoke(
            {
                "log_message": "Error: Test error",
                "log_level": "ERROR",
                "log_service": "test-service",
                "include_root_cause": True,
            }
        )

        assert result is not None
        assert "explanation" in result
        assert "root_causes" in result
        assert "remediation_steps" in result
        assert "severity" in result

    @patch("app.services.agent_tools.llm_reasoning_service")
    @patch("app.services.agent_tools.qdrant_service")
    @patch("app.services.embedding_service.embedding_service")
    def test_analyze_anomaly_tool_fallback(self, mock_embedding, mock_qdrant, mock_llm):
        """Test analyze_anomaly_tool fallback when root cause analysis fails."""
        # Mock embedding service
        mock_embedding.generate_embedding.return_value = {
            "embedding": [0.1] * 1536,
        }

        # Mock Qdrant search
        mock_qdrant.search_vectors.return_value = []

        # Mock LLM reasoning service - root cause fails, fallback to regular analysis
        mock_llm.analyze_anomaly_with_root_cause.return_value = None
        mock_llm.analyze_anomaly.return_value = "Fallback explanation"

        result = analyze_anomaly_tool.invoke(
            {
                "log_message": "Error: Test error",
                "include_root_cause": True,
            }
        )

        assert result is not None
        assert result["explanation"] == "Fallback explanation"

    @patch("app.services.agent_tools.llm_reasoning_service")
    @patch("app.services.agent_tools.qdrant_service")
    @patch("app.services.embedding_service.embedding_service")
    def test_detect_anomaly_tool(self, mock_embedding, mock_qdrant, mock_llm):
        """Test detect_anomaly_tool."""
        # Mock embedding service
        mock_embedding.generate_embedding.return_value = {
            "embedding": [0.1] * 1536,
        }

        # Mock Qdrant search
        mock_qdrant.search_vectors.return_value = []

        # Mock LLM reasoning service
        mock_llm.detect_anomaly.return_value = {
            "is_anomaly": True,
            "confidence": 0.85,
            "reasoning": "This is an anomaly",
        }

        result = detect_anomaly_tool.invoke(
            {
                "log_message": "Error: Test error",
                "log_level": "ERROR",
            }
        )

        assert result is not None
        assert result["is_anomaly"] is True
        assert result["confidence"] == 0.85
        assert "reasoning" in result

    @patch("app.services.agent_tools.clustering_service")
    @patch("app.services.agent_tools.llm_reasoning_service")
    @patch("app.services.agent_tools.qdrant_service")
    @patch("app.services.embedding_service.embedding_service")
    @patch("app.db.session.get_db")
    def test_analyze_anomaly_with_cluster_context(
        self, mock_get_db, mock_embedding, mock_qdrant, mock_llm, mock_clustering
    ):
        """Test analyze_anomaly_with_cluster_context tool."""
        # Mock database session
        mock_db = MagicMock()
        mock_get_db.return_value = iter([mock_db])

        # Mock embedding service
        mock_embedding.generate_embedding.return_value = {
            "embedding": [0.1] * 1536,
        }

        # Mock Qdrant search
        mock_qdrant.search_vectors.return_value = []

        # Mock cluster info
        mock_clustering.get_cluster_info.return_value = {
            "cluster_id": 1,
            "cluster_size": 100,
            "sample_logs": [
                {"level": "INFO", "message": "Normal log"},
            ],
        }

        # Mock LLM reasoning service
        mock_llm.analyze_anomaly_with_root_cause.return_value = {
            "explanation": "Test explanation with cluster context",
            "root_causes": [],
            "remediation_steps": [],
            "severity": "MEDIUM",
            "severity_reason": "Test",
        }

        result = analyze_anomaly_with_cluster_context.invoke(
            {
                "log_message": "Error: Test error",
                "cluster_id": 1,
                "log_level": "ERROR",
            }
        )

        assert result is not None
        assert "explanation" in result
        assert "cluster_context" in result
        assert result["cluster_context"]["cluster_id"] == 1

    def test_get_agent_tools(self):
        """Test get_agent_tools returns list of tools."""
        tools = get_agent_tools()
        assert isinstance(tools, list)
        assert len(tools) == 3
        assert analyze_anomaly_tool in tools
        assert detect_anomaly_tool in tools
        assert analyze_anomaly_with_cluster_context in tools
