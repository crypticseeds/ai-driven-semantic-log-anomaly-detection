"""Integration tests for agent API endpoints."""

from unittest.mock import MagicMock, patch
from uuid import uuid4

from fastapi.testclient import TestClient

from app.db.session import get_db
from app.main import app

client = TestClient(app)


class TestAgentEndpoints:
    """Integration tests for agent API endpoints."""

    @patch("app.api.v1.agent.analyze_anomaly_tool")
    def test_analyze_anomaly_endpoint(self, mock_tool):
        """Test POST /api/v1/agent/analyze-anomaly endpoint."""
        mock_tool.invoke.return_value = {
            "explanation": "Test explanation",
            "root_causes": [],
            "remediation_steps": [],
            "severity": "MEDIUM",
            "severity_reason": "Test",
        }

        response = client.post(
            "/api/v1/agent/analyze-anomaly",
            params={
                "log_message": "Error: Test error",
                "log_level": "ERROR",
                "include_root_cause": True,
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert "explanation" in data
        assert "severity" in data

    @patch("app.api.v1.agent.detect_anomaly_tool")
    def test_detect_anomaly_endpoint(self, mock_tool):
        """Test POST /api/v1/agent/detect-anomaly endpoint."""
        mock_tool.invoke.return_value = {
            "is_anomaly": True,
            "confidence": 0.85,
            "reasoning": "This is an anomaly",
        }

        response = client.post(
            "/api/v1/agent/detect-anomaly",
            params={
                "log_message": "Error: Test error",
                "log_level": "ERROR",
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["is_anomaly"] is True
        assert data["confidence"] == 0.85

    @patch("app.api.v1.agent.analyze_anomaly_tool")
    def test_analyze_anomaly_by_id_endpoint(self, mock_tool):
        """Test POST /api/v1/agent/analyze-anomaly/{log_id} endpoint."""
        from datetime import datetime

        from app.db.postgres import AnomalyResult, LogEntry

        log_id = uuid4()
        mock_db = MagicMock()
        mock_log_entry = LogEntry(
            id=log_id,
            timestamp=datetime.now(),
            level="ERROR",
            service="test-service",
            message="Error: Test error",
            raw_log="raw",
        )

        # Mock the query chain for LogEntry
        mock_log_query = MagicMock()
        mock_log_query.filter.return_value.first.return_value = mock_log_entry

        # Mock the query chain for AnomalyResult (no cluster context)
        mock_anomaly_query = MagicMock()
        mock_anomaly_query.filter.return_value.first.return_value = None

        # Set up query to return different mocks based on what's queried
        def query_side_effect(model):
            if model == LogEntry:
                return mock_log_query
            elif model == AnomalyResult:
                return mock_anomaly_query
            return MagicMock()

        mock_db.query.side_effect = query_side_effect

        # Override FastAPI dependency
        def override_get_db():
            yield mock_db

        app.dependency_overrides[get_db] = override_get_db

        try:
            mock_tool.invoke.return_value = {
                "explanation": "Test explanation",
                "root_causes": [],
                "remediation_steps": [],
                "severity": "MEDIUM",
                "severity_reason": "Test",
            }

            response = client.post(
                f"/api/v1/agent/analyze-anomaly/{log_id}",
                params={"include_root_cause": True},
            )

            assert response.status_code == 200
            data = response.json()
            assert "explanation" in data
        finally:
            # Clean up dependency override
            app.dependency_overrides.pop(get_db, None)

    @patch("app.api.v1.agent.analyze_anomaly_tool")
    def test_analyze_anomaly_stream_endpoint(self, mock_tool):
        """Test POST /api/v1/agent/analyze-anomaly/stream endpoint."""
        mock_tool.invoke.return_value = {
            "explanation": "Test explanation",
            "root_causes": [],
            "remediation_steps": [],
            "severity": "MEDIUM",
            "severity_reason": "Test",
        }

        response = client.post(
            "/api/v1/agent/analyze-anomaly/stream",
            params={
                "log_message": "Error: Test error",
                "include_root_cause": True,  # FastAPI Query handles bool conversion
            },
        )

        assert response.status_code == 200
        assert response.headers["content-type"] == "text/event-stream; charset=utf-8"

    def test_list_agent_tools_endpoint(self):
        """Test GET /api/v1/agent/tools endpoint."""
        response = client.get("/api/v1/agent/tools")

        assert response.status_code == 200
        data = response.json()
        assert "tools" in data
        assert len(data["tools"]) == 5  # Updated to include new tools
        tool_names = [tool["name"] for tool in data["tools"]]
        assert "analyze_anomaly_tool" in tool_names
        assert "detect_anomaly_tool" in tool_names
        assert "analyze_anomaly_with_cluster_context" in tool_names
        assert "search_logs" in tool_names
        assert "summarize_range" in tool_names

    @patch("app.api.v1.agent.agent_executor_service")
    def test_root_cause_analysis_endpoint(self, mock_service):
        """Test POST /api/v1/agent/rca endpoint."""
        # Mock agent executor service
        mock_service.is_available.return_value = True
        mock_service.analyze_root_cause.return_value = {
            "response": "Based on the analysis, the root cause appears to be...",
            "intermediate_steps": [],
            "query": "What caused the errors?",
        }

        response = client.post(
            "/api/v1/agent/rca",
            params={"query": "What caused the errors?"},
        )

        assert response.status_code == 200
        data = response.json()
        assert "response" in data
        assert "query" in data
        assert data["query"] == "What caused the errors?"

    @patch("app.api.v1.agent.agent_executor_service")
    def test_root_cause_analysis_endpoint_unavailable(self, mock_service):
        """Test POST /api/v1/agent/rca endpoint when agent executor is unavailable."""
        mock_service.is_available.return_value = False

        response = client.post(
            "/api/v1/agent/rca",
            params={"query": "What caused the errors?"},
        )

        assert response.status_code == 503
        data = response.json()
        assert "detail" in data
        assert "not available" in data["detail"].lower()

    @patch("app.api.v1.agent.agent_executor_service")
    def test_root_cause_analysis_with_context(self, mock_service):
        """Test POST /api/v1/agent/rca endpoint with context."""
        mock_service.is_available.return_value = True
        mock_service.analyze_root_cause.return_value = {
            "response": "Analysis with context",
            "intermediate_steps": [],
            "query": "Analyze errors",
        }

        import json

        context = json.dumps({"service": "auth-service", "time_range": "last_hour"})

        response = client.post(
            "/api/v1/agent/rca",
            params={"query": "Analyze errors", "context": context},
        )

        assert response.status_code == 200
        data = response.json()
        assert "response" in data
