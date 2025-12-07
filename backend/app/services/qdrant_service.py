"""Qdrant vector storage service for log embeddings."""

import logging
import time
from typing import Any
from uuid import UUID

from qdrant_client import QdrantClient
from qdrant_client.http import models
from qdrant_client.http.models import (
    Distance,
    Filter,
    PointStruct,
    SearchParams,
)

from app.config import get_settings
from app.observability.metrics import (
    qdrant_operation_duration_seconds,
    qdrant_operations_total,
    vector_store_size,
)

logger = logging.getLogger(__name__)


class QdrantService:
    """Service for storing and searching log embeddings in Qdrant."""

    def __init__(self):
        """Initialize Qdrant service."""
        settings = get_settings()
        self.collection_name = settings.qdrant_collection
        self.vector_size = 1536  # text-embedding-3-small dimension

        if not settings.qdrant_url or not settings.qdrant_api_key:
            logger.warning("Qdrant credentials not configured. Vector storage will not work.")
            self.client = None
            return

        try:
            self.client = QdrantClient(
                url=settings.qdrant_url,
                api_key=settings.qdrant_api_key,
            )
            logger.info(f"Connected to Qdrant at {settings.qdrant_url}")
        except Exception as e:
            logger.error(f"Failed to connect to Qdrant: {e}", exc_info=True)
            self.client = None

    def ensure_collection(self) -> bool:
        """Ensure collection exists with correct configuration.

        Returns:
            True if collection exists or was created successfully
        """
        if not self.client:
            logger.error("Qdrant client not initialized.")
            return False

        try:
            # Check if collection exists
            collections = self.client.get_collections().collections
            collection_names = [col.name for col in collections]

            if self.collection_name in collection_names:
                # Verify collection configuration
                collection_info = self.client.get_collection(self.collection_name)
                config = collection_info.config.params

                # Check vector size matches
                if hasattr(config, "vectors") and config.vectors.size != self.vector_size:
                    logger.warning(
                        f"Collection {self.collection_name} has vector size "
                        f"{config.vectors.size}, expected {self.vector_size}"
                    )
                logger.info(f"Collection {self.collection_name} already exists")
                return True

            # Create collection with correct settings
            logger.info(f"Creating collection {self.collection_name}")
            start_time = time.time()
            try:
                self.client.create_collection(
                    collection_name=self.collection_name,
                    vectors_config=models.VectorParams(
                        size=self.vector_size,
                        distance=Distance.COSINE,
                    ),
                )
                duration = time.time() - start_time
                qdrant_operation_duration_seconds.labels(operation="create_collection").observe(
                    duration
                )
                qdrant_operations_total.labels(
                    operation="create_collection", status="success"
                ).inc()
                logger.info(f"Collection {self.collection_name} created successfully")
                self._update_vector_store_size()
                return True
            except Exception:
                duration = time.time() - start_time
                qdrant_operation_duration_seconds.labels(operation="create_collection").observe(
                    duration
                )
                qdrant_operations_total.labels(operation="create_collection", status="error").inc()
                raise

        except Exception as e:
            logger.error(f"Error ensuring collection: {e}", exc_info=True)
            return False

    def store_vector(
        self,
        log_id: UUID,
        embedding: list[float],
        payload: dict[str, Any] | None = None,
    ) -> bool:
        """Store a vector in Qdrant.

        Args:
            log_id: UUID of the log entry
            embedding: Embedding vector (1536 dimensions)
            payload: Optional metadata payload (level, service, timestamp, etc.)

        Returns:
            True if stored successfully
        """
        if not self.client:
            logger.error("Qdrant client not initialized.")
            return False

        if not self.ensure_collection():
            return False

        start_time = time.time()
        try:
            point = PointStruct(
                id=str(log_id),
                vector=embedding,
                payload=payload or {},
            )
            self.client.upsert(
                collection_name=self.collection_name,
                points=[point],
            )
            duration = time.time() - start_time
            qdrant_operation_duration_seconds.labels(operation="store_vector").observe(duration)
            qdrant_operations_total.labels(operation="store_vector", status="success").inc()
            self._update_vector_store_size()
            logger.debug(f"Stored vector for log_id: {log_id}")
            return True
        except Exception as e:
            duration = time.time() - start_time
            qdrant_operation_duration_seconds.labels(operation="store_vector").observe(duration)
            qdrant_operations_total.labels(operation="store_vector", status="error").inc()
            logger.error(f"Error storing vector: {e}", exc_info=True)
            return False

    def search_vectors(
        self,
        query_embedding: list[float],
        limit: int = 10,
        filter_conditions: Filter | None = None,
        score_threshold: float | None = None,
    ) -> list[dict[str, Any]]:
        """Search for similar vectors using hybrid filtering.

        Args:
            query_embedding: Query embedding vector
            limit: Maximum number of results
            filter_conditions: Optional Qdrant filter for metadata (level, service, etc.)
            score_threshold: Optional minimum similarity score threshold

        Returns:
            List of search results with id, score, and payload
        """
        if not self.client:
            logger.error("Qdrant client not initialized.")
            return []

        if not self.ensure_collection():
            return []

        start_time = time.time()
        try:
            search_params = SearchParams()
            if score_threshold is not None:
                search_params.score_threshold = score_threshold

            results = self.client.search(
                collection_name=self.collection_name,
                query_vector=query_embedding,
                query_filter=filter_conditions,
                limit=limit,
                search_params=search_params,
            )

            duration = time.time() - start_time
            qdrant_operation_duration_seconds.labels(operation="search_vectors").observe(duration)
            qdrant_operations_total.labels(operation="search_vectors", status="success").inc()

            return [
                {
                    "id": result.id,
                    "score": result.score,
                    "payload": result.payload,
                }
                for result in results
            ]
        except Exception as e:
            duration = time.time() - start_time
            qdrant_operation_duration_seconds.labels(operation="search_vectors").observe(duration)
            qdrant_operations_total.labels(operation="search_vectors", status="error").inc()
            logger.error(f"Error searching vectors: {e}", exc_info=True)
            return []

    def delete_vector(self, log_id: UUID) -> bool:
        """Delete a vector from Qdrant.

        Args:
            log_id: UUID of the log entry to delete

        Returns:
            True if deleted successfully
        """
        if not self.client:
            logger.error("Qdrant client not initialized.")
            return False

        try:
            self.client.delete(
                collection_name=self.collection_name,
                points_selector=[str(log_id)],
            )
            logger.debug(f"Deleted vector for log_id: {log_id}")
            return True
        except Exception as e:
            logger.error(f"Error deleting vector: {e}", exc_info=True)
            return False

    def get_collection_info(self) -> dict[str, Any] | None:
        """Get collection information and statistics.

        Returns:
            Dictionary with collection info or None if error
        """
        if not self.client:
            return None

        try:
            collection_info = self.client.get_collection(self.collection_name)
            return {
                "name": self.collection_name,
                "points_count": collection_info.points_count,
                "vectors_count": collection_info.points_count,  # points_count represents vectors in Qdrant
                "status": collection_info.status,
                "config": {
                    "vector_size": collection_info.config.params.vectors.size,
                    "distance": collection_info.config.params.vectors.distance,
                },
            }
        except Exception as e:
            logger.error(f"Error getting collection info: {e}", exc_info=True)
            return None

    def get_all_embeddings(
        self, limit: int | None = None, filter_conditions: Filter | None = None
    ) -> list[dict[str, Any]]:
        """Retrieve all embeddings from Qdrant for clustering.

        Args:
            limit: Optional limit on number of points to retrieve (None = all)
            filter_conditions: Optional Qdrant filter for metadata

        Returns:
            List of dictionaries with 'id', 'vector', and 'payload' for each point
        """
        if not self.client:
            logger.error("Qdrant client not initialized.")
            return []

        if not self.ensure_collection():
            return []

        start_time = time.time()
        try:
            all_points = []
            offset = None

            while True:
                # Use scroll to retrieve points in batches
                result, next_offset = self.client.scroll(
                    collection_name=self.collection_name,
                    limit=10000,  # Qdrant's max scroll limit
                    offset=offset,
                    with_payload=True,
                    with_vectors=True,
                    scroll_filter=filter_conditions,
                )

                all_points.extend(result)

                if next_offset is None or (limit and len(all_points) >= limit):
                    break

                offset = next_offset

            # Apply limit if specified
            if limit and len(all_points) > limit:
                all_points = all_points[:limit]

            duration = time.time() - start_time
            qdrant_operation_duration_seconds.labels(operation="get_all_embeddings").observe(
                duration
            )
            qdrant_operations_total.labels(operation="get_all_embeddings", status="success").inc()

            # Format results
            results = [
                {
                    "id": point.id,
                    "vector": point.vector if hasattr(point, "vector") else None,
                    "payload": point.payload or {},
                }
                for point in all_points
            ]

            logger.info(f"Retrieved {len(results)} embeddings from Qdrant")
            return results

        except Exception as e:
            duration = time.time() - start_time
            qdrant_operation_duration_seconds.labels(operation="get_all_embeddings").observe(
                duration
            )
            qdrant_operations_total.labels(operation="get_all_embeddings", status="error").inc()
            logger.error(f"Error retrieving embeddings: {e}", exc_info=True)
            return []

    def get_vector(self, log_id: UUID) -> dict[str, Any] | None:
        """Retrieve a single vector by log ID.

        Args:
            log_id: UUID of the log entry

        Returns:
            Dictionary with 'id', 'vector', and 'payload' or None if not found
        """
        if not self.client:
            logger.error("Qdrant client not initialized.")
            return None

        if not self.ensure_collection():
            return None

        try:
            result = self.client.retrieve(
                collection_name=self.collection_name,
                ids=[str(log_id)],
                with_payload=True,
                with_vectors=True,
            )

            if not result or len(result) == 0:
                return None

            point = result[0]
            return {
                "id": point.id,
                "vector": point.vector if hasattr(point, "vector") else None,
                "payload": point.payload or {},
            }
        except Exception as e:
            logger.error(f"Error retrieving vector for log_id {log_id}: {e}", exc_info=True)
            return None

    def _update_vector_store_size(self) -> None:
        """Update the vector_store_size metric."""
        try:
            collection_info = self.get_collection_info()
            if collection_info:
                vector_store_size.set(collection_info["points_count"])
        except Exception as e:
            logger.debug(f"Error updating vector store size metric: {e}")


# Global instance
qdrant_service = QdrantService()
