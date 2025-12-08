"""LangChain tool wrappers for LLM reasoning service."""

import logging
from datetime import datetime
from typing import Any
from uuid import UUID

from langchain_core.tools import tool
from sqlalchemy import and_

from app.db.postgres import LogEntry
from app.db.session import get_db
from app.services.clustering_service import clustering_service
from app.services.embedding_service import embedding_service
from app.services.llm_reasoning_service import llm_reasoning_service
from app.services.qdrant_service import qdrant_service

logger = logging.getLogger(__name__)


@tool
def analyze_anomaly_tool(
    log_message: str,
    log_level: str | None = None,
    log_service: str | None = None,
    include_root_cause: bool = True,
) -> dict[str, Any]:
    """Analyze an anomalous log entry and provide explanation with root cause analysis.

    This tool uses the LLM reasoning service to analyze why a log entry is anomalous,
    providing detailed explanations, root cause hypotheses, and remediation steps.

    Args:
        log_message: The log message to analyze
        log_level: Optional log level (INFO, ERROR, WARN, etc.)
        log_service: Optional service name that generated the log
        include_root_cause: Whether to include structured root cause analysis

    Returns:
        Dictionary with analysis results including explanation, root causes,
        remediation steps, and severity assessment
    """
    try:
        # Get similar logs for context from Qdrant
        context_logs = []
        try:
            # Generate embedding for the log message to find similar logs
            from app.services.embedding_service import embedding_service

            embedding_result = embedding_service.generate_embedding(log_message)
            if embedding_result and embedding_result.get("embedding"):
                query_embedding = embedding_result["embedding"]
                similar_logs = qdrant_service.search_vectors(
                    query_embedding=query_embedding,
                    limit=5,
                )
                context_logs = [
                    {
                        "level": log.get("level", "N/A"),
                        "message": log.get("message", ""),
                        "service": log.get("service", "N/A"),
                    }
                    for log in similar_logs
                ]
        except Exception as e:
            logger.warning(f"Failed to retrieve context logs: {e}")

        if include_root_cause:
            result = llm_reasoning_service.analyze_anomaly_with_root_cause(
                log_message=log_message,
                log_level=log_level,
                log_service=log_service,
                context_logs=context_logs if context_logs else None,
            )
            if result:
                return result

        # Fallback to regular analysis
        explanation = llm_reasoning_service.analyze_anomaly(
            log_message=log_message,
            log_level=log_level,
            log_service=log_service,
            context_logs=context_logs if context_logs else None,
        )
        return {
            "explanation": explanation or "Analysis failed",
            "root_causes": [],
            "remediation_steps": [],
            "severity": "MEDIUM",
            "severity_reason": "Standard analysis completed",
        }

    except Exception as e:
        logger.error(f"Error in analyze_anomaly_tool: {e}", exc_info=True)
        return {
            "error": str(e),
            "explanation": "Tool execution failed",
            "root_causes": [],
            "remediation_steps": [],
            "severity": "UNKNOWN",
        }


@tool
def detect_anomaly_tool(
    log_message: str,
    log_level: str | None = None,
    log_service: str | None = None,
) -> dict[str, Any]:
    """Detect if a log entry is anomalous using LLM classification.

    This tool validates whether a log entry is truly anomalous by analyzing
    its semantic content. Returns confidence score and reasoning.

    Args:
        log_message: The log message to analyze
        log_level: Optional log level (INFO, ERROR, WARN, etc.)
        log_service: Optional service name

    Returns:
        Dictionary with is_anomaly (bool), confidence (float), and reasoning (str)
    """
    try:
        # Get similar logs for context
        context_logs = []
        try:
            from app.services.embedding_service import embedding_service

            embedding_result = embedding_service.generate_embedding(log_message)
            if embedding_result and embedding_result.get("embedding"):
                query_embedding = embedding_result["embedding"]
                similar_logs = qdrant_service.search_vectors(
                    query_embedding=query_embedding,
                    limit=5,
                )
                context_logs = [
                    {
                        "level": log.get("level", "N/A"),
                        "message": log.get("message", ""),
                    }
                    for log in similar_logs
                ]
        except Exception as e:
            logger.warning(f"Failed to retrieve context logs: {e}")

        result = llm_reasoning_service.detect_anomaly(
            log_message=log_message,
            log_level=log_level,
            log_service=log_service,
            context_logs=context_logs if context_logs else None,
        )

        if result:
            return result

        return {
            "is_anomaly": False,
            "confidence": 0.0,
            "reasoning": "Detection failed",
        }

    except Exception as e:
        logger.error(f"Error in detect_anomaly_tool: {e}", exc_info=True)
        return {
            "error": str(e),
            "is_anomaly": False,
            "confidence": 0.0,
            "reasoning": "Tool execution failed",
        }


@tool
def analyze_anomaly_with_cluster_context(
    log_message: str,
    cluster_id: int,
    log_level: str | None = None,
    log_service: str | None = None,
) -> dict[str, Any]:
    """Analyze an anomalous log entry with cluster context for richer analysis.

    This tool retrieves cluster information and uses it to provide more accurate
    root cause analysis by comparing the outlier against cluster patterns.

    Args:
        log_message: The log message to analyze
        cluster_id: The cluster ID to compare against (outlier is compared to this cluster)
        log_level: Optional log level (INFO, ERROR, WARN, etc.)
        log_service: Optional service name

    Returns:
        Dictionary with enhanced analysis including cluster comparison
    """
    try:
        from app.db.session import get_db

        # Get cluster information
        db = next(get_db())
        try:
            cluster_info = clustering_service.get_cluster_info(cluster_id, db)
        finally:
            db.close()

        if not cluster_info:
            logger.warning(f"Cluster {cluster_id} not found, falling back to standard analysis")
            return analyze_anomaly_tool.invoke(
                {
                    "log_message": log_message,
                    "log_level": log_level,
                    "log_service": log_service,
                    "include_root_cause": True,
                }
            )

        # Get similar logs from Qdrant for additional context
        context_logs = []
        try:
            from app.services.embedding_service import embedding_service

            embedding_result = embedding_service.generate_embedding(log_message)
            if embedding_result and embedding_result.get("embedding"):
                query_embedding = embedding_result["embedding"]
                similar_logs = qdrant_service.search_vectors(
                    query_embedding=query_embedding,
                    limit=5,
                )
                context_logs = [
                    {
                        "level": log.get("level", "N/A"),
                        "message": log.get("message", ""),
                    }
                    for log in similar_logs
                ]
        except Exception as e:
            logger.warning(f"Failed to retrieve context logs: {e}")

        # Use enhanced root cause analysis with cluster context
        result = llm_reasoning_service.analyze_anomaly_with_root_cause(
            log_message=log_message,
            log_level=log_level,
            log_service=log_service,
            context_logs=context_logs if context_logs else None,
            cluster_info=cluster_info,
        )

        if result:
            # Add cluster context to result
            result["cluster_context"] = {
                "cluster_id": cluster_id,
                "cluster_size": cluster_info.get("cluster_size"),
                "comparison": f"Outlier compared to {cluster_info.get('cluster_size', 0)} normal logs in cluster",
            }
            return result

        # Fallback
        return {
            "explanation": "Analysis completed but no structured result returned",
            "root_causes": [],
            "remediation_steps": [],
            "severity": "MEDIUM",
            "severity_reason": "Standard analysis",
            "cluster_context": {
                "cluster_id": cluster_id,
                "cluster_size": cluster_info.get("cluster_size"),
            },
        }

    except Exception as e:
        logger.error(f"Error in analyze_anomaly_with_cluster_context: {e}", exc_info=True)
        return {
            "error": str(e),
            "explanation": "Tool execution failed",
            "root_causes": [],
            "remediation_steps": [],
            "severity": "UNKNOWN",
        }


@tool
def search_logs(
    query: str | None = None,
    level: str | None = None,
    service: str | None = None,
    start_time: str | None = None,
    end_time: str | None = None,
    limit: int = 50,
    use_semantic_search: bool = False,
) -> dict[str, Any]:
    """Search logs with optional filters and semantic search support.

    This tool searches log entries from the database with various filters.
    Can use semantic search for finding similar logs by meaning.

    Args:
        query: Text search query (searches in log message)
        level: Filter by log level (INFO, ERROR, WARN, etc.)
        service: Filter by service name
        start_time: Start time in ISO format (e.g., 2024-01-15T10:30:00)
        end_time: End time in ISO format
        limit: Maximum number of results (default: 50, max: 100)
        use_semantic_search: Use semantic search instead of text search

    Returns:
        Dictionary with search results including logs and metadata
    """
    try:
        # Limit to reasonable maximum
        limit = min(limit, 100)

        db = next(get_db())
        try:
            # Use semantic search if requested and query is provided
            if use_semantic_search and query:
                try:
                    embedding_result = embedding_service.generate_embedding(query)
                    if embedding_result and embedding_result.get("embedding"):
                        query_embedding = embedding_result["embedding"]
                        similar_logs = qdrant_service.search_vectors(
                            query_embedding=query_embedding,
                            limit=limit,
                        )

                        # Get log entries from database
                        log_ids = [UUID(log["id"]) for log in similar_logs]
                        entries = db.query(LogEntry).filter(LogEntry.id.in_(log_ids)).all()

                        results = []
                        for entry in entries:
                            results.append(
                                {
                                    "id": str(entry.id),
                                    "timestamp": entry.timestamp.isoformat(),
                                    "level": entry.level,
                                    "service": entry.service,
                                    "message": entry.message[:200],  # Truncate for tool output
                                }
                            )

                        return {
                            "results": results,
                            "total": len(results),
                            "search_type": "semantic",
                        }
                except Exception as e:
                    logger.warning(f"Semantic search failed, falling back to text search: {e}")

            # Traditional text-based search
            filters = []

            if level:
                filters.append(LogEntry.level == level.upper())

            if service:
                filters.append(LogEntry.service.ilike(f"%{service}%"))

            if start_time:
                try:
                    start_dt = datetime.fromisoformat(start_time.replace("Z", "+00:00"))
                    filters.append(LogEntry.timestamp >= start_dt)
                except ValueError:
                    logger.warning(f"Invalid start_time format: {start_time}")

            if end_time:
                try:
                    end_dt = datetime.fromisoformat(end_time.replace("Z", "+00:00"))
                    filters.append(LogEntry.timestamp <= end_dt)
                except ValueError:
                    logger.warning(f"Invalid end_time format: {end_time}")

            if query:
                filters.append(LogEntry.message.ilike(f"%{query}%"))

            # Execute query
            db_query = db.query(LogEntry)
            if filters:
                db_query = db_query.filter(and_(*filters))

            db_query = db_query.order_by(LogEntry.timestamp.desc())
            entries = db_query.limit(limit).all()

            results = []
            for entry in entries:
                results.append(
                    {
                        "id": str(entry.id),
                        "timestamp": entry.timestamp.isoformat(),
                        "level": entry.level,
                        "service": entry.service,
                        "message": entry.message[:200],  # Truncate for tool output
                    }
                )

            return {
                "results": results,
                "total": len(results),
                "search_type": "text",
            }
        finally:
            db.close()

    except Exception as e:
        logger.error(f"Error in search_logs tool: {e}", exc_info=True)
        return {
            "error": str(e),
            "results": [],
            "total": 0,
            "search_type": "error",
        }


@tool
def summarize_range(
    start_time: str,
    end_time: str,
    service: str | None = None,
    level: str | None = None,
    max_logs: int = 100,
) -> dict[str, Any]:
    """Summarize logs within a time range with aggregation and analysis.

    This tool retrieves logs within a specified time range and provides
    a summary including counts by level, service, and common patterns.

    Args:
        start_time: Start time in ISO format (e.g., 2024-01-15T10:30:00)
        end_time: End time in ISO format
        service: Optional filter by service name
        level: Optional filter by log level
        max_logs: Maximum number of logs to analyze for summary (default: 100)

    Returns:
        Dictionary with summary statistics and analysis
    """
    try:
        db = next(get_db())
        try:
            # Parse time range
            try:
                start_dt = datetime.fromisoformat(start_time.replace("Z", "+00:00"))
                end_dt = datetime.fromisoformat(end_time.replace("Z", "+00:00"))
            except ValueError as e:
                return {
                    "error": f"Invalid time format: {e}",
                    "summary": {},
                }

            # Build filters
            filters = [
                LogEntry.timestamp >= start_dt,
                LogEntry.timestamp <= end_dt,
            ]

            if service:
                filters.append(LogEntry.service.ilike(f"%{service}%"))

            if level:
                filters.append(LogEntry.level == level.upper())

            # Query logs
            entries = (
                db.query(LogEntry)
                .filter(and_(*filters))
                .order_by(LogEntry.timestamp.desc())
                .limit(max_logs)
                .all()
            )

            if not entries:
                return {
                    "summary": {
                        "total_logs": 0,
                        "time_range": {
                            "start": start_time,
                            "end": end_time,
                        },
                        "message": "No logs found in specified time range",
                    },
                }

            # Aggregate statistics
            level_counts = {}
            service_counts = {}
            error_count = 0
            warning_count = 0

            for entry in entries:
                # Count by level
                level_counts[entry.level] = level_counts.get(entry.level, 0) + 1
                if entry.level == "ERROR":
                    error_count += 1
                elif entry.level == "WARN":
                    warning_count += 1

                # Count by service
                service_counts[entry.service] = service_counts.get(entry.service, 0) + 1

            # Find common error patterns (simple keyword extraction)
            error_messages = [e.message.lower()[:100] for e in entries if e.level == "ERROR"]
            common_patterns = []
            if error_messages:
                # Simple pattern detection (can be enhanced)
                word_freq = {}
                for msg in error_messages:
                    words = msg.split()[:10]  # First 10 words
                    for word in words:
                        if len(word) > 4:  # Skip short words
                            word_freq[word] = word_freq.get(word, 0) + 1

                # Get top 5 most common words
                sorted_words = sorted(word_freq.items(), key=lambda x: x[1], reverse=True)[:5]
                common_patterns = [word for word, _ in sorted_words]

            summary = {
                "total_logs": len(entries),
                "time_range": {
                    "start": start_time,
                    "end": end_time,
                },
                "level_distribution": level_counts,
                "service_distribution": dict(list(service_counts.items())[:10]),  # Top 10 services
                "error_count": error_count,
                "warning_count": warning_count,
                "common_error_patterns": common_patterns,
                "sample_logs": [
                    {
                        "timestamp": e.timestamp.isoformat(),
                        "level": e.level,
                        "service": e.service,
                        "message": e.message[:150],
                    }
                    for e in entries[:5]  # First 5 logs as samples
                ],
            }

            return {"summary": summary}

        finally:
            db.close()

    except Exception as e:
        logger.error(f"Error in summarize_range tool: {e}", exc_info=True)
        return {
            "error": str(e),
            "summary": {},
        }


def get_agent_tools() -> list:
    """Get list of LangChain tools for agent executor.

    Returns:
        List of LangChain tool instances
    """
    return [
        analyze_anomaly_tool,
        detect_anomaly_tool,
        analyze_anomaly_with_cluster_context,
        search_logs,
        summarize_range,
    ]
