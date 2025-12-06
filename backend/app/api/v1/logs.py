"""Log search and retrieval API endpoints."""

from datetime import datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import JSONResponse
from sqlalchemy import and_
from sqlalchemy.orm import Session

from app.db.postgres import LogEntry
from app.db.session import get_db
from app.observability.metrics import http_requests_total
from app.services.pii_service import pii_service

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
    db: Session = Depends(get_db),
) -> JSONResponse:
    """Search logs with optional filters.

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
        db: Database session

    Returns:
        JSON response with search results (PII-redacted)
    """
    try:
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
            }
        )

    except HTTPException:
        raise
    except Exception as e:
        http_requests_total.labels(method="GET", endpoint="/api/v1/logs/search", status=500).inc()
        raise HTTPException(status_code=500, detail=f"Error searching logs: {str(e)}") from e


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
