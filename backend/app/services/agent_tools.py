"""LangChain tool wrappers for LLM reasoning service."""

import logging
from typing import Any

from langchain_core.tools import tool

from app.services.clustering_service import clustering_service
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


def get_agent_tools() -> list:
    """Get list of LangChain tools for agent executor.

    Returns:
        List of LangChain tool instances
    """
    return [
        analyze_anomaly_tool,
        detect_anomaly_tool,
        analyze_anomaly_with_cluster_context,
    ]
