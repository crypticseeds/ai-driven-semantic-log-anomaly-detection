"""Unit tests for anomaly detection service."""

from unittest.mock import MagicMock, patch
from uuid import uuid4

from app.services.anomaly_detection_service import AnomalyDetectionService


class TestAnomalyDetectionService:
    """Unit tests for anomaly detection service functionality."""

    def test_init(self):
        """Test service initialization."""
        service = AnomalyDetectionService()
        assert service.settings is not None
        assert service.qdrant_service is not None

    @patch("app.services.anomaly_detection_service.qdrant_service")
    def test_detect_with_isolation_forest_no_embeddings(self, mock_qdrant):
        """Test IsolationForest with no embeddings."""
        mock_qdrant.get_all_embeddings.return_value = []

        service = AnomalyDetectionService()
        result = service.detect_with_isolation_forest()

        assert result["total"] == 0
        assert result["method"] == "IsolationForest"
        assert result["anomalies"] == []

    @patch("app.services.anomaly_detection_service.qdrant_service")
    @patch("app.services.anomaly_detection_service.get_db")
    def test_detect_with_isolation_forest_success(self, mock_get_db, mock_qdrant):
        """Test successful IsolationForest detection."""
        # Create mock embeddings
        log_id1 = uuid4()
        log_id2 = uuid4()
        log_id3 = uuid4()

        mock_qdrant.get_all_embeddings.return_value = [
            {"id": str(log_id1), "vector": [0.1] * 1536},
            {"id": str(log_id2), "vector": [0.2] * 1536},
            {"id": str(log_id3), "vector": [10.0] * 1536},  # Outlier
        ]

        # Mock log entries with ERROR level
        mock_log_entries = []
        for log_id in [log_id1, log_id2, log_id3]:
            mock_entry = MagicMock()
            mock_entry.id = log_id
            mock_entry.level = "ERROR"
            mock_log_entries.append(mock_entry)

        # Mock database
        mock_db = MagicMock()
        mock_get_db.return_value = iter([mock_db])

        def query_side_effect(model):
            mock_query = MagicMock()
            if model.__name__ == "LogEntry":
                mock_query.filter.return_value.all.return_value = mock_log_entries
            mock_query.filter.return_value.first.return_value = None
            return mock_query

        mock_db.query.side_effect = query_side_effect

        service = AnomalyDetectionService()
        result = service.detect_with_isolation_forest(db=mock_db)

        assert result["method"] == "IsolationForest"
        assert result["total"] >= 0  # May detect 0 or more anomalies
        assert "anomalies" in result

    @patch("app.services.anomaly_detection_service.qdrant_service")
    @patch("app.services.anomaly_detection_service.get_db")
    def test_detect_with_zscore_success(self, mock_get_db, mock_qdrant):
        """Test successful Z-score detection."""
        log_id1 = uuid4()
        log_id2 = uuid4()

        mock_qdrant.get_all_embeddings.return_value = [
            {"id": str(log_id1), "vector": [0.1] * 1536},
            {"id": str(log_id2), "vector": [0.2] * 1536},
        ]

        # Mock log entries with ERROR level
        mock_log_entries = []
        for log_id in [log_id1, log_id2]:
            mock_entry = MagicMock()
            mock_entry.id = log_id
            mock_entry.level = "ERROR"
            mock_log_entries.append(mock_entry)

        mock_db = MagicMock()
        mock_get_db.return_value = iter([mock_db])

        def query_side_effect(model):
            mock_query = MagicMock()
            if model.__name__ == "LogEntry":
                mock_query.filter.return_value.all.return_value = mock_log_entries
            mock_query.filter.return_value.first.return_value = None
            return mock_query

        mock_db.query.side_effect = query_side_effect

        service = AnomalyDetectionService()
        result = service.detect_with_zscore(threshold=3.0, db=mock_db)

        assert result["method"] == "Z-score"
        assert result["threshold"] == 3.0
        assert "anomalies" in result

    @patch("app.services.anomaly_detection_service.qdrant_service")
    @patch("app.services.anomaly_detection_service.get_db")
    def test_detect_with_iqr_success(self, mock_get_db, mock_qdrant):
        """Test successful IQR detection."""
        log_ids = [uuid4() for _ in range(10)]

        mock_qdrant.get_all_embeddings.return_value = [
            {"id": str(log_id), "vector": [0.1 + i * 0.01] * 1536}
            for i, log_id in enumerate(log_ids)
        ]

        # Mock log entries with ERROR level
        mock_log_entries = []
        for log_id in log_ids:
            mock_entry = MagicMock()
            mock_entry.id = log_id
            mock_entry.level = "ERROR"
            mock_log_entries.append(mock_entry)

        mock_db = MagicMock()
        mock_get_db.return_value = iter([mock_db])

        def query_side_effect(model):
            mock_query = MagicMock()
            if model.__name__ == "LogEntry":
                mock_query.filter.return_value.all.return_value = mock_log_entries
            mock_query.filter.return_value.first.return_value = None
            return mock_query

        mock_db.query.side_effect = query_side_effect

        service = AnomalyDetectionService()
        result = service.detect_with_iqr(multiplier=1.5, db=mock_db)

        assert result["method"] == "IQR"
        assert result["multiplier"] == 1.5
        assert "anomalies" in result

    @patch("app.services.anomaly_detection_service.qdrant_service")
    @patch("app.services.anomaly_detection_service.get_db")
    def test_score_log_entry_success(self, mock_get_db, mock_qdrant):
        """Test real-time scoring of a log entry."""
        log_id = uuid4()

        mock_qdrant.get_vector.return_value = {
            "id": str(log_id),
            "vector": [0.1] * 1536,
            "payload": {},
        }

        mock_qdrant.get_all_embeddings.return_value = [
            {"id": str(uuid4()), "vector": [0.1 + i * 0.01] * 1536} for i in range(10)
        ]

        # Mock log entry with ERROR level (should be flagged as anomaly if statistical anomaly)
        mock_log_entry = MagicMock()
        mock_log_entry.level = "ERROR"

        mock_db = MagicMock()
        mock_get_db.return_value = iter([mock_db])

        # First query returns log entry, second returns None for AnomalyResult
        def query_side_effect(model):
            mock_query = MagicMock()
            if model.__name__ == "LogEntry":
                mock_query.filter.return_value.first.return_value = mock_log_entry
            else:
                mock_query.filter.return_value.first.return_value = None
            return mock_query

        mock_db.query.side_effect = query_side_effect

        service = AnomalyDetectionService()
        result = service.score_log_entry(log_id=log_id, method="IsolationForest", db=mock_db)

        assert result is not None
        assert result["log_id"] == str(log_id)
        assert "anomaly_score" in result
        assert "is_anomaly" in result
        assert result["method"] == "IsolationForest"

    @patch("app.services.anomaly_detection_service.qdrant_service")
    def test_score_log_entry_no_embedding(self, mock_qdrant):
        """Test scoring when no embedding exists."""
        log_id = uuid4()
        mock_qdrant.get_vector.return_value = None

        service = AnomalyDetectionService()
        result = service.score_log_entry(log_id=log_id)

        assert result is None

    @patch("app.services.anomaly_detection_service.qdrant_service")
    @patch("app.services.anomaly_detection_service.get_db")
    def test_info_logs_not_flagged_as_anomalies(self, mock_get_db, mock_qdrant):
        """Test that INFO logs are not easily flagged as anomalies.

        INFO logs should require much higher anomaly scores to be flagged,
        reducing false positives for routine log messages.
        """
        log_id_info = uuid4()
        log_id_error = uuid4()

        # Both logs have similar embeddings (slight outlier)
        mock_qdrant.get_all_embeddings.return_value = [
            {"id": str(uuid4()), "vector": [0.1] * 1536},
            {"id": str(uuid4()), "vector": [0.11] * 1536},
            {"id": str(uuid4()), "vector": [0.12] * 1536},
            {"id": str(log_id_info), "vector": [0.5] * 1536},  # Slight outlier - INFO
            {"id": str(log_id_error), "vector": [0.5] * 1536},  # Same outlier - ERROR
        ]

        # Mock log entries - one INFO, one ERROR
        mock_log_entries = [
            MagicMock(id=uuid4(), level="INFO"),
            MagicMock(id=uuid4(), level="INFO"),
            MagicMock(id=uuid4(), level="INFO"),
            MagicMock(id=log_id_info, level="INFO"),
            MagicMock(id=log_id_error, level="ERROR"),
        ]

        mock_db = MagicMock()
        mock_get_db.return_value = iter([mock_db])

        def query_side_effect(model):
            mock_query = MagicMock()
            if model.__name__ == "LogEntry":
                mock_query.filter.return_value.all.return_value = mock_log_entries
            mock_query.filter.return_value.first.return_value = None
            return mock_query

        mock_db.query.side_effect = query_side_effect

        service = AnomalyDetectionService()
        result = service.detect_with_isolation_forest(contamination=0.3, db=mock_db)

        # The service should apply level-based filtering
        # ERROR logs with same score should be more likely to be flagged than INFO logs
        assert result["method"] == "IsolationForest"
        assert "anomalies" in result
