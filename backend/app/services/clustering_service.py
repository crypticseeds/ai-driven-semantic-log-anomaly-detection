"""HDBSCAN clustering service for log embeddings."""

import logging
import random
from typing import Any
from uuid import UUID

import numpy as np
from hdbscan import HDBSCAN
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db.postgres import AnomalyResult, ClusteringMetadata, LogEntry
from app.db.session import get_db
from app.services.llm_reasoning_service import llm_reasoning_service
from app.services.qdrant_service import qdrant_service

logger = logging.getLogger(__name__)


class ClusteringService:
    """Service for HDBSCAN clustering of log embeddings."""

    def __init__(self):
        """Initialize clustering service."""
        self.settings = get_settings()
        self.qdrant_service = qdrant_service

    def perform_clustering(
        self,
        sample_size: int | None = None,
        min_cluster_size: int | None = None,
        min_samples: int | None = None,
        skip_llm: bool = True,
        max_llm_outliers: int = 5,
        db: Session | None = None,
    ) -> dict[str, Any]:
        """Perform HDBSCAN clustering on log embeddings.

        Args:
            sample_size: Optional sample size for large datasets (None = use all)
            min_cluster_size: Override default min_cluster_size from config
            min_samples: Override default min_samples from config
            skip_llm: Skip LLM analysis for faster clustering (default: True)
            max_llm_outliers: Max outliers to analyze with LLM (default: 5)
            db: Optional database session

        Returns:
            Dictionary with clustering results including:
            - n_clusters: Number of clusters found
            - n_outliers: Number of outliers (cluster_id = -1)
            - cluster_assignments: Dict mapping log_id to cluster_id
            - cluster_metadata: Dict with cluster statistics
        """
        # Track if we created the session ourselves
        created_session = False
        if db is None:
            db = next(get_db())
            created_session = True

        try:
            # Get configuration
            min_cluster_size = min_cluster_size or self.settings.hdbscan_min_cluster_size
            min_samples = min_samples or self.settings.hdbscan_min_samples
            sample_size = sample_size or self.settings.hdbscan_sample_size

            logger.info(
                f"Starting HDBSCAN clustering with min_cluster_size={min_cluster_size}, "
                f"min_samples={min_samples}, sample_size={sample_size}"
            )

            # Extract embeddings from Qdrant
            logger.info("Extracting embeddings from Qdrant...")
            embeddings_data = self.qdrant_service.get_all_embeddings(limit=sample_size)

            if not embeddings_data:
                logger.warning("No embeddings found in Qdrant")
                return {
                    "n_clusters": 0,
                    "n_outliers": 0,
                    "cluster_assignments": {},
                    "cluster_metadata": {},
                    "error": "No embeddings found",
                }

            # Filter out points without vectors
            valid_embeddings = [
                (UUID(emb["id"]), emb["vector"])
                for emb in embeddings_data
                if emb.get("vector") is not None
            ]

            if not valid_embeddings:
                logger.warning("No valid embeddings found")
                return {
                    "n_clusters": 0,
                    "n_outliers": 0,
                    "cluster_assignments": {},
                    "cluster_metadata": {},
                    "error": "No valid embeddings found",
                }

            log_ids, vectors = zip(*valid_embeddings, strict=True)
            log_ids = list(log_ids)
            vectors_array = np.array(vectors)

            logger.info(f"Clustering {len(vectors_array)} embeddings...")

            # Performance optimization: aggressive sampling for memory-constrained environments
            # HDBSCAN memory usage scales with O(n²) for distance matrix
            max_clustering_size = self.settings.clustering_max_embeddings

            if sample_size and len(vectors_array) > sample_size:
                logger.info(f"Sampling {sample_size} embeddings from {len(vectors_array)} total")
                indices = random.sample(
                    range(len(vectors_array)), min(sample_size, len(vectors_array))
                )
                vectors_array = vectors_array[indices]
                log_ids = [log_ids[i] for i in indices]

            if len(vectors_array) > max_clustering_size:
                logger.warning(
                    f"Dataset size ({len(vectors_array)}) exceeds memory-safe limit ({max_clustering_size}). "
                    f"Sampling {max_clustering_size} embeddings to prevent OOM."
                )
                indices = random.sample(range(len(vectors_array)), max_clustering_size)
                vectors_array = vectors_array[indices]
                log_ids = [log_ids[i] for i in indices]

            # Convert to float32 to reduce memory usage (float64 is default)
            if self.settings.clustering_use_float32:
                vectors_array = vectors_array.astype(np.float32)

            # Configure and run HDBSCAN with memory-optimized settings
            hdbscan_params = {
                "min_cluster_size": min_cluster_size,
                "min_samples": min_samples,
                "cluster_selection_epsilon": self.settings.hdbscan_cluster_selection_epsilon,
                "metric": "euclidean",
                "cluster_selection_method": "eom",
                "algorithm": "boruvka_kdtree",  # More memory efficient than "best"
                "leaf_size": 50,  # Larger leaf size = less memory
                "core_dist_n_jobs": 1,  # Single thread to limit memory
            }
            # Only add max_cluster_size if it's not None (HDBSCAN handles None as default)
            if self.settings.hdbscan_max_cluster_size is not None:
                hdbscan_params["max_cluster_size"] = self.settings.hdbscan_max_cluster_size

            logger.info(f"Running HDBSCAN with parameters: {hdbscan_params}")
            logger.info(f"Dataset shape: {vectors_array.shape}, dtype: {vectors_array.dtype}")
            clusterer = HDBSCAN(**hdbscan_params)

            cluster_labels = clusterer.fit_predict(vectors_array)

            # Process results - ensure cluster_id is Python int, not numpy.int64
            cluster_assignments = {
                str(log_id): int(cluster_id.item())
                if hasattr(cluster_id, "item")
                else int(cluster_id)
                for log_id, cluster_id in zip(log_ids, cluster_labels, strict=True)
            }

            # Count clusters and outliers
            unique_clusters = set(cluster_labels)
            n_clusters = len(unique_clusters) - (1 if -1 in unique_clusters else 0)
            n_outliers = int(np.sum(cluster_labels == -1))

            logger.info(
                f"Clustering complete: {n_clusters} clusters, {n_outliers} outliers "
                f"({n_outliers / len(cluster_labels) * 100:.1f}%)"
            )

            # Store cluster assignments in database
            self._store_cluster_assignments(cluster_assignments, db)

            # Generate LLM reasoning for outliers (optional, can be slow)
            if not skip_llm and max_llm_outliers > 0:
                self._analyze_outliers_with_llm(
                    cluster_assignments, db, max_outliers=max_llm_outliers
                )
            else:
                logger.info(
                    f"Skipping LLM analysis (skip_llm={skip_llm}, max_llm_outliers={max_llm_outliers})"
                )

            # Calculate cluster metadata
            cluster_metadata = self._calculate_cluster_metadata(
                cluster_labels, log_ids, vectors_array, db
            )

            return {
                "n_clusters": n_clusters,
                "n_outliers": n_outliers,
                "cluster_assignments": cluster_assignments,
                "cluster_metadata": cluster_metadata,
            }

        except Exception as e:
            logger.error(f"Error performing clustering: {e}", exc_info=True)
            if db:
                db.rollback()
            return {
                "n_clusters": 0,
                "n_outliers": 0,
                "cluster_assignments": {},
                "cluster_metadata": {},
                "error": str(e),
            }
        finally:
            # Only close the session if we created it ourselves
            # If it was passed from FastAPI dependency injection, let FastAPI manage it
            if created_session and db:
                db.close()

    def _store_cluster_assignments(self, cluster_assignments: dict[str, int], db: Session) -> None:
        """Store cluster assignments in AnomalyResult table.

        Args:
            cluster_assignments: Dict mapping log_id (str) to cluster_id (int)
            db: Database session
        """
        try:
            stored_count = 0
            for log_id_str, cluster_id in cluster_assignments.items():
                try:
                    log_id = UUID(log_id_str)

                    # Check if AnomalyResult already exists for this log
                    existing = (
                        db.query(AnomalyResult).filter(AnomalyResult.log_entry_id == log_id).first()
                    )

                    if existing:
                        # Update existing record
                        existing.cluster_id = cluster_id
                        existing.detection_method = "HDBSCAN"
                    else:
                        # Create new record
                        anomaly_result = AnomalyResult(
                            log_entry_id=log_id,
                            cluster_id=cluster_id,
                            detection_method="HDBSCAN",
                            anomaly_score=0.0,  # Will be calculated separately if needed
                            is_anomaly=(cluster_id == -1),  # Outliers are anomalies
                        )
                        db.add(anomaly_result)

                    stored_count += 1
                except ValueError:
                    logger.warning(f"Invalid UUID format: {log_id_str}")
                    continue

            db.commit()
            logger.info(f"Stored {stored_count} cluster assignments in database")

        except Exception as e:
            logger.error(f"Error storing cluster assignments: {e}", exc_info=True)
            db.rollback()
            raise

    def _analyze_outliers_with_llm(
        self, cluster_assignments: dict[str, int], db: Session, max_outliers: int = 5
    ) -> None:
        """Generate LLM reasoning for outlier log entries.

        Args:
            cluster_assignments: Dict mapping log_id (str) to cluster_id (int)
            db: Database session
            max_outliers: Maximum number of outliers to analyze (default: 5)
        """
        try:
            # Get all outliers (cluster_id = -1)
            outlier_log_ids = [
                UUID(log_id_str)
                for log_id_str, cluster_id in cluster_assignments.items()
                if cluster_id == -1
            ]

            if not outlier_log_ids:
                logger.info("No outliers to analyze with LLM")
                return

            # Limit outliers to analyze
            outliers_to_analyze = outlier_log_ids[:max_outliers]
            logger.info(
                f"Analyzing {len(outliers_to_analyze)} outliers with LLM (of {len(outlier_log_ids)} total)..."
            )

            # Get log entries for outliers
            log_entries = db.query(LogEntry).filter(LogEntry.id.in_(outlier_log_ids)).all()
            log_dict = {log.id: log for log in log_entries}

            # Get cluster information for richer context
            # Find the largest cluster to use as reference for comparison
            cluster_sizes = {}
            for _log_id_str, cluster_id in cluster_assignments.items():
                if cluster_id != -1:
                    cluster_sizes[cluster_id] = cluster_sizes.get(cluster_id, 0) + 1

            largest_cluster_id = None
            if cluster_sizes:
                largest_cluster_id = max(cluster_sizes.items(), key=lambda x: x[1])[0]

            # Get cluster info for the largest cluster (if available)
            cluster_info = None
            if largest_cluster_id is not None:
                try:
                    cluster_info = self.get_cluster_info(largest_cluster_id, db)
                except Exception as e:
                    logger.warning(
                        f"Failed to get cluster info for cluster {largest_cluster_id}: {e}"
                    )

            # Get some normal logs for context (from clusters)
            normal_log_ids = [
                UUID(log_id_str)
                for log_id_str, cluster_id in cluster_assignments.items()
                if cluster_id != -1
            ][:10]  # Sample 10 normal logs for context
            normal_logs = db.query(LogEntry).filter(LogEntry.id.in_(normal_log_ids)).all()

            # Prepare context logs
            context_logs = [
                {
                    "level": log.level,
                    "service": log.service,
                    "message": log.message,
                }
                for log in normal_logs
            ]

            # Validate each outlier with LLM (Tier 2 validation)
            settings = get_settings()
            validated_count = 0
            confirmed_count = 0

            for log_id in outliers_to_analyze:  # Use limited list
                log_entry = log_dict.get(log_id)
                if not log_entry:
                    continue

                # Try enhanced root cause analysis with cluster context if available
                root_cause_result = None
                if cluster_info:
                    try:
                        root_cause_result = llm_reasoning_service.analyze_anomaly_with_root_cause(
                            log_message=log_entry.message,
                            log_level=log_entry.level,
                            log_service=log_entry.service,
                            context_logs=context_logs,
                            cluster_info=cluster_info,
                        )
                        if root_cause_result:
                            # Format root cause result as reasoning string
                            reasoning_parts = [root_cause_result.get("explanation", "")]
                            if root_cause_result.get("root_causes"):
                                reasoning_parts.append("\n\nRoot Causes:")
                                for rc in root_cause_result["root_causes"]:
                                    reasoning_parts.append(
                                        f"- {rc.get('hypothesis', 'Unknown')}: {rc.get('description', '')}"
                                    )
                            if root_cause_result.get("remediation_steps"):
                                reasoning_parts.append("\n\nRemediation Steps:")
                                for step in root_cause_result["remediation_steps"]:
                                    reasoning_parts.append(
                                        f"- [{step.get('priority', 'MEDIUM')}] {step.get('step', 'Unknown')}: {step.get('description', '')}"
                                    )
                            reasoning_parts.append(
                                f"\n\nSeverity: {root_cause_result.get('severity', 'MEDIUM')} - {root_cause_result.get('severity_reason', '')}"
                            )
                    except Exception as e:
                        logger.warning(
                            f"Root cause analysis failed, falling back to standard detection: {e}"
                        )

                # Run LLM detection (validation) and ensure explanation is always generated
                llm_result = llm_reasoning_service.detect_anomaly(
                    log_message=log_entry.message,
                    log_level=log_entry.level,
                    log_service=log_entry.service,
                    context_logs=context_logs,
                )

                # Get or create anomaly result
                anomaly_result = (
                    db.query(AnomalyResult).filter(AnomalyResult.log_entry_id == log_id).first()
                )

                if anomaly_result:
                    if root_cause_result:
                        # Use enhanced root cause analysis if available
                        reasoning_parts = [root_cause_result.get("explanation", "")]
                        if root_cause_result.get("root_causes"):
                            reasoning_parts.append("\n\nRoot Causes:")
                            for rc in root_cause_result["root_causes"]:
                                reasoning_parts.append(
                                    f"- {rc.get('hypothesis', 'Unknown')}: {rc.get('description', '')}"
                                )
                        if root_cause_result.get("remediation_steps"):
                            reasoning_parts.append("\n\nRemediation Steps:")
                            for step in root_cause_result["remediation_steps"]:
                                reasoning_parts.append(
                                    f"- [{step.get('priority', 'MEDIUM')}] {step.get('step', 'Unknown')}: {step.get('description', '')}"
                                )
                        reasoning_parts.append(
                            f"\n\nSeverity: {root_cause_result.get('severity', 'MEDIUM')} - {root_cause_result.get('severity_reason', '')}"
                        )
                        enhanced_reasoning = "\n".join(reasoning_parts)
                        anomaly_result.llm_reasoning = enhanced_reasoning
                        validated_count += 1
                    elif llm_result:
                        # LLM detection succeeded - use its results
                        llm_is_anomaly = llm_result["is_anomaly"]
                        llm_confidence = llm_result["confidence"]
                        llm_reasoning = llm_result["reasoning"]

                        # Store LLM validation results
                        anomaly_result.llm_reasoning = llm_reasoning
                        validated_count += 1

                        # Check if LLM confirms the anomaly
                        if (
                            llm_is_anomaly
                            and llm_confidence >= settings.llm_validation_confidence_threshold
                        ):
                            confirmed_count += 1
                            logger.debug(
                                f"LLM confirmed HDBSCAN outlier for log_id: {log_id} "
                                f"(confidence: {llm_confidence:.2f})"
                            )
                        else:
                            logger.debug(
                                f"LLM did not confirm HDBSCAN outlier for log_id: {log_id} "
                                f"(may be false positive)"
                            )
                    else:
                        # LLM detection failed - fallback to explanation-only
                        # This ensures explanations are ALWAYS generated for anomalies
                        logger.warning(
                            f"LLM detection failed for log_id: {log_id}, "
                            f"falling back to explanation-only mode"
                        )
                        explanation = llm_reasoning_service.analyze_anomaly(
                            log_message=log_entry.message,
                            log_level=log_entry.level,
                            log_service=log_entry.service,
                            context_logs=context_logs,
                        )

                        if explanation:
                            # Store explanation even if detection failed
                            anomaly_result.llm_reasoning = explanation
                            logger.debug(
                                f"Generated LLM explanation for log_id: {log_id} "
                                f"(detection failed, explanation-only)"
                            )

            db.commit()
            logger.info(
                f"LLM validation completed: {validated_count} outliers validated, "
                f"{confirmed_count} confirmed as anomalies"
            )

        except Exception as e:
            logger.error(f"Error analyzing outliers with LLM: {e}", exc_info=True)
            db.rollback()

    def _calculate_cluster_metadata(
        self,
        cluster_labels: np.ndarray,
        log_ids: list[UUID],
        vectors: np.ndarray,
        db: Session,
    ) -> dict[int, dict[str, Any]]:
        """Calculate and store metadata for each cluster.

        Args:
            cluster_labels: Array of cluster labels
            log_ids: List of log IDs corresponding to labels
            vectors: Array of embedding vectors
            db: Database session

        Returns:
            Dictionary mapping cluster_id to metadata
        """
        try:
            cluster_metadata = {}
            unique_clusters = set(cluster_labels)

            for cluster_id in unique_clusters:
                if cluster_id == -1:
                    continue  # Skip outliers

                # Convert numpy types to Python native types immediately
                cluster_id_int = (
                    int(cluster_id.item()) if hasattr(cluster_id, "item") else int(cluster_id)
                )

                # Get indices for this cluster
                cluster_indices = np.where(cluster_labels == cluster_id)[0]
                cluster_vectors = vectors[cluster_indices]
                cluster_log_ids = [log_ids[i] for i in cluster_indices]

                # Calculate centroid
                centroid = np.mean(cluster_vectors, axis=0).tolist()

                # Get representative logs (sample of log IDs)
                representative_logs = [
                    str(log_id) for log_id in cluster_log_ids[:10]
                ]  # First 10 as representatives

                metadata = {
                    "cluster_id": cluster_id_int,
                    "cluster_size": len(cluster_indices),
                    "centroid": centroid,
                    "representative_logs": representative_logs,
                }

                cluster_metadata[cluster_id_int] = metadata

                # Store in database - ensure cluster_id is Python int
                existing = (
                    db.query(ClusteringMetadata)
                    .filter(ClusteringMetadata.cluster_id == cluster_id_int)
                    .first()
                )

                if existing:
                    existing.cluster_size = metadata["cluster_size"]
                    existing.cluster_centroid = metadata["centroid"]
                    existing.representative_logs = metadata["representative_logs"]
                else:
                    clustering_metadata = ClusteringMetadata(
                        cluster_id=cluster_id_int,
                        cluster_size=metadata["cluster_size"],
                        cluster_centroid=metadata["centroid"],
                        representative_logs=metadata["representative_logs"],
                    )
                    db.add(clustering_metadata)

            db.commit()
            logger.info(f"Stored metadata for {len(cluster_metadata)} clusters")

            return cluster_metadata

        except Exception as e:
            logger.error(f"Error calculating cluster metadata: {e}", exc_info=True)
            db.rollback()
            return {}

    def get_cluster_info(self, cluster_id: int, db: Session | None = None) -> dict[str, Any] | None:
        """Get information about a specific cluster.

        Args:
            cluster_id: Cluster ID to query
            db: Optional database session

        Returns:
            Dictionary with cluster information or None if not found
        """
        if db is None:
            db = next(get_db())

        try:
            metadata = (
                db.query(ClusteringMetadata)
                .filter(ClusteringMetadata.cluster_id == cluster_id)
                .first()
            )

            if not metadata:
                return None

            # Get log entries in this cluster
            anomaly_results = (
                db.query(AnomalyResult).filter(AnomalyResult.cluster_id == cluster_id).all()
            )

            log_entries = (
                db.query(LogEntry)
                .filter(LogEntry.id.in_([ar.log_entry_id for ar in anomaly_results]))
                .limit(100)
                .all()
            )

            return {
                "cluster_id": metadata.cluster_id,
                "cluster_size": metadata.cluster_size,
                "centroid": metadata.cluster_centroid,
                "representative_logs": metadata.representative_logs,
                "sample_logs": [
                    {
                        "id": str(log.id),
                        "message": log.message,
                        "level": log.level,
                        "service": log.service,
                        "timestamp": log.timestamp.isoformat(),
                    }
                    for log in log_entries
                ],
            }

        except Exception as e:
            logger.error(f"Error getting cluster info: {e}", exc_info=True)
            return None
        finally:
            if db:
                db.close()

    def get_cluster_info_by_log_id(
        self, log_id: UUID, db: Session | None = None
    ) -> dict[str, Any] | None:
        """Get cluster information for a specific log entry.

        Args:
            log_id: UUID of the log entry
            db: Optional database session

        Returns:
            Dictionary with cluster information or None if log not found or not in a cluster
        """
        # Track if we created the session ourselves
        created_session = False
        if db is None:
            db = next(get_db())
            created_session = True

        try:
            # Get the anomaly result for this log to find its cluster_id
            anomaly_result = (
                db.query(AnomalyResult).filter(AnomalyResult.log_entry_id == log_id).first()
            )

            if not anomaly_result or anomaly_result.cluster_id is None:
                return None

            # If it's an outlier (cluster_id = -1), return special response
            if anomaly_result.cluster_id == -1:
                return {
                    "cluster_id": -1,
                    "cluster_size": 0,
                    "is_outlier": True,
                    "message": "This log is an outlier and does not belong to any cluster",
                }

            # Get cluster metadata using the same session
            cluster_id = anomaly_result.cluster_id
            metadata = (
                db.query(ClusteringMetadata)
                .filter(ClusteringMetadata.cluster_id == cluster_id)
                .first()
            )

            if not metadata:
                return None

            # Get log entries in this cluster
            anomaly_results = (
                db.query(AnomalyResult).filter(AnomalyResult.cluster_id == cluster_id).all()
            )

            log_entries = (
                db.query(LogEntry)
                .filter(LogEntry.id.in_([ar.log_entry_id for ar in anomaly_results]))
                .limit(100)
                .all()
            )

            return {
                "cluster_id": metadata.cluster_id,
                "cluster_size": metadata.cluster_size,
                "centroid": metadata.cluster_centroid,
                "representative_logs": metadata.representative_logs,
                "sample_logs": [
                    {
                        "id": str(log.id),
                        "message": log.message,
                        "level": log.level,
                        "service": log.service,
                        "timestamp": log.timestamp.isoformat(),
                    }
                    for log in log_entries
                ],
            }

        except Exception as e:
            logger.error(f"Error getting cluster info by log_id: {e}", exc_info=True)
            return None
        finally:
            # Only close the session if we created it ourselves
            if created_session and db:
                db.close()


# Global instance
clustering_service = ClusteringService()
