"""Unit tests for agent tools."""

from unittest.mock import MagicMock, patch

from app.services.agent_tools import (
    analyze_anomaly_tool,
    analyze_anomaly_with_cluster_context,
    detect_anomaly_tool,
    get_agent_tools,
    search_logs,
    summarize_range,
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

    @patch("app.services.agent_tools.get_db")
    @patch("app.services.agent_tools.embedding_service")
    @patch("app.services.agent_tools.qdrant_service")
    def test_search_logs_tool(self, _mock_qdrant, _mock_embedding, mock_get_db):
        """Test search_logs tool."""
        from datetime import datetime
        from uuid import uuid4

        from app.db.postgres import LogEntry

        # Mock database session
        mock_db = MagicMock()
        mock_get_db.return_value = iter([mock_db])

        # Create mock log entries
        log_id = uuid4()
        mock_entry = LogEntry(
            id=log_id,
            timestamp=datetime.now(),
            level="ERROR",
            service="test-service",
            message="Error: Test error",
            raw_log="raw",
        )

        # Mock query
        mock_query = MagicMock()
        mock_query.filter.return_value.order_by.return_value.limit.return_value.all.return_value = [
            mock_entry
        ]
        mock_db.query.return_value = mock_query

        result = search_logs.invoke(
            {
                "query": "error",
                "level": "ERROR",
                "limit": 10,
            }
        )

        assert result is not None
        assert "results" in result
        assert "total" in result
        assert result["search_type"] == "text"

    @patch("app.services.agent_tools.get_db")
    def test_summarize_range_tool(self, mock_get_db):
        """Test summarize_range tool."""
        from datetime import datetime, timedelta
        from uuid import uuid4

        from app.db.postgres import LogEntry

        # Mock database session
        mock_db = MagicMock()
        mock_get_db.return_value = iter([mock_db])

        # Create mock log entries
        log_id1 = uuid4()
        log_id2 = uuid4()
        now = datetime.now()
        mock_entries = [
            LogEntry(
                id=log_id1,
                timestamp=now - timedelta(hours=1),
                level="ERROR",
                service="test-service",
                message="Error: Test error 1",
                raw_log="raw1",
            ),
            LogEntry(
                id=log_id2,
                timestamp=now - timedelta(minutes=30),
                level="WARN",
                service="test-service",
                message="Warning: Test warning",
                raw_log="raw2",
            ),
        ]

        # Mock query
        mock_query = MagicMock()
        mock_query.filter.return_value.order_by.return_value.limit.return_value.all.return_value = (
            mock_entries
        )
        mock_db.query.return_value = mock_query

        start_time = (now - timedelta(hours=2)).isoformat()
        end_time = now.isoformat()

        result = summarize_range.invoke(
            {
                "start_time": start_time,
                "end_time": end_time,
                "service": "test-service",
            }
        )

        assert result is not None
        assert "summary" in result
        summary = result["summary"]
        assert "total_logs" in summary
        assert summary["total_logs"] == 2
        assert "level_distribution" in summary
        assert "error_count" in summary
        assert summary["error_count"] == 1
        assert "warning_count" in summary
        assert summary["warning_count"] == 1

    def test_get_agent_tools(self):
        """Test get_agent_tools returns list of tools."""
        tools = get_agent_tools()
        assert isinstance(tools, list)
        assert len(tools) == 5  # Updated to include new tools
        assert analyze_anomaly_tool in tools
        assert detect_anomaly_tool in tools
        assert analyze_anomaly_with_cluster_context in tools
        assert search_logs in tools
        assert summarize_range in tools
