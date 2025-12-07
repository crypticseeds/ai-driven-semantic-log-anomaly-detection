"""Unit tests for clustering service."""

from unittest.mock import MagicMock, patch
from uuid import uuid4

import numpy as np
from sqlalchemy.orm import Session

from app.db.postgres import AnomalyResult, ClusteringMetadata, LogEntry
from app.services.clustering_service import ClusteringService


class TestClusteringService:
    """Unit tests for clustering service functionality."""

    @patch("app.services.clustering_service.get_settings")
    def test_init(self, mock_get_settings):
        """Test initialization of clustering service."""
        mock_settings = MagicMock()
        mock_settings.hdbscan_min_cluster_size = 5
        mock_settings.hdbscan_min_samples = 3
        mock_settings.hdbscan_cluster_selection_epsilon = 0.0
        mock_settings.hdbscan_max_cluster_size = None
        mock_settings.hdbscan_sample_size = None
        mock_get_settings.return_value = mock_settings

        service = ClusteringService()
        assert service.settings is not None
        assert service.qdrant_service is not None

    @patch("app.services.clustering_service.get_settings")
    @patch("app.services.clustering_service.qdrant_service")
    def test_perform_clustering_no_embeddings(self, mock_qdrant_service, mock_get_settings):
        """Test clustering when no embeddings are available."""
        mock_settings = MagicMock()
        mock_settings.hdbscan_min_cluster_size = 5
        mock_settings.hdbscan_min_samples = 3
        mock_settings.hdbscan_cluster_selection_epsilon = 0.0
        mock_settings.hdbscan_max_cluster_size = None
        mock_settings.hdbscan_sample_size = None
        mock_get_settings.return_value = mock_settings

        mock_qdrant_service.get_all_embeddings.return_value = []

        service = ClusteringService()
        mock_db = MagicMock(spec=Session)

        result = service.perform_clustering(db=mock_db)

        assert result["n_clusters"] == 0
        assert result["n_outliers"] == 0
        assert "error" in result
        assert result["error"] == "No embeddings found"

    @patch("app.services.clustering_service.get_settings")
    @patch("app.services.clustering_service.qdrant_service")
    @patch("app.services.clustering_service.HDBSCAN")
    def test_perform_clustering_success(self, mock_hdbscan, mock_qdrant_service, mock_get_settings):
        """Test successful clustering."""
        mock_settings = MagicMock()
        mock_settings.hdbscan_min_cluster_size = 5
        mock_settings.hdbscan_min_samples = 3
        mock_settings.hdbscan_cluster_selection_epsilon = 0.0
        mock_settings.hdbscan_max_cluster_size = None
        mock_settings.hdbscan_sample_size = None
        mock_get_settings.return_value = mock_settings

        # Create mock embeddings
        log_id1 = uuid4()
        log_id2 = uuid4()
        log_id3 = uuid4()
        log_id4 = uuid4()
        log_id5 = uuid4()
        log_id6 = uuid4()

        embeddings_data = [
            {"id": str(log_id1), "vector": [0.1] * 1536, "payload": {}},
            {"id": str(log_id2), "vector": [0.1] * 1536, "payload": {}},
            {"id": str(log_id3), "vector": [0.1] * 1536, "payload": {}},
            {"id": str(log_id4), "vector": [0.1] * 1536, "payload": {}},
            {"id": str(log_id5), "vector": [0.1] * 1536, "payload": {}},
            {"id": str(log_id6), "vector": [0.9] * 1536, "payload": {}},  # Outlier
        ]

        mock_qdrant_service.get_all_embeddings.return_value = embeddings_data

        # Mock HDBSCAN
        mock_clusterer = MagicMock()
        # Create cluster labels: first 5 in cluster 0, last one is outlier (-1)
        mock_clusterer.fit_predict.return_value = np.array([0, 0, 0, 0, 0, -1])
        mock_hdbscan.return_value = mock_clusterer

        service = ClusteringService()
        mock_db = MagicMock(spec=Session)
        mock_db.query.return_value.filter.return_value.first.return_value = None
        mock_db.query.return_value.filter.return_value.all.return_value = []

        result = service.perform_clustering(db=mock_db)

        assert result["n_clusters"] == 1
        assert result["n_outliers"] == 1
        assert len(result["cluster_assignments"]) == 6
        assert result["cluster_assignments"][str(log_id6)] == -1
        mock_clusterer.fit_predict.assert_called_once()

    @patch("app.services.clustering_service.get_settings")
    @patch("app.services.clustering_service.qdrant_service")
    @patch("app.services.clustering_service.HDBSCAN")
    def test_perform_clustering_with_sampling(
        self, mock_hdbscan, mock_qdrant_service, mock_get_settings
    ):
        """Test clustering with sampling for large datasets."""
        mock_settings = MagicMock()
        mock_settings.hdbscan_min_cluster_size = 5
        mock_settings.hdbscan_min_samples = 3
        mock_settings.hdbscan_cluster_selection_epsilon = 0.0
        mock_settings.hdbscan_max_cluster_size = None
        mock_settings.hdbscan_sample_size = None
        mock_get_settings.return_value = mock_settings

        # Create many mock embeddings
        embeddings_data = [
            {"id": str(uuid4()), "vector": [0.1] * 1536, "payload": {}} for _ in range(1000)
        ]

        mock_qdrant_service.get_all_embeddings.return_value = embeddings_data

        # Mock HDBSCAN
        mock_clusterer = MagicMock()
        mock_clusterer.fit_predict.return_value = np.array([0] * 1000)
        mock_hdbscan.return_value = mock_clusterer

        service = ClusteringService()
        mock_db = MagicMock(spec=Session)
        mock_db.query.return_value.filter.return_value.first.return_value = None
        mock_db.query.return_value.filter.return_value.all.return_value = []

        # Test with sample_size parameter
        result = service.perform_clustering(sample_size=100, db=mock_db)

        # Should still work, but with sampled data
        assert "n_clusters" in result
        mock_clusterer.fit_predict.assert_called_once()

    @patch("app.services.clustering_service.get_settings")
    @patch("app.services.clustering_service.qdrant_service")
    def test_perform_clustering_invalid_embeddings(self, mock_qdrant_service, mock_get_settings):
        """Test clustering with invalid embeddings (no vectors)."""
        mock_settings = MagicMock()
        mock_settings.hdbscan_min_cluster_size = 5
        mock_settings.hdbscan_min_samples = 3
        mock_settings.hdbscan_cluster_selection_epsilon = 0.0
        mock_settings.hdbscan_max_cluster_size = None
        mock_settings.hdbscan_sample_size = None
        mock_get_settings.return_value = mock_settings

        # Embeddings without vectors
        embeddings_data = [
            {"id": str(uuid4()), "vector": None, "payload": {}},
            {"id": str(uuid4()), "vector": None, "payload": {}},
        ]

        mock_qdrant_service.get_all_embeddings.return_value = embeddings_data

        service = ClusteringService()
        mock_db = MagicMock(spec=Session)

        result = service.perform_clustering(db=mock_db)

        assert result["n_clusters"] == 0
        assert result["n_outliers"] == 0
        assert "error" in result
        assert result["error"] == "No valid embeddings found"

    @patch("app.services.clustering_service.get_settings")
    def test_store_cluster_assignments(self, mock_get_settings):
        """Test storing cluster assignments in database."""
        mock_settings = MagicMock()
        mock_get_settings.return_value = mock_settings

        service = ClusteringService()
        mock_db = MagicMock(spec=Session)

        # Mock query to return None (no existing record)
        mock_query = MagicMock()
        mock_query.filter.return_value.first.return_value = None
        mock_db.query.return_value = mock_query

        cluster_assignments = {
            str(uuid4()): 0,
            str(uuid4()): 1,
            str(uuid4()): -1,  # Outlier
        }

        service._store_cluster_assignments(cluster_assignments, mock_db)

        # Should commit
        mock_db.commit.assert_called_once()
        # Should add new records
        assert mock_db.add.call_count == 3

    @patch("app.services.clustering_service.get_settings")
    def test_store_cluster_assignments_update_existing(self, mock_get_settings):
        """Test updating existing cluster assignments."""
        mock_settings = MagicMock()
        mock_get_settings.return_value = mock_settings

        service = ClusteringService()
        mock_db = MagicMock(spec=Session)

        # Mock existing AnomalyResult
        mock_existing = MagicMock()
        mock_query = MagicMock()
        mock_query.filter.return_value.first.return_value = mock_existing
        mock_db.query.return_value = mock_query

        log_id = uuid4()
        cluster_assignments = {str(log_id): 0}

        service._store_cluster_assignments(cluster_assignments, mock_db)

        # Should update existing record
        assert mock_existing.cluster_id == 0
        assert mock_existing.detection_method == "HDBSCAN"
        mock_db.commit.assert_called_once()

    @patch("app.services.clustering_service.get_settings")
    def test_calculate_cluster_metadata(self, mock_get_settings):
        """Test calculating cluster metadata."""
        mock_settings = MagicMock()
        mock_get_settings.return_value = mock_settings

        service = ClusteringService()
        mock_db = MagicMock(spec=Session)

        # Mock query to return None (no existing metadata)
        mock_query = MagicMock()
        mock_query.filter.return_value.first.return_value = None
        mock_db.query.return_value = mock_query

        log_ids = [uuid4() for _ in range(10)]
        cluster_labels = np.array([0, 0, 0, 1, 1, 1, 1, -1, -1, -1])
        vectors = np.random.rand(10, 1536)

        metadata = service._calculate_cluster_metadata(cluster_labels, log_ids, vectors, mock_db)

        # Should have metadata for 2 clusters (0 and 1, excluding -1)
        assert len(metadata) == 2
        assert 0 in metadata
        assert 1 in metadata
        assert metadata[0]["cluster_size"] == 3
        assert metadata[1]["cluster_size"] == 4
        mock_db.commit.assert_called_once()

    @patch("app.services.clustering_service.get_settings")
    def test_get_cluster_info_not_found(self, mock_get_settings):
        """Test getting cluster info when cluster doesn't exist."""
        mock_settings = MagicMock()
        mock_get_settings.return_value = mock_settings

        service = ClusteringService()
        mock_db = MagicMock(spec=Session)

        # Mock query to return None
        mock_query = MagicMock()
        mock_query.filter.return_value.first.return_value = None
        mock_db.query.return_value = mock_query

        result = service.get_cluster_info(999, db=mock_db)

        assert result is None

    @patch("app.services.clustering_service.get_settings")
    def test_get_cluster_info_success(self, mock_get_settings):
        """Test getting cluster info successfully."""
        mock_settings = MagicMock()
        mock_get_settings.return_value = mock_settings

        service = ClusteringService()
        mock_db = MagicMock(spec=Session)

        # Mock ClusteringMetadata
        mock_metadata = MagicMock()
        mock_metadata.cluster_id = 0
        mock_metadata.cluster_size = 5
        mock_metadata.cluster_centroid = [0.1] * 1536
        mock_metadata.representative_logs = [str(uuid4())]

        # Mock AnomalyResult
        mock_anomaly_result = MagicMock()
        mock_anomaly_result.log_entry_id = uuid4()

        # Mock LogEntry
        mock_log_entry = MagicMock()
        mock_log_entry.id = mock_anomaly_result.log_entry_id
        mock_log_entry.message = "Test log message"
        mock_log_entry.level = "INFO"
        mock_log_entry.service = "test-service"
        mock_log_entry.timestamp.isoformat.return_value = "2024-01-01T00:00:00"

        # Setup query chain
        mock_query_metadata = MagicMock()
        mock_query_metadata.filter.return_value.first.return_value = mock_metadata

        mock_query_anomaly = MagicMock()
        mock_query_anomaly.filter.return_value.all.return_value = [mock_anomaly_result]

        mock_query_log = MagicMock()
        mock_query_log.filter.return_value.limit.return_value.all.return_value = [mock_log_entry]

        def query_side_effect(model):
            if model is ClusteringMetadata:
                return mock_query_metadata
            elif model is AnomalyResult:
                return mock_query_anomaly
            elif model is LogEntry:
                return mock_query_log
            return MagicMock()

        mock_db.query.side_effect = query_side_effect

        result = service.get_cluster_info(0, db=mock_db)

        assert result is not None
        assert result["cluster_id"] == 0
        assert result["cluster_size"] == 5
        assert len(result["sample_logs"]) == 1
