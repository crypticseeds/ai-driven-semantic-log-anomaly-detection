"""Log search and retrieval API endpoints."""

from datetime import datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import JSONResponse
from qdrant_client.http.models import FieldCondition, Filter, MatchValue
from sqlalchemy import and_
from sqlalchemy.orm import Session

from app.db.postgres import LogEntry
from app.db.session import get_db
from app.observability.metrics import http_requests_total
from app.services.embedding_service import BudgetExceededError, embedding_service
from app.services.pii_service import pii_service
from app.services.qdrant_service import qdrant_service

router = APIRouter(prefix="/api/v1/logs", tags=["logs"])


@router.get("/search")
async def search_logs(
    query: Annotated[str | None, Query(description="Search query string")] = None,
    level: Annotated[str | None, Query(description="Filter by log level")] = None,
    service: Annotated[str | None, Query(description="Filter by service name")] = None,
    start_time: Annotated[str | None, Query(description="Start time (ISO format)")] = None,
    end_time: Annotated[str | None, Query(description="End time (ISO format)")] = None,
    limit: Annotated[int, Query(ge=1, le=1000, description="Maximum number of results")] = 100,
    offset: Annotated[int, Query(ge=0, description="Offset for pagination")] = 0,
    use_semantic_search: Annotated[
        bool, Query(description="Use semantic search instead of text search")
    ] = False,
    similarity_threshold: Annotated[
        float | None,
        Query(ge=0.0, le=1.0, description="Minimum similarity score for semantic search"),
    ] = None,
    db: Session = Depends(get_db),
) -> JSONResponse:
    """Search logs with optional filters and semantic search support.

    All returned log messages are automatically redacted for PII before being returned.
    The raw_log field contains the original unredacted log for audit purposes (if authorized).

    Args:
        query: Text search query
        level: Filter by log level (INFO, WARN, ERROR, etc.)
        service: Filter by service name
        start_time: Start time in ISO format (e.g., 2024-01-15T10:30:00)
        end_time: End time in ISO format
        limit: Maximum number of results (1-1000)
        offset: Offset for pagination
        use_semantic_search: Use semantic search with vector embeddings
        similarity_threshold: Minimum similarity score (0.0-1.0) for semantic search
        db: Database session

    Returns:
        JSON response with search results (PII-redacted)
    """
    try:
        # Use semantic search if requested and query is provided
        if use_semantic_search and query:
            return await _semantic_search(
                query=query,
                level=level,
                service=service,
                start_time=start_time,
                end_time=end_time,
                limit=limit,
                offset=offset,
                similarity_threshold=similarity_threshold,
                db=db,
            )

        # Traditional text-based search
        # Build query filters
        filters = []

        if level:
            filters.append(LogEntry.level == level.upper())

        if service:
            filters.append(LogEntry.service.ilike(f"%{service}%"))

        if start_time:
            try:
                start_dt = datetime.fromisoformat(start_time.replace("Z", "+00:00"))
                filters.append(LogEntry.timestamp >= start_dt)
            except ValueError as err:
                raise HTTPException(
                    status_code=400, detail="Invalid start_time format. Use ISO format."
                ) from err

        if end_time:
            try:
                end_dt = datetime.fromisoformat(end_time.replace("Z", "+00:00"))
                filters.append(LogEntry.timestamp <= end_dt)
            except ValueError as err:
                raise HTTPException(
                    status_code=400, detail="Invalid end_time format. Use ISO format."
                ) from err

        if query:
            # Search in message field
            filters.append(LogEntry.message.ilike(f"%{query}%"))

        # Execute query
        db_query = db.query(LogEntry)
        if filters:
            db_query = db_query.filter(and_(*filters))

        # Order by timestamp descending (newest first)
        db_query = db_query.order_by(LogEntry.timestamp.desc())

        # Get total count
        total = db_query.count()

        # Apply pagination
        entries = db_query.offset(offset).limit(limit).all()

        # Convert to response format and redact PII from messages
        results = []
        for entry in entries:
            # Redact PII from the message field before returning
            redacted_message, pii_entities = pii_service.redact_pii(entry.message)

            result = {
                "id": str(entry.id),
                "timestamp": entry.timestamp.isoformat(),
                "level": entry.level,
                "service": entry.service,
                "message": redacted_message,  # PII-redacted message
                "metadata": entry.log_metadata,
                "pii_redacted": entry.pii_redacted,
                "pii_entities_detected": pii_entities,  # PII entities found in this search
                "created_at": entry.created_at.isoformat(),
            }
            results.append(result)

        http_requests_total.labels(method="GET", endpoint="/api/v1/logs/search", status=200).inc()

        return JSONResponse(
            content={
                "results": results,
                "total": total,
                "limit": limit,
                "offset": offset,
                "has_more": (offset + limit) < total,
                "search_type": "text",
            }
        )

    except HTTPException:
        raise
    except Exception as e:
        http_requests_total.labels(method="GET", endpoint="/api/v1/logs/search", status=500).inc()
        raise HTTPException(status_code=500, detail=f"Error searching logs: {str(e)}") from e


async def _semantic_search(
    query: str,
    level: str | None,
    service: str | None,
    start_time: str | None,
    end_time: str | None,
    limit: int,
    offset: int,
    similarity_threshold: float | None,
    db: Session,
) -> JSONResponse:
    """Perform semantic search using Qdrant vector search with hybrid filtering.

    Args:
        query: Search query text
        level: Filter by log level
        service: Filter by service name
        start_time: Start time filter
        end_time: End time filter
        limit: Maximum results
        offset: Pagination offset
        similarity_threshold: Minimum similarity score
        db: Database session

    Returns:
        JSON response with search results
    """
    # Generate embedding for query
    try:
        embedding_result = embedding_service.generate_embedding(query)
        if not embedding_result or not embedding_result.get("embedding"):
            raise HTTPException(status_code=500, detail="Failed to generate embedding for query")
        query_embedding = embedding_result["embedding"]
    except BudgetExceededError as e:
        raise HTTPException(
            status_code=429,
            detail=f"OpenAI budget limit exceeded: {str(e)}. Please try again later or contact administrator.",
        ) from e

    # Build Qdrant filter conditions
    filter_conditions = None
    filter_must = []

    if level:
        filter_must.append(FieldCondition(key="level", match=MatchValue(value=level.upper())))

    if service:
        filter_must.append(FieldCondition(key="service", match=MatchValue(value=service)))

    if filter_must:
        filter_conditions = Filter(must=filter_must)

    # Search in Qdrant
    vector_results = qdrant_service.search_vectors(
        query_embedding=query_embedding,
        limit=limit + offset,  # Get more results to account for offset
        filter_conditions=filter_conditions,
        score_threshold=similarity_threshold,
    )

    # Apply offset
    vector_results = vector_results[offset:]

    # Fetch full log entries from PostgreSQL
    log_ids = [UUID(result["id"]) for result in vector_results]
    if not log_ids:
        http_requests_total.labels(method="GET", endpoint="/api/v1/logs/search", status=200).inc()
        return JSONResponse(
            content={
                "results": [],
                "total": 0,
                "limit": limit,
                "offset": offset,
                "has_more": False,
                "search_type": "semantic",
            }
        )

    # Query PostgreSQL for full log entries
    entries = db.query(LogEntry).filter(LogEntry.id.in_(log_ids)).all()

    # Create a mapping of ID to entry for efficient lookup
    entry_map = {entry.id: entry for entry in entries}

    # Build results in the same order as vector search results
    results = []
    for vector_result in vector_results:
        log_id = UUID(vector_result["id"])
        entry = entry_map.get(log_id)

        if not entry:
            continue

        # Apply time filters if specified
        if start_time:
            try:
                start_dt = datetime.fromisoformat(start_time.replace("Z", "+00:00"))
                if entry.timestamp < start_dt:
                    continue
            except ValueError:
                pass

        if end_time:
            try:
                end_dt = datetime.fromisoformat(end_time.replace("Z", "+00:00"))
                if entry.timestamp > end_dt:
                    continue
            except ValueError:
                pass

        # Redact PII from the message field before returning
        redacted_message, pii_entities = pii_service.redact_pii(entry.message)

        result = {
            "id": str(entry.id),
            "timestamp": entry.timestamp.isoformat(),
            "level": entry.level,
            "service": entry.service,
            "message": redacted_message,
            "metadata": entry.log_metadata,
            "pii_redacted": entry.pii_redacted,
            "pii_entities_detected": pii_entities,
            "created_at": entry.created_at.isoformat(),
            "similarity_score": vector_result["score"],
        }
        results.append(result)

    http_requests_total.labels(method="GET", endpoint="/api/v1/logs/search", status=200).inc()

    return JSONResponse(
        content={
            "results": results,
            "total": len(results),  # Approximate total for semantic search
            "limit": limit,
            "offset": offset,
            "has_more": len(vector_results) >= limit,
            "search_type": "semantic",
        }
    )


@router.get("/{log_id}")
async def get_log(
    log_id: UUID,
    db: Session = Depends(get_db),
) -> JSONResponse:
    """Get a specific log entry by ID.

    The message field is automatically redacted for PII before being returned.

    Args:
        log_id: UUID of the log entry
        db: Database session

    Returns:
        JSON response with log entry (PII-redacted)
    """
    try:
        entry = db.query(LogEntry).filter(LogEntry.id == log_id).first()

        if not entry:
            http_requests_total.labels(
                method="GET", endpoint="/api/v1/logs/{log_id}", status=404
            ).inc()
            raise HTTPException(status_code=404, detail="Log entry not found")

        # Redact PII from the message field before returning
        redacted_message, pii_entities = pii_service.redact_pii(entry.message)

        result = {
            "id": str(entry.id),
            "timestamp": entry.timestamp.isoformat(),
            "level": entry.level,
            "service": entry.service,
            "message": redacted_message,  # PII-redacted message
            "raw_log": entry.raw_log,  # Original log (for audit, if authorized)
            "metadata": entry.log_metadata,
            "pii_redacted": entry.pii_redacted,
            "pii_entities_detected": pii_entities,  # PII entities found in this retrieval
            "created_at": entry.created_at.isoformat(),
        }

        http_requests_total.labels(method="GET", endpoint="/api/v1/logs/{log_id}", status=200).inc()

        return JSONResponse(content=result)

    except HTTPException:
        raise
    except Exception as e:
        http_requests_total.labels(method="GET", endpoint="/api/v1/logs/{log_id}", status=500).inc()
        raise HTTPException(status_code=500, detail=f"Error retrieving log: {str(e)}") from e
