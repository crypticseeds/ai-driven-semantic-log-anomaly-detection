"""Storage service for saving processed log entries to PostgreSQL and Qdrant.

Implements a two-track processing pipeline:
- Fast Path: All logs saved to PostgreSQL immediately (no embedding)
- Priority Path: ERROR/WARN logs get embeddings and anomaly detection
"""

import logging
from uuid import UUID

from sqlalchemy.orm import Session

from app.config import get_settings
from app.db.postgres import AnomalyResult, LogEntry
from app.db.session import get_db
from app.models.log import ProcessedLogEntry
from app.services.embedding_service import BudgetExceededError, embedding_service

logger = logging.getLogger(__name__)


class StorageService:
    """Service for storing processed log entries in PostgreSQL.

    Supports two modes:
    - Fast save: PostgreSQL only (for all logs)
    - Full save: PostgreSQL + Qdrant embedding + anomaly detection (for priority logs)
    """

    def save_log_entry_fast(
        self, processed_log: ProcessedLogEntry, db: Session | None = None
    ) -> UUID | None:
        """Save processed log entry to database WITHOUT embedding generation.

        This is the fast path for all logs - they appear in the dashboard immediately.

        Args:
            processed_log: Processed log entry
            db: Database session (optional, creates new if not provided)

        Returns:
            UUID of saved log entry or None if error
        """
        should_close_db = db is None
        try:
            if db is None:
                db = next(get_db())

            log_entry = LogEntry(
                timestamp=processed_log.timestamp,
                level=processed_log.level,
                service=processed_log.service,
                message=processed_log.message,
                raw_log=processed_log.raw_log,
                log_metadata=processed_log.metadata,
                pii_redacted=processed_log.pii_redacted,
            )

            db.add(log_entry)
            db.commit()
            db.refresh(log_entry)

            logger.debug(f"Fast saved log entry with ID: {log_entry.id}")
            return log_entry.id
        except Exception as e:
            logger.error(f"Failed to fast save log entry: {e}")
            if db:
                db.rollback()
            return None
        finally:
            if should_close_db and db:
                db.close()

    def save_log_entry(
        self, processed_log: ProcessedLogEntry, db: Session | None = None
    ) -> UUID | None:
        """Save processed log entry to database (fast path only).

        For backward compatibility - now just calls save_log_entry_fast.
        Use process_priority_logs_batch for embedding generation.

        Args:
            processed_log: Processed log entry
            db: Database session

        Returns:
            UUID of saved log entry or None if error
        """
        return self.save_log_entry_fast(processed_log, db)

    def save_log_entry_async(self, processed_log: ProcessedLogEntry) -> UUID | None:
        """Save processed log entry asynchronously (creates new session)."""
        db = next(get_db())
        try:
            return self.save_log_entry_fast(processed_log, db)
        except Exception as e:
            logger.error(f"Failed to save log entry async: {e}")
            db.rollback()
            return None
        finally:
            db.close()

    def process_priority_logs_batch(
        self, log_ids: list[UUID], messages: list[str], log_entries_data: list[dict]
    ) -> dict:
        """Process a batch of priority logs with embeddings and anomaly detection.

        This is the priority path for ERROR/WARN logs.
        Uses parallel processing for Qdrant storage and anomaly detection.

        Args:
            log_ids: List of log entry UUIDs (already saved to PostgreSQL)
            messages: List of log messages for embedding
            log_entries_data: List of log entry metadata dicts

        Returns:
            Dict with processing results:
            {
                'processed': int,
                'embeddings_generated': int,
                'anomalies_detected': int,
                'errors': int
            }
        """
        import concurrent.futures
        from contextlib import contextmanager

        from app.services.anomaly_detection_service import anomaly_detection_service
        from app.services.llm_reasoning_service import llm_reasoning_service
        from app.services.qdrant_service import qdrant_service

        @contextmanager
        def get_db_session():
            """Context manager for database sessions."""
            db = next(get_db())
            try:
                yield db
                db.commit()
            except Exception:
                db.rollback()
                raise
            finally:
                db.close()

        settings = get_settings()
        results = {
            "processed": 0,
            "embeddings_generated": 0,
            "anomalies_detected": 0,
            "errors": 0,
        }

        if not log_ids or not messages:
            return results

        try:
            # Generate embeddings in batch (single OpenAI API call)
            embedding_results = embedding_service.generate_embeddings_batch(
                messages, use_cache=True
            )

            # Prepare data for parallel processing
            items_to_process = []
            for i, (log_id, message, embedding_result) in enumerate(
                zip(log_ids, messages, embedding_results, strict=False)
            ):
                results["processed"] += 1

                if not embedding_result or not embedding_result.get("embedding"):
                    logger.warning(f"No embedding generated for log_id: {log_id}")
                    results["errors"] += 1
                    continue

                results["embeddings_generated"] += 1
                log_data = log_entries_data[i] if i < len(log_entries_data) else {}

                items_to_process.append(
                    {
                        "log_id": log_id,
                        "message": message,
                        "embedding": embedding_result["embedding"],
                        "embedding_result": embedding_result,
                        "log_data": log_data,
                    }
                )

            # Process Qdrant storage and anomaly detection in parallel
            def process_single_log(item: dict) -> dict:
                """Process a single log entry (Qdrant + anomaly detection)."""
                log_id = item["log_id"]
                result = {"success": False, "is_anomaly": False, "error": None}

                try:
                    # Prepare payload for Qdrant
                    embedding_result = item["embedding_result"]
                    log_data = item["log_data"]
                    payload = {
                        "level": log_data.get("level"),
                        "service": log_data.get("service"),
                        "timestamp": log_data.get("timestamp"),
                        "pii_redacted": log_data.get("pii_redacted", False),
                        "embedding_model": embedding_result.get("model"),
                        "embedding_timestamp": embedding_result.get("timestamp").isoformat()
                        if embedding_result.get("timestamp")
                        else None,
                        "embedding_cost_usd": embedding_result.get("cost_usd", 0.0),
                        "embedding_tokens": embedding_result.get("tokens", 0),
                        "embedding_cached": embedding_result.get("cached", False),
                    }

                    # Store in Qdrant
                    success = qdrant_service.store_vector(log_id, item["embedding"], payload)
                    if not success:
                        result["error"] = "Failed to store vector"
                        return result

                    result["success"] = True

                    # Run anomaly detection (Tier 1: IsolationForest)
                    with get_db_session() as db:
                        tier1_result = anomaly_detection_service.score_log_entry(
                            log_id=log_id, method="IsolationForest", db=db
                        )

                        if tier1_result and tier1_result.get("is_anomaly", False):
                            result["is_anomaly"] = True
                            tier1_score = tier1_result.get("anomaly_score", 0.0)

                            # Tier 2: LLM validation for high-scoring anomalies
                            if (
                                settings.llm_validation_enabled
                                and tier1_score >= settings.anomaly_score_threshold
                            ):
                                self._run_llm_validation(
                                    log_id,
                                    item["message"],
                                    log_data,
                                    db,
                                    llm_reasoning_service,
                                )

                except Exception as e:
                    result["error"] = str(e)
                    logger.warning(f"Processing failed for log_id {log_id}: {e}")

                return result

            # Use ThreadPoolExecutor for parallel processing
            max_workers = min(len(items_to_process), settings.embedding_parallel_batches)
            if max_workers > 0:
                with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
                    futures = {
                        executor.submit(process_single_log, item): item for item in items_to_process
                    }

                    for future in concurrent.futures.as_completed(futures):
                        try:
                            result = future.result(timeout=30)  # 30s timeout per item
                            if result.get("is_anomaly"):
                                results["anomalies_detected"] += 1
                            if result.get("error"):
                                results["errors"] += 1
                        except concurrent.futures.TimeoutError:
                            results["errors"] += 1
                            logger.warning("Processing timed out for a log entry")
                        except Exception as e:
                            results["errors"] += 1
                            logger.warning(f"Processing failed: {e}")

        except BudgetExceededError as e:
            logger.warning(f"Budget exceeded during batch processing: {e}")
            results["errors"] += len(log_ids) - results["processed"]
        except Exception as e:
            logger.error(f"Error in batch processing: {e}", exc_info=True)
            results["errors"] += len(log_ids) - results["processed"]

        logger.info(
            f"Batch processed: {results['processed']} logs, "
            f"{results['embeddings_generated']} embeddings, "
            f"{results['anomalies_detected']} anomalies"
        )
        return results

    def _run_llm_validation(
        self,
        log_id: UUID,
        message: str,
        log_data: dict,
        db: Session,
        llm_reasoning_service,
    ) -> None:
        """Run LLM validation for a detected anomaly.

        Args:
            log_id: Log entry UUID
            message: Log message
            log_data: Log metadata
            db: Database session
            llm_reasoning_service: LLM reasoning service instance
        """
        settings = get_settings()

        try:
            # Get context logs
            context_logs = (
                db.query(LogEntry)
                .filter(LogEntry.id != log_id)
                .order_by(LogEntry.timestamp.desc())
                .limit(5)
                .all()
            )

            context = [
                {"level": log.level, "service": log.service, "message": log.message}
                for log in context_logs
            ]

            # Run LLM validation
            llm_result = llm_reasoning_service.detect_anomaly(
                log_message=message,
                log_level=log_data.get("level"),
                log_service=log_data.get("service"),
                context_logs=context,
            )

            # Update anomaly result with LLM reasoning
            anomaly_result = (
                db.query(AnomalyResult).filter(AnomalyResult.log_entry_id == log_id).first()
            )

            if anomaly_result and llm_result:
                anomaly_result.llm_reasoning = llm_result.get("reasoning")
                llm_is_anomaly = llm_result.get("is_anomaly", False)
                llm_confidence = llm_result.get("confidence", 0.0)

                if (
                    llm_is_anomaly
                    and llm_confidence >= settings.llm_validation_confidence_threshold
                ):
                    logger.info(f"LLM validated anomaly for log_id: {log_id}")
                else:
                    logger.info(f"LLM did not confirm anomaly for log_id: {log_id}")

        except Exception as e:
            logger.warning(f"LLM validation failed for log_id {log_id}: {e}")


# Global instance
storage_service = StorageService()
