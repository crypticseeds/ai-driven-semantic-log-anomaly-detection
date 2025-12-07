"""Storage service for saving processed log entries to PostgreSQL and Qdrant."""

import logging
from uuid import UUID

from sqlalchemy.orm import Session

from app.config import get_settings
from app.db.postgres import AnomalyResult, LogEntry
from app.db.session import get_db
from app.models.log import ProcessedLogEntry
from app.services.anomaly_detection_service import anomaly_detection_service
from app.services.embedding_service import BudgetExceededError, embedding_service
from app.services.llm_reasoning_service import llm_reasoning_service
from app.services.qdrant_service import qdrant_service

logger = logging.getLogger(__name__)


class StorageService:
    """Service for storing processed log entries in PostgreSQL."""

    def save_log_entry(
        self, processed_log: ProcessedLogEntry, db: Session | None = None
    ) -> UUID | None:
        """Save processed log entry to database."""
        try:
            if db is None:
                db = next(get_db())

            log_entry = LogEntry(
                timestamp=processed_log.timestamp,
                level=processed_log.level,
                service=processed_log.service,
                message=processed_log.message,
                raw_log=processed_log.raw_log,
                log_metadata=processed_log.metadata,  # Renamed from 'metadata' to 'log_metadata'
                pii_redacted=processed_log.pii_redacted,
            )

            db.add(log_entry)
            db.commit()
            db.refresh(log_entry)

            logger.debug(f"Saved log entry with ID: {log_entry.id}")

            # Store vector embedding in Qdrant
            self._store_vector_embedding(log_entry.id, processed_log)

            return log_entry.id
        except Exception as e:
            logger.error(f"Failed to save log entry: {e}")
            if db:
                db.rollback()
            return None

    def save_log_entry_async(self, processed_log: ProcessedLogEntry) -> UUID | None:
        """Save processed log entry asynchronously (creates new session)."""
        db = next(get_db())
        try:
            return self.save_log_entry(processed_log, db)
        finally:
            db.close()

    def _store_vector_embedding(self, log_id: UUID, processed_log: ProcessedLogEntry) -> None:
        """Store vector embedding in Qdrant with metadata.

        Args:
            log_id: UUID of the log entry
            processed_log: Processed log entry
        """
        try:
            # Generate embedding from the message (with caching enabled)
            embedding_result = embedding_service.generate_embedding(
                processed_log.message, use_cache=True
            )
            if not embedding_result or not embedding_result.get("embedding"):
                logger.warning(f"Failed to generate embedding for log_id: {log_id}")
                return

            embedding = embedding_result["embedding"]

            # Prepare payload with metadata for filtering and embedding metadata
            payload = {
                "level": processed_log.level,
                "service": processed_log.service,
                "timestamp": processed_log.timestamp.isoformat(),
                "pii_redacted": processed_log.pii_redacted,
                # Embedding metadata
                "embedding_model": embedding_result.get("model"),
                "embedding_timestamp": embedding_result.get("timestamp").isoformat()
                if embedding_result.get("timestamp")
                else None,
                "embedding_cost_usd": embedding_result.get("cost_usd", 0.0),
                "embedding_tokens": embedding_result.get("tokens", 0),
                "embedding_cached": embedding_result.get("cached", False),
            }

            # Store in Qdrant
            success = qdrant_service.store_vector(log_id, embedding, payload)
            if success:
                logger.debug(
                    f"Stored vector embedding for log_id: {log_id} "
                    f"(cached: {embedding_result.get('cached', False)})"
                )

                # Real-time scoring pipeline: Hybrid/Tiered Detection
                # Tier 1: Fast statistical method (IsolationForest)
                # Tier 2: LLM validation for high-scoring anomalies
                try:
                    db = next(get_db())
                    try:
                        settings = get_settings()

                        # Tier 1: Run IsolationForest
                        tier1_result = anomaly_detection_service.score_log_entry(
                            log_id=log_id, method="IsolationForest", db=db
                        )

                        if tier1_result:
                            tier1_score = tier1_result.get("anomaly_score", 0.0)
                            tier1_is_anomaly = tier1_result.get("is_anomaly", False)

                            logger.debug(
                                f"Tier 1 (IsolationForest) completed for log_id: {log_id}, "
                                f"score: {tier1_score:.3f}, is_anomaly: {tier1_is_anomaly}"
                            )

                            # Tier 2: LLM validation if score exceeds threshold and flagged as anomaly
                            if (
                                settings.llm_validation_enabled
                                and tier1_is_anomaly
                                and tier1_score >= settings.anomaly_score_threshold
                            ):
                                # Get log entry for LLM context
                                log_entry = db.query(LogEntry).filter(LogEntry.id == log_id).first()
                                if log_entry:
                                    # Get some context logs
                                    context_logs = (
                                        db.query(LogEntry)
                                        .filter(LogEntry.id != log_id)
                                        .order_by(LogEntry.timestamp.desc())
                                        .limit(5)
                                        .all()
                                    )

                                    context = [
                                        {
                                            "level": log.level,
                                            "service": log.service,
                                            "message": log.message,
                                        }
                                        for log in context_logs
                                    ]

                                    # Run LLM validation
                                    llm_result = llm_reasoning_service.detect_anomaly(
                                        log_message=log_entry.message,
                                        log_level=log_entry.level,
                                        log_service=log_entry.service,
                                        context_logs=context,
                                    )

                                    # Get anomaly result
                                    anomaly_result = (
                                        db.query(AnomalyResult)
                                        .filter(AnomalyResult.log_entry_id == log_id)
                                        .first()
                                    )

                                    if anomaly_result:
                                        if llm_result:
                                            # LLM detection succeeded - use its results
                                            llm_is_anomaly = llm_result["is_anomaly"]
                                            llm_confidence = llm_result["confidence"]
                                            llm_reasoning = llm_result["reasoning"]

                                            # Store LLM validation results (includes reasoning)
                                            anomaly_result.llm_reasoning = llm_reasoning

                                            # Final decision: Both methods must agree for high confidence
                                            # If LLM disagrees, reduce confidence but keep the flag
                                            if (
                                                llm_is_anomaly
                                                and llm_confidence
                                                >= settings.llm_validation_confidence_threshold
                                            ):
                                                # LLM confirms: High confidence anomaly
                                                logger.info(
                                                    f"LLM validated anomaly for log_id: {log_id} "
                                                    f"(confidence: {llm_confidence:.2f})"
                                                )
                                            elif not llm_is_anomaly:
                                                # LLM disagrees: May be false positive, but keep for review
                                                logger.info(
                                                    f"LLM did not confirm anomaly for log_id: {log_id} "
                                                    f"(may be false positive, keeping for review)"
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
                                                context_logs=context,
                                            )

                                            if explanation:
                                                # Store explanation even if detection failed
                                                anomaly_result.llm_reasoning = explanation
                                                logger.debug(
                                                    f"Generated LLM explanation for log_id: {log_id} "
                                                    f"(detection failed, explanation-only)"
                                                )

                                    db.commit()
                        else:
                            logger.debug(f"Tier 1 scoring returned no result for log_id: {log_id}")
                    finally:
                        db.close()
                except Exception as e:
                    # Don't fail the entire storage operation if scoring fails
                    logger.warning(f"Real-time scoring failed for log_id: {log_id}: {e}")
            else:
                logger.warning(f"Failed to store vector embedding for log_id: {log_id}")
        except BudgetExceededError as e:
            logger.warning(f"Budget exceeded, skipping embedding for log_id: {log_id}. Error: {e}")
            return
        except Exception as e:
            logger.error(f"Error storing vector embedding: {e}", exc_info=True)


# Global instance
storage_service = StorageService()
