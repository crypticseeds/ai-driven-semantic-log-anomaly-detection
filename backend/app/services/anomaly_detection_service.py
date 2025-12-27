"""Traditional anomaly detection service using statistical methods and IsolationForest."""

import logging
from typing import Any
from uuid import UUID

import numpy as np
from sklearn.ensemble import IsolationForest
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db.postgres import AnomalyResult, LogEntry
from app.db.session import get_db
from app.services.qdrant_service import qdrant_service

logger = logging.getLogger(__name__)

# Log level weights for anomaly detection
# Higher weight = more likely to be flagged as anomaly
# INFO/DEBUG logs need much higher statistical anomaly scores to be flagged
LOG_LEVEL_ANOMALY_WEIGHTS = {
    "ERROR": 1.0,  # Errors are always worth investigating
    "WARN": 0.8,  # Warnings are often important
    "WARNING": 0.8,  # Alternative spelling
    "INFO": 0.3,  # INFO logs need very high scores to be anomalous
    "DEBUG": 0.2,  # DEBUG logs rarely indicate real anomalies
    "TRACE": 0.1,  # TRACE logs almost never indicate anomalies
}

# Threshold multiplier: INFO logs need 3x higher score to be flagged
DEFAULT_LEVEL_WEIGHT = 0.5


class AnomalyDetectionService:
    """Service for traditional anomaly detection methods.

    Supports:
    - IsolationForest (unsupervised anomaly detection)
    - Z-score (statistical outlier detection)
    - IQR (Interquartile Range) method
    """

    def __init__(self):
        """Initialize anomaly detection service."""
        self.settings = get_settings()
        self.qdrant_service = qdrant_service

    def detect_with_isolation_forest(
        self,
        contamination: float = 0.1,
        n_estimators: int = 100,
        db: Session | None = None,
    ) -> dict[str, Any]:
        """Detect anomalies using IsolationForest algorithm.

        Args:
            contamination: Expected proportion of anomalies (0.0 to 0.5)
            n_estimators: Number of trees in the forest
            db: Optional database session

        Returns:
            Dictionary with anomaly detection results
        """
        if db is None:
            db = next(get_db())

        try:
            # Get all embeddings from Qdrant
            embeddings_data = self.qdrant_service.get_all_embeddings()
            if not embeddings_data:
                logger.warning("No embeddings found for IsolationForest")
                return {"anomalies": [], "total": 0, "method": "IsolationForest"}

            # Extract vectors and log IDs
            valid_data = [
                (UUID(emb["id"]), emb["vector"])
                for emb in embeddings_data
                if emb.get("vector") is not None
            ]

            if len(valid_data) < 2:
                logger.warning("Not enough embeddings for IsolationForest (need at least 2)")
                return {"anomalies": [], "total": 0, "method": "IsolationForest"}

            log_ids, vectors = zip(*valid_data, strict=True)
            vectors_array = np.array(vectors)

            # Get log levels for all log IDs to apply level-based filtering
            log_entries = db.query(LogEntry).filter(LogEntry.id.in_(log_ids)).all()
            log_level_map = {entry.id: entry.level for entry in log_entries}

            # Train IsolationForest
            logger.info(f"Training IsolationForest on {len(vectors_array)} embeddings...")
            isolation_forest = IsolationForest(
                contamination=contamination,
                n_estimators=n_estimators,
                random_state=42,
            )
            predictions = isolation_forest.fit_predict(vectors_array)
            anomaly_scores = isolation_forest.score_samples(vectors_array)

            # Calculate score threshold for level-based filtering
            # We use the median anomaly score as a baseline
            median_score = np.median(-anomaly_scores)  # Convert to positive scale

            # Process results
            anomalies = []
            for log_id, prediction, score in zip(log_ids, predictions, anomaly_scores, strict=True):
                # Normalize score (IsolationForest returns negative scores, lower = more anomalous)
                normalized_score = -score  # Convert to positive scale

                # Get log level and apply level-based filtering
                log_level = log_level_map.get(log_id, "INFO").upper()
                level_weight = LOG_LEVEL_ANOMALY_WEIGHTS.get(log_level, DEFAULT_LEVEL_WEIGHT)

                # Determine if this is truly an anomaly based on both statistical score and log level
                # For INFO/DEBUG logs, require much higher scores to be flagged
                statistical_anomaly = prediction == -1

                # Apply level-based threshold: INFO logs need score > median * (1/weight)
                # This means INFO logs (weight=0.3) need ~3x higher score than ERROR logs
                level_adjusted_threshold = (
                    median_score / level_weight if level_weight > 0 else float("inf")
                )
                is_anomaly = statistical_anomaly and (
                    level_weight >= 0.8  # ERROR/WARN always flagged if statistical anomaly
                    or normalized_score > level_adjusted_threshold  # Others need higher scores
                )

                # Store or update anomaly result
                existing = (
                    db.query(AnomalyResult).filter(AnomalyResult.log_entry_id == log_id).first()
                )

                if existing:
                    # Update with IsolationForest results
                    existing.anomaly_score = float(normalized_score)
                    existing.is_anomaly = is_anomaly
                    existing.detection_method = "IsolationForest"
                else:
                    anomaly_result = AnomalyResult(
                        log_entry_id=log_id,
                        anomaly_score=float(normalized_score),
                        is_anomaly=is_anomaly,
                        detection_method="IsolationForest",
                    )
                    db.add(anomaly_result)

                if is_anomaly:
                    anomalies.append(
                        {
                            "log_id": str(log_id),
                            "anomaly_score": float(normalized_score),
                        }
                    )

            db.commit()
            logger.info(
                f"IsolationForest detected {len(anomalies)} anomalies out of {len(log_ids)} logs"
            )

            return {
                "anomalies": anomalies,
                "total": len(anomalies),
                "method": "IsolationForest",
                "contamination": contamination,
            }

        except Exception as e:
            logger.error(f"Error in IsolationForest detection: {e}", exc_info=True)
            if db:
                db.rollback()
            return {"anomalies": [], "total": 0, "method": "IsolationForest", "error": str(e)}
        finally:
            if db:
                db.close()

    def detect_with_zscore(
        self,
        threshold: float = 3.0,
        db: Session | None = None,
    ) -> dict[str, Any]:
        """Detect anomalies using Z-score method.

        Args:
            threshold: Z-score threshold (default 3.0 = 3 standard deviations)
            db: Optional database session

        Returns:
            Dictionary with anomaly detection results
        """
        if db is None:
            db = next(get_db())

        try:
            # Get all embeddings
            embeddings_data = self.qdrant_service.get_all_embeddings()
            if not embeddings_data:
                return {"anomalies": [], "total": 0, "method": "Z-score"}

            valid_data = [
                (UUID(emb["id"]), emb["vector"])
                for emb in embeddings_data
                if emb.get("vector") is not None
            ]

            if len(valid_data) < 2:
                return {"anomalies": [], "total": 0, "method": "Z-score"}

            log_ids, vectors = zip(*valid_data, strict=True)
            vectors_array = np.array(vectors)

            # Get log levels for all log IDs to apply level-based filtering
            log_entries = db.query(LogEntry).filter(LogEntry.id.in_(log_ids)).all()
            log_level_map = {entry.id: entry.level for entry in log_entries}

            # Calculate Z-scores for each dimension, then aggregate
            # Method: Calculate mean distance from centroid for each point
            centroid = np.mean(vectors_array, axis=0)
            distances = np.linalg.norm(vectors_array - centroid, axis=1)

            # Calculate Z-scores of distances
            mean_distance = np.mean(distances)
            std_distance = np.std(distances)

            if std_distance == 0:
                logger.warning("Zero standard deviation in distances, skipping Z-score detection")
                return {"anomalies": [], "total": 0, "method": "Z-score"}

            z_scores = np.abs((distances - mean_distance) / std_distance)

            # Find anomalies
            anomalies = []
            for log_id, z_score, distance in zip(log_ids, z_scores, distances, strict=True):
                # Get log level and apply level-based filtering
                log_level = log_level_map.get(log_id, "INFO").upper()
                level_weight = LOG_LEVEL_ANOMALY_WEIGHTS.get(log_level, DEFAULT_LEVEL_WEIGHT)

                # Apply level-adjusted threshold
                # INFO logs (weight=0.3) need ~3x higher z-score than ERROR logs
                level_adjusted_threshold = (
                    threshold / level_weight if level_weight > 0 else float("inf")
                )
                statistical_anomaly = z_score > threshold

                is_anomaly = statistical_anomaly and (
                    level_weight >= 0.8  # ERROR/WARN always flagged if statistical anomaly
                    or z_score > level_adjusted_threshold  # Others need higher scores
                )

                # Store or update anomaly result
                existing = (
                    db.query(AnomalyResult).filter(AnomalyResult.log_entry_id == log_id).first()
                )

                if existing:
                    existing.anomaly_score = float(z_score)
                    existing.is_anomaly = is_anomaly
                    existing.detection_method = "Z-score"
                else:
                    anomaly_result = AnomalyResult(
                        log_entry_id=log_id,
                        anomaly_score=float(z_score),
                        is_anomaly=is_anomaly,
                        detection_method="Z-score",
                    )
                    db.add(anomaly_result)

                if is_anomaly:
                    anomalies.append(
                        {
                            "log_id": str(log_id),
                            "anomaly_score": float(z_score),
                            "distance_from_centroid": float(distance),
                        }
                    )

            db.commit()
            logger.info(f"Z-score method detected {len(anomalies)} anomalies")

            return {
                "anomalies": anomalies,
                "total": len(anomalies),
                "method": "Z-score",
                "threshold": threshold,
            }

        except Exception as e:
            logger.error(f"Error in Z-score detection: {e}", exc_info=True)
            if db:
                db.rollback()
            return {"anomalies": [], "total": 0, "method": "Z-score", "error": str(e)}
        finally:
            if db:
                db.close()

    def detect_with_iqr(
        self,
        multiplier: float = 1.5,
        db: Session | None = None,
    ) -> dict[str, Any]:
        """Detect anomalies using Interquartile Range (IQR) method.

        Args:
            multiplier: IQR multiplier (default 1.5)
            db: Optional database session

        Returns:
            Dictionary with anomaly detection results
        """
        if db is None:
            db = next(get_db())

        try:
            # Get all embeddings
            embeddings_data = self.qdrant_service.get_all_embeddings()
            if not embeddings_data:
                return {"anomalies": [], "total": 0, "method": "IQR"}

            valid_data = [
                (UUID(emb["id"]), emb["vector"])
                for emb in embeddings_data
                if emb.get("vector") is not None
            ]

            if len(valid_data) < 4:  # Need at least 4 points for quartiles
                return {"anomalies": [], "total": 0, "method": "IQR"}

            log_ids, vectors = zip(*valid_data, strict=True)
            vectors_array = np.array(vectors)

            # Get log levels for all log IDs to apply level-based filtering
            log_entries = db.query(LogEntry).filter(LogEntry.id.in_(log_ids)).all()
            log_level_map = {entry.id: entry.level for entry in log_entries}

            # Calculate distances from centroid
            centroid = np.mean(vectors_array, axis=0)
            distances = np.linalg.norm(vectors_array - centroid, axis=1)

            # Calculate quartiles
            q1 = np.percentile(distances, 25)
            q3 = np.percentile(distances, 75)
            iqr = q3 - q1

            if iqr == 0:
                logger.warning("Zero IQR, skipping IQR detection")
                return {"anomalies": [], "total": 0, "method": "IQR"}

            # Define bounds
            lower_bound = q1 - multiplier * iqr
            upper_bound = q3 + multiplier * iqr

            # Find anomalies (points outside bounds)
            anomalies = []
            for log_id, distance in zip(log_ids, distances, strict=True):
                statistical_anomaly = distance < lower_bound or distance > upper_bound

                # Calculate anomaly score (distance from nearest bound)
                if distance < lower_bound:
                    score = (lower_bound - distance) / iqr if iqr > 0 else 0
                elif distance > upper_bound:
                    score = (distance - upper_bound) / iqr if iqr > 0 else 0
                else:
                    score = 0.0

                # Get log level and apply level-based filtering
                log_level = log_level_map.get(log_id, "INFO").upper()
                level_weight = LOG_LEVEL_ANOMALY_WEIGHTS.get(log_level, DEFAULT_LEVEL_WEIGHT)

                # Apply level-adjusted threshold for IQR score
                # INFO logs need higher IQR scores to be flagged
                level_adjusted_score_threshold = (
                    1.0 / level_weight if level_weight > 0 else float("inf")
                )

                is_anomaly = statistical_anomaly and (
                    level_weight >= 0.8  # ERROR/WARN always flagged if statistical anomaly
                    or score > level_adjusted_score_threshold  # Others need higher scores
                )

                # Store or update anomaly result
                existing = (
                    db.query(AnomalyResult).filter(AnomalyResult.log_entry_id == log_id).first()
                )

                if existing:
                    existing.anomaly_score = float(score)
                    existing.is_anomaly = is_anomaly
                    existing.detection_method = "IQR"
                else:
                    anomaly_result = AnomalyResult(
                        log_entry_id=log_id,
                        anomaly_score=float(score),
                        is_anomaly=is_anomaly,
                        detection_method="IQR",
                    )
                    db.add(anomaly_result)

                if is_anomaly:
                    anomalies.append(
                        {
                            "log_id": str(log_id),
                            "anomaly_score": float(score),
                            "distance_from_centroid": float(distance),
                        }
                    )

            db.commit()
            logger.info(f"IQR method detected {len(anomalies)} anomalies")

            return {
                "anomalies": anomalies,
                "total": len(anomalies),
                "method": "IQR",
                "multiplier": multiplier,
            }

        except Exception as e:
            logger.error(f"Error in IQR detection: {e}", exc_info=True)
            if db:
                db.rollback()
            return {"anomalies": [], "total": 0, "method": "IQR", "error": str(e)}
        finally:
            if db:
                db.close()

    def score_log_entry(
        self,
        log_id: UUID,
        method: str = "IsolationForest",
        db: Session | None = None,
    ) -> dict[str, Any] | None:
        """Score a single log entry for anomaly detection (real-time scoring).

        Args:
            log_id: UUID of the log entry
            method: Detection method to use (IsolationForest, Z-score, IQR)
            db: Optional database session

        Returns:
            Dictionary with anomaly score and is_anomaly flag, or None if error
        """
        # Track if we created the session ourselves
        created_session = False
        if db is None:
            db = next(get_db())
            created_session = True

        try:
            # Get embedding for this log
            embedding_data = self.qdrant_service.get_vector(log_id)
            if not embedding_data or not embedding_data.get("vector"):
                logger.warning(f"No embedding found for log_id: {log_id}")
                return None

            vector = np.array(embedding_data["vector"])

            # Get log level for this entry
            log_entry = db.query(LogEntry).filter(LogEntry.id == log_id).first()
            if not log_entry:
                logger.warning(f"Log entry not found for log_id: {log_id}")
                return None

            log_level = log_entry.level.upper() if log_entry.level else "INFO"
            level_weight = LOG_LEVEL_ANOMALY_WEIGHTS.get(log_level, DEFAULT_LEVEL_WEIGHT)

            # Get all other embeddings for comparison (for statistical methods)
            all_embeddings_data = self.qdrant_service.get_all_embeddings()
            if not all_embeddings_data or len(all_embeddings_data) < 2:
                logger.warning("Not enough embeddings for real-time scoring")
                return None

            all_vectors = np.array(
                [emb["vector"] for emb in all_embeddings_data if emb.get("vector")]
            )

            statistical_anomaly = False
            normalized_score = 0.0

            if method == "IsolationForest":
                # Train on all data including this point
                isolation_forest = IsolationForest(contamination=0.1, random_state=42)
                all_vectors_with_new = np.vstack([all_vectors, vector.reshape(1, -1)])
                predictions = isolation_forest.fit_predict(all_vectors_with_new)
                score = isolation_forest.score_samples(vector.reshape(1, -1))[0]
                statistical_anomaly = bool(predictions[-1] == -1)
                normalized_score = -score

                # Calculate median score for level-based threshold
                all_scores = -isolation_forest.score_samples(all_vectors)
                median_score = float(np.median(all_scores))
                level_adjusted_threshold = (
                    median_score / level_weight if level_weight > 0 else float("inf")
                )

                is_anomaly = statistical_anomaly and (
                    level_weight >= 0.8 or normalized_score > level_adjusted_threshold
                )

            elif method == "Z-score":
                centroid = np.mean(all_vectors, axis=0)
                distance = np.linalg.norm(vector - centroid)
                mean_distance = np.mean(np.linalg.norm(all_vectors - centroid, axis=1))
                std_distance = np.std(np.linalg.norm(all_vectors - centroid, axis=1))
                if std_distance == 0:
                    return None
                z_score = abs((distance - mean_distance) / std_distance)
                normalized_score = z_score
                threshold = 3.0
                statistical_anomaly = bool(z_score > threshold)

                level_adjusted_threshold = (
                    threshold / level_weight if level_weight > 0 else float("inf")
                )
                is_anomaly = statistical_anomaly and (
                    level_weight >= 0.8 or z_score > level_adjusted_threshold
                )

            elif method == "IQR":
                centroid = np.mean(all_vectors, axis=0)
                distances = np.linalg.norm(all_vectors - centroid, axis=1)
                distance = np.linalg.norm(vector - centroid)
                q1 = np.percentile(distances, 25)
                q3 = np.percentile(distances, 75)
                iqr = q3 - q1
                if iqr == 0:
                    return None
                lower_bound = q1 - 1.5 * iqr
                upper_bound = q3 + 1.5 * iqr
                statistical_anomaly = bool(distance < lower_bound or distance > upper_bound)
                if distance < lower_bound:
                    normalized_score = (lower_bound - distance) / iqr
                elif distance > upper_bound:
                    normalized_score = (distance - upper_bound) / iqr
                else:
                    normalized_score = 0.0

                level_adjusted_score_threshold = (
                    1.0 / level_weight if level_weight > 0 else float("inf")
                )
                is_anomaly = statistical_anomaly and (
                    level_weight >= 0.8 or normalized_score > level_adjusted_score_threshold
                )

            else:
                logger.error(f"Unknown detection method: {method}")
                return None

            # Store result
            existing = db.query(AnomalyResult).filter(AnomalyResult.log_entry_id == log_id).first()

            if existing:
                existing.anomaly_score = float(normalized_score)
                existing.is_anomaly = is_anomaly
                existing.detection_method = method
            else:
                anomaly_result = AnomalyResult(
                    log_entry_id=log_id,
                    anomaly_score=float(normalized_score),
                    is_anomaly=is_anomaly,
                    detection_method=method,
                )
                db.add(anomaly_result)

            db.commit()

            return {
                "log_id": str(log_id),
                "anomaly_score": float(normalized_score),
                "is_anomaly": is_anomaly,
                "method": method,
            }

        except Exception as e:
            logger.error(f"Error in real-time scoring: {e}", exc_info=True)
            if db:
                db.rollback()
            return None
        finally:
            # Only close the session if we created it ourselves
            # If it was passed from FastAPI dependency injection, let FastAPI manage it
            if created_session and db:
                db.close()


# Global instance
anomaly_detection_service = AnomalyDetectionService()
