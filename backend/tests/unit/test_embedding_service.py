"""Unit tests for embedding service."""

import os
from unittest.mock import MagicMock, patch

from app.config import get_settings
from app.services.embedding_service import EmbeddingService


class TestEmbeddingService:
    """Unit tests for embedding service functionality."""

    def test_init_without_api_key(self):
        """Test initialization without OpenAI API key."""
        get_settings.cache_clear()
        with patch.dict(os.environ, {}, clear=True):
            service = EmbeddingService()
            assert service.client is None
            assert service.model == "text-embedding-3-small"
            assert service.vector_size == 1536

    def test_init_with_api_key(self):
        """Test initialization with OpenAI API key."""
        get_settings.cache_clear()
        with (
            patch.dict(os.environ, {"OPENAI_API_KEY": "test-key"}),
            patch("app.services.embedding_service.OpenAI") as mock_openai,
        ):
            service = EmbeddingService()
            assert service.client is not None
            mock_openai.assert_called_once_with(api_key="test-key")

    def test_generate_embedding_without_client(self):
        """Test generating embedding without client initialized."""
        service = EmbeddingService()
        service.client = None

        result = service.generate_embedding("test text")
        assert result is None

    @patch("app.services.embedding_service.OpenAI")
    def test_generate_embedding_success(self, mock_openai_class):
        """Test successful embedding generation."""
        # Mock OpenAI client
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.data = [MagicMock(embedding=[0.1] * 1536)]
        mock_client.embeddings.create.return_value = mock_response
        mock_openai_class.return_value = mock_client

        get_settings.cache_clear()
        with patch.dict(os.environ, {"OPENAI_API_KEY": "test-key"}):
            service = EmbeddingService()
            result = service.generate_embedding("test text")

            assert result is not None
            assert len(result) == 1536
            mock_client.embeddings.create.assert_called_once_with(
                model="text-embedding-3-small", input="test text"
            )

    @patch("app.services.embedding_service.OpenAI")
    def test_generate_embedding_error(self, mock_openai_class):
        """Test embedding generation with error."""
        mock_client = MagicMock()
        mock_client.embeddings.create.side_effect = Exception("API Error")
        mock_openai_class.return_value = mock_client

        get_settings.cache_clear()
        with patch.dict(os.environ, {"OPENAI_API_KEY": "test-key"}):
            service = EmbeddingService()
            result = service.generate_embedding("test text")

            assert result is None

    @patch("app.services.embedding_service.OpenAI")
    def test_generate_embeddings_batch_success(self, mock_openai_class):
        """Test successful batch embedding generation."""
        mock_client = MagicMock()
        mock_response = MagicMock()
        # Create mock embeddings with index
        mock_embeddings = [
            MagicMock(index=0, embedding=[0.1] * 1536),
            MagicMock(index=1, embedding=[0.2] * 1536),
        ]
        mock_response.data = mock_embeddings
        mock_client.embeddings.create.return_value = mock_response
        mock_openai_class.return_value = mock_client

        get_settings.cache_clear()
        with patch.dict(os.environ, {"OPENAI_API_KEY": "test-key"}):
            service = EmbeddingService()
            texts = ["text1", "text2"]
            results = service.generate_embeddings_batch(texts)

            assert len(results) == 2
            assert all(r is not None for r in results)
            mock_client.embeddings.create.assert_called_once_with(
                model="text-embedding-3-small", input=texts
            )

    def test_generate_embeddings_batch_without_client(self):
        """Test batch embedding generation without client."""
        service = EmbeddingService()
        service.client = None

        results = service.generate_embeddings_batch(["text1", "text2"])
        assert len(results) == 2
        assert all(r is None for r in results)
