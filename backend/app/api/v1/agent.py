"""Agent-specific API endpoints for LLM reasoning."""

import logging
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import JSONResponse, StreamingResponse
from sqlalchemy.orm import Session

from app.db.postgres import AnomalyResult, LogEntry
from app.db.session import get_db
from app.observability.metrics import http_requests_total
from app.services.agent_executor_service import agent_executor_service
from app.services.agent_tools import (
    analyze_anomaly_tool,
    analyze_anomaly_with_cluster_context,
    detect_anomaly_tool,
    search_logs,
    summarize_range,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/agent", tags=["agent"])


@router.post("/analyze-anomaly")
async def agent_analyze_anomaly(
    log_message: Annotated[str, Query(description="Log message to analyze")],
    log_level: Annotated[str | None, Query(description="Log level (INFO, ERROR, etc.)")] = None,
    log_service: Annotated[str | None, Query(description="Service name")] = None,
    include_root_cause: Annotated[
        bool, Query(description="Include structured root cause analysis")
    ] = True,
) -> JSONResponse:
    """Analyze an anomalous log entry using agent tools.

    This endpoint uses LangChain tools to analyze log anomalies with optional
    root cause analysis and remediation suggestions.

    Args:
        log_message: The log message to analyze
        log_level: Optional log level
        log_service: Optional service name
        include_root_cause: Whether to include structured root cause analysis

    Returns:
        JSON response with analysis results
    """
    try:
        result = analyze_anomaly_tool.invoke(
            {
                "log_message": log_message,
                "log_level": log_level,
                "log_service": log_service,
                "include_root_cause": include_root_cause,
            }
        )

        http_requests_total.labels(
            method="POST", endpoint="/api/v1/agent/analyze-anomaly", status=200
        ).inc()

        return JSONResponse(content=result)

    except Exception as e:
        http_requests_total.labels(
            method="POST", endpoint="/api/v1/agent/analyze-anomaly", status=500
        ).inc()
        logger.error(f"Error in agent analyze anomaly: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Error analyzing anomaly: {str(e)}") from e


@router.post("/analyze-anomaly/stream")
async def agent_analyze_anomaly_stream(
    log_message: Annotated[str, Query(description="Log message to analyze")],
    log_level: Annotated[str | None, Query(description="Log level (INFO, ERROR, etc.)")] = None,
    log_service: Annotated[str | None, Query(description="Service name")] = None,
    include_root_cause: Annotated[
        bool, Query(description="Include structured root cause analysis")
    ] = True,
) -> StreamingResponse:
    """Stream analysis results for an anomalous log entry.

    This endpoint provides streaming support for real-time reasoning analysis.
    Results are streamed as they become available.

    Args:
        log_message: The log message to analyze
        log_level: Optional log level
        log_service: Optional service name
        include_root_cause: Whether to include structured root cause analysis

    Returns:
        Streaming response with analysis results
    """
    try:
        # For now, return the result as JSON (streaming can be enhanced later with OpenAI streaming)
        result = analyze_anomaly_tool.invoke(
            {
                "log_message": log_message,
                "log_level": log_level,
                "log_service": log_service,
                "include_root_cause": include_root_cause,
            }
        )

        import json

        async def generate():
            yield f"data: {json.dumps(result)}\n\n"

        http_requests_total.labels(
            method="POST", endpoint="/api/v1/agent/analyze-anomaly/stream", status=200
        ).inc()

        return StreamingResponse(
            generate(), media_type="text/event-stream", headers={"Cache-Control": "no-cache"}
        )

    except Exception as e:
        http_requests_total.labels(
            method="POST", endpoint="/api/v1/agent/analyze-anomaly/stream", status=500
        ).inc()
        logger.error(f"Error in agent analyze anomaly stream: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Error streaming analysis: {str(e)}") from e


@router.post("/analyze-anomaly/{log_id}")
async def agent_analyze_anomaly_by_id(
    log_id: UUID,
    include_root_cause: Annotated[
        bool, Query(description="Include structured root cause analysis")
    ] = True,
    use_cluster_context: Annotated[
        bool, Query(description="Use cluster context if available")
    ] = True,
    db: Session = Depends(get_db),
) -> JSONResponse:
    """Analyze an anomalous log entry by ID using agent tools.

    This endpoint retrieves a log entry by ID and analyzes it with optional
    cluster context for richer analysis.

    Args:
        log_id: UUID of the log entry to analyze
        include_root_cause: Whether to include structured root cause analysis
        use_cluster_context: Whether to use cluster context if available
        db: Database session

    Returns:
        JSON response with analysis results
    """
    try:
        # Get log entry
        log_entry = db.query(LogEntry).filter(LogEntry.id == log_id).first()
        if not log_entry:
            http_requests_total.labels(
                method="POST", endpoint="/api/v1/agent/analyze-anomaly/{log_id}", status=404
            ).inc()
            raise HTTPException(status_code=404, detail=f"Log entry {log_id} not found")

        # Check if there's cluster context available
        cluster_id = None
        if use_cluster_context:
            anomaly_result = (
                db.query(AnomalyResult).filter(AnomalyResult.log_entry_id == log_id).first()
            )
            if anomaly_result and anomaly_result.cluster_id and anomaly_result.cluster_id != -1:
                cluster_id = anomaly_result.cluster_id

        # Use cluster context if available
        if cluster_id and use_cluster_context:
            result = analyze_anomaly_with_cluster_context.invoke(
                {
                    "log_message": log_entry.message,
                    "cluster_id": cluster_id,
                    "log_level": log_entry.level,
                    "log_service": log_entry.service,
                }
            )
        else:
            result = analyze_anomaly_tool.invoke(
                {
                    "log_message": log_entry.message,
                    "log_level": log_entry.level,
                    "log_service": log_entry.service,
                    "include_root_cause": include_root_cause,
                }
            )

        http_requests_total.labels(
            method="POST", endpoint="/api/v1/agent/analyze-anomaly/{log_id}", status=200
        ).inc()

        return JSONResponse(content=result)

    except HTTPException:
        raise
    except Exception as e:
        http_requests_total.labels(
            method="POST", endpoint="/api/v1/agent/analyze-anomaly/{log_id}", status=500
        ).inc()
        logger.error(f"Error in agent analyze anomaly by ID: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Error analyzing anomaly: {str(e)}") from e


@router.post("/detect-anomaly")
async def agent_detect_anomaly(
    log_message: Annotated[str, Query(description="Log message to analyze")],
    log_level: Annotated[str | None, Query(description="Log level (INFO, ERROR, etc.)")] = None,
    log_service: Annotated[str | None, Query(description="Service name")] = None,
) -> JSONResponse:
    """Detect if a log entry is anomalous using agent tools.

    This endpoint uses LangChain tools to classify log entries as anomalous or normal.

    Args:
        log_message: The log message to analyze
        log_level: Optional log level
        log_service: Optional service name

    Returns:
        JSON response with detection results (is_anomaly, confidence, reasoning)
    """
    try:
        result = detect_anomaly_tool.invoke(
            {
                "log_message": log_message,
                "log_level": log_level,
                "log_service": log_service,
            }
        )

        http_requests_total.labels(
            method="POST", endpoint="/api/v1/agent/detect-anomaly", status=200
        ).inc()

        return JSONResponse(content=result)

    except Exception as e:
        http_requests_total.labels(
            method="POST", endpoint="/api/v1/agent/detect-anomaly", status=500
        ).inc()
        logger.error(f"Error in agent detect anomaly: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Error detecting anomaly: {str(e)}") from e


@router.post("/rca")
async def root_cause_analysis(
    query: Annotated[str, Query(description="Natural language query for root cause analysis")],
    context: Annotated[str | None, Query(description="Optional JSON context as string")] = None,
) -> JSONResponse:
    """Perform root cause analysis using the agent executor.

    This endpoint uses a LangChain agent executor to perform comprehensive
    root cause analysis. The agent can search logs, analyze anomalies,
    summarize time ranges, and provide detailed insights.

    Args:
        query: Natural language query describing what to analyze
            Examples:
            - "What caused the database connection errors yesterday?"
            - "Analyze the spike in ERROR logs between 10am and 12pm"
            - "Find the root cause of authentication failures in the auth service"
        context: Optional JSON string with additional context

    Returns:
        JSON response with agent analysis results
    """
    try:
        if not agent_executor_service.is_available():
            http_requests_total.labels(
                method="POST", endpoint="/api/v1/agent/rca", status=503
            ).inc()
            raise HTTPException(
                status_code=503,
                detail="Agent executor not available. Check OpenAI API key configuration.",
            )

        # Parse context if provided
        context_dict = None
        if context:
            import json

            try:
                context_dict = json.loads(context)
            except json.JSONDecodeError:
                logger.warning(f"Invalid JSON context provided: {context}")

        # Execute agent
        result = agent_executor_service.analyze_root_cause(query=query, context=context_dict)

        if "error" in result:
            http_requests_total.labels(
                method="POST", endpoint="/api/v1/agent/rca", status=500
            ).inc()
            raise HTTPException(status_code=500, detail=result["error"])

        http_requests_total.labels(method="POST", endpoint="/api/v1/agent/rca", status=200).inc()

        return JSONResponse(content=result)

    except HTTPException:
        raise
    except Exception as e:
        http_requests_total.labels(method="POST", endpoint="/api/v1/agent/rca", status=500).inc()
        logger.error(f"Error in root cause analysis: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Error performing RCA: {str(e)}") from e


@router.get("/tools")
async def list_agent_tools() -> JSONResponse:
    """List available agent tools.

    Returns:
        JSON response with list of available tools and their descriptions
    """
    try:
        tools_info = [
            {
                "name": "analyze_anomaly_tool",
                "description": analyze_anomaly_tool.description,
                "parameters": {
                    "log_message": "str - The log message to analyze",
                    "log_level": "str | None - Optional log level",
                    "log_service": "str | None - Optional service name",
                    "include_root_cause": "bool - Whether to include root cause analysis",
                },
            },
            {
                "name": "detect_anomaly_tool",
                "description": detect_anomaly_tool.description,
                "parameters": {
                    "log_message": "str - The log message to analyze",
                    "log_level": "str | None - Optional log level",
                    "log_service": "str | None - Optional service name",
                },
            },
            {
                "name": "analyze_anomaly_with_cluster_context",
                "description": analyze_anomaly_with_cluster_context.description,
                "parameters": {
                    "log_message": "str - The log message to analyze",
                    "cluster_id": "int - The cluster ID to compare against",
                    "log_level": "str | None - Optional log level",
                    "log_service": "str | None - Optional service name",
                },
            },
            {
                "name": "search_logs",
                "description": search_logs.description,
                "parameters": {
                    "query": "str | None - Text search query",
                    "level": "str | None - Filter by log level",
                    "service": "str | None - Filter by service name",
                    "start_time": "str | None - Start time in ISO format",
                    "end_time": "str | None - End time in ISO format",
                    "limit": "int - Maximum number of results (default: 50)",
                    "use_semantic_search": "bool - Use semantic search",
                },
            },
            {
                "name": "summarize_range",
                "description": summarize_range.description,
                "parameters": {
                    "start_time": "str - Start time in ISO format",
                    "end_time": "str - End time in ISO format",
                    "service": "str | None - Optional filter by service",
                    "level": "str | None - Optional filter by level",
                    "max_logs": "int - Maximum logs to analyze (default: 100)",
                },
            },
        ]

        http_requests_total.labels(method="GET", endpoint="/api/v1/agent/tools", status=200).inc()

        return JSONResponse(content={"tools": tools_info})

    except Exception as e:
        http_requests_total.labels(method="GET", endpoint="/api/v1/agent/tools", status=500).inc()
        logger.error(f"Error listing agent tools: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Error listing tools: {str(e)}") from e
