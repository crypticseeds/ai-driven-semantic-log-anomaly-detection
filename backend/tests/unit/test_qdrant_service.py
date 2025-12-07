"""Unit tests for Qdrant service."""

from unittest.mock import MagicMock, patch
from uuid import uuid4

from app.services.qdrant_service import QdrantService


class TestQdrantService:
    """Unit tests for Qdrant service functionality."""

    @patch("app.services.qdrant_service.get_settings")
    def test_init_without_credentials(self, mock_get_settings):
        """Test initialization without Qdrant credentials."""
        mock_settings = MagicMock()
        mock_settings.qdrant_url = None
        mock_settings.qdrant_api_key = None
        mock_settings.qdrant_collection = "log_embeddings"
        mock_get_settings.return_value = mock_settings

        service = QdrantService()
        assert service.client is None
        assert service.collection_name == "log_embeddings"
        assert service.vector_size == 1536

    @patch("app.services.qdrant_service.get_settings")
    @patch("app.services.qdrant_service.QdrantClient")
    def test_init_with_credentials(self, mock_qdrant_client, mock_get_settings):
        """Test initialization with Qdrant credentials."""
        mock_client = MagicMock()
        mock_qdrant_client.return_value = mock_client

        mock_settings = MagicMock()
        mock_settings.qdrant_url = "https://test.qdrant.io"
        mock_settings.qdrant_api_key = "test-key"
        mock_settings.qdrant_collection = "log_embeddings"
        mock_get_settings.return_value = mock_settings

        service = QdrantService()
        assert service.client is not None
        mock_qdrant_client.assert_called_once_with(url="https://test.qdrant.io", api_key="test-key")

    @patch("app.services.qdrant_service.get_settings")
    @patch("app.services.qdrant_service.QdrantClient")
    def test_ensure_collection_exists(self, mock_qdrant_client, mock_get_settings):
        """Test ensuring collection when it already exists."""
        mock_client = MagicMock()
        mock_collection = MagicMock()
        mock_collection.name = "log_embeddings"
        mock_client.get_collections.return_value = MagicMock(collections=[mock_collection])
        mock_collection_info = MagicMock()
        mock_collection_info.config.params.vectors.size = 1536
        mock_client.get_collection.return_value = mock_collection_info
        mock_qdrant_client.return_value = mock_client

        mock_settings = MagicMock()
        mock_settings.qdrant_url = "https://test.qdrant.io"
        mock_settings.qdrant_api_key = "test-key"
        mock_settings.qdrant_collection = "log_embeddings"
        mock_get_settings.return_value = mock_settings

        service = QdrantService()
        result = service.ensure_collection()

        assert result is True
        mock_client.get_collections.assert_called_once()
        mock_client.get_collection.assert_called_once_with("log_embeddings")
        # Should not create collection
        mock_client.create_collection.assert_not_called()

    @patch("app.services.qdrant_service.get_settings")
    @patch("app.services.qdrant_service.QdrantClient")
    def test_ensure_collection_creates_new(self, mock_qdrant_client, mock_get_settings):
        """Test creating collection when it doesn't exist."""
        mock_client = MagicMock()
        mock_client.get_collections.return_value = MagicMock(collections=[])
        mock_qdrant_client.return_value = mock_client

        mock_settings = MagicMock()
        mock_settings.qdrant_url = "https://test.qdrant.io"
        mock_settings.qdrant_api_key = "test-key"
        mock_settings.qdrant_collection = "log_embeddings"
        mock_get_settings.return_value = mock_settings

        service = QdrantService()
        result = service.ensure_collection()

        assert result is True
        mock_client.create_collection.assert_called_once()
        call_args = mock_client.create_collection.call_args
        assert call_args[1]["collection_name"] == "log_embeddings"
        assert call_args[1]["vectors_config"].size == 1536

    @patch("app.services.qdrant_service.get_settings")
    @patch("app.services.qdrant_service.QdrantClient")
    def test_store_vector_success(self, mock_qdrant_client, mock_get_settings):
        """Test storing a vector successfully."""
        mock_client = MagicMock()
        mock_client.get_collections.return_value = MagicMock(
            collections=[MagicMock(name="log_embeddings")]
        )
        mock_collection_info = MagicMock()
        mock_collection_info.config.params.vectors.size = 1536
        mock_client.get_collection.return_value = mock_collection_info
        mock_qdrant_client.return_value = mock_client

        mock_settings = MagicMock()
        mock_settings.qdrant_url = "https://test.qdrant.io"
        mock_settings.qdrant_api_key = "test-key"
        mock_settings.qdrant_collection = "log_embeddings"
        mock_get_settings.return_value = mock_settings

        service = QdrantService()
        log_id = uuid4()
        embedding = [0.1] * 1536
        payload = {"level": "INFO", "service": "test-service"}

        result = service.store_vector(log_id, embedding, payload)

        assert result is True
        mock_client.upsert.assert_called_once()

    @patch("app.services.qdrant_service.get_settings")
    def test_store_vector_without_client(self, mock_get_settings):
        """Test storing vector without client."""
        mock_settings = MagicMock()
        mock_settings.qdrant_url = None
        mock_settings.qdrant_api_key = None
        mock_get_settings.return_value = mock_settings

        service = QdrantService()
        log_id = uuid4()
        embedding = [0.1] * 1536

        result = service.store_vector(log_id, embedding)

        assert result is False

    @patch("app.services.qdrant_service.get_settings")
    @patch("app.services.qdrant_service.QdrantClient")
    def test_search_vectors_success(self, mock_qdrant_client, mock_get_settings):
        """Test searching vectors successfully."""
        mock_client = MagicMock()
        mock_client.get_collections.return_value = MagicMock(
            collections=[MagicMock(name="log_embeddings")]
        )
        mock_collection_info = MagicMock()
        mock_collection_info.config.params.vectors.size = 1536
        mock_client.get_collection.return_value = mock_collection_info

        # Mock search results
        mock_result = MagicMock()
        mock_result.id = str(uuid4())
        mock_result.score = 0.95
        mock_result.payload = {"level": "INFO"}
        mock_client.search.return_value = [mock_result]
        mock_qdrant_client.return_value = mock_client

        mock_settings = MagicMock()
        mock_settings.qdrant_url = "https://test.qdrant.io"
        mock_settings.qdrant_api_key = "test-key"
        mock_settings.qdrant_collection = "log_embeddings"
        mock_get_settings.return_value = mock_settings

        service = QdrantService()
        query_embedding = [0.1] * 1536

        results = service.search_vectors(query_embedding, limit=10)

        assert len(results) == 1
        assert results[0]["id"] == mock_result.id
        assert results[0]["score"] == 0.95
        assert results[0]["payload"] == {"level": "INFO"}
        mock_client.search.assert_called_once()

    @patch("app.services.qdrant_service.get_settings")
    def test_search_vectors_without_client(self, mock_get_settings):
        """Test searching vectors without client."""
        mock_settings = MagicMock()
        mock_settings.qdrant_url = None
        mock_settings.qdrant_api_key = None
        mock_get_settings.return_value = mock_settings

        service = QdrantService()
        query_embedding = [0.1] * 1536

        results = service.search_vectors(query_embedding)

        assert results == []

    @patch("app.services.qdrant_service.get_settings")
    @patch("app.services.qdrant_service.QdrantClient")
    def test_delete_vector_success(self, mock_qdrant_client, mock_get_settings):
        """Test deleting a vector successfully."""
        mock_client = MagicMock()
        mock_qdrant_client.return_value = mock_client

        mock_settings = MagicMock()
        mock_settings.qdrant_url = "https://test.qdrant.io"
        mock_settings.qdrant_api_key = "test-key"
        mock_settings.qdrant_collection = "log_embeddings"
        mock_get_settings.return_value = mock_settings

        service = QdrantService()
        log_id = uuid4()

        result = service.delete_vector(log_id)

        assert result is True
        mock_client.delete.assert_called_once()

    @patch("app.services.qdrant_service.get_settings")
    @patch("app.services.qdrant_service.QdrantClient")
    def test_get_collection_info_success(self, mock_qdrant_client, mock_get_settings):
        """Test getting collection info successfully."""
        mock_client = MagicMock()
        mock_collection_info = MagicMock()
        mock_collection_info.points_count = 100
        # Note: vectors_count doesn't exist in Qdrant CollectionInfo, only points_count
        # The service maps points_count to vectors_count for backward compatibility
        mock_collection_info.status = "green"
        mock_collection_info.config.params.vectors.size = 1536
        mock_collection_info.config.params.vectors.distance = "Cosine"
        mock_client.get_collection.return_value = mock_collection_info
        mock_qdrant_client.return_value = mock_client

        mock_settings = MagicMock()
        mock_settings.qdrant_url = "https://test.qdrant.io"
        mock_settings.qdrant_api_key = "test-key"
        mock_settings.qdrant_collection = "log_embeddings"
        mock_get_settings.return_value = mock_settings

        service = QdrantService()
        info = service.get_collection_info()

        assert info is not None
        assert info["points_count"] == 100
        assert info["vectors_count"] == 100
        assert info["status"] == "green"
        assert info["config"]["vector_size"] == 1536

    @patch("app.services.qdrant_service.get_settings")
    def test_get_collection_info_without_client(self, mock_get_settings):
        """Test getting collection info without client."""
        mock_settings = MagicMock()
        mock_settings.qdrant_url = None
        mock_settings.qdrant_api_key = None
        mock_get_settings.return_value = mock_settings

        service = QdrantService()
        info = service.get_collection_info()

        assert info is None
