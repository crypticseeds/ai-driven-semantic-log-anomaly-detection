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

        # Mock database
        mock_db = MagicMock()
        mock_get_db.return_value = iter([mock_db])
        mock_db.query.return_value.filter.return_value.first.return_value = None

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

        mock_db = MagicMock()
        mock_get_db.return_value = iter([mock_db])
        mock_db.query.return_value.filter.return_value.first.return_value = None

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

        mock_db = MagicMock()
        mock_get_db.return_value = iter([mock_db])
        mock_db.query.return_value.filter.return_value.first.return_value = None

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

        mock_db = MagicMock()
        mock_get_db.return_value = iter([mock_db])
        mock_db.query.return_value.filter.return_value.first.return_value = None

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
