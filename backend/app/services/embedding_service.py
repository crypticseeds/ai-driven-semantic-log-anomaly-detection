"""Service for generating text embeddings using OpenAI."""

import logging

from openai import OpenAI

from app.config import get_settings

logger = logging.getLogger(__name__)


class EmbeddingService:
    """Service for generating embeddings using OpenAI's text-embedding-3-small model."""

    def __init__(self):
        """Initialize embedding service."""
        settings = get_settings()
        if not settings.openai_api_key:
            logger.warning("OpenAI API key not configured. Embeddings will not work.")
            self.client = None
        else:
            self.client = OpenAI(api_key=settings.openai_api_key)
        self.model = "text-embedding-3-small"
        self.vector_size = 1536

    def generate_embedding(self, text: str) -> list[float] | None:
        """Generate embedding for text.

        Args:
            text: Text to generate embedding for

        Returns:
            Embedding vector (1536 dimensions) or None if error
        """
        if not self.client:
            logger.error("OpenAI client not initialized. Check OPENAI_API_KEY.")
            return None

        try:
            response = self.client.embeddings.create(
                model=self.model,
                input=text,
            )
            return response.data[0].embedding
        except Exception as e:
            logger.error(f"Error generating embedding: {e}", exc_info=True)
            return None

    def generate_embeddings_batch(self, texts: list[str]) -> list[list[float] | None]:
        """Generate embeddings for multiple texts in batch.

        Args:
            texts: List of texts to generate embeddings for

        Returns:
            List of embedding vectors (or None for failed embeddings)
        """
        if not self.client:
            logger.error("OpenAI client not initialized. Check OPENAI_API_KEY.")
            return [None] * len(texts)

        try:
            response = self.client.embeddings.create(
                model=self.model,
                input=texts,
            )
            # Return embeddings in the same order as input texts
            embeddings_dict = {item.index: item.embedding for item in response.data}
            return [embeddings_dict.get(i) for i in range(len(texts))]
        except Exception as e:
            logger.error(f"Error generating batch embeddings: {e}", exc_info=True)
            return [None] * len(texts)


# Global instance
embedding_service = EmbeddingService()
