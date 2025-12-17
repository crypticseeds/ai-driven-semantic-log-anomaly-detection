"""Log search and retrieval API endpoints."""

from datetime import datetime, timedelta
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import JSONResponse
from qdrant_client.http.models import FieldCondition, Filter, MatchValue
from sqlalchemy import and_
from sqlalchemy.orm import Session

from app.db.postgres import AnomalyResult, ClusteringMetadata, LogEntry
from app.db.session import get_db
from app.observability.metrics import http_requests_total
from app.services.anomaly_detection_service import anomaly_detection_service
from app.services.clustering_service import clustering_service
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


@router.get("/volume")
async def get_log_volume(
    hours: Annotated[int, Query(ge=1, le=24, description="Number of hours to look back")] = 1,
    bucket_minutes: Annotated[
        int, Query(ge=1, le=60, description="Time bucket size in minutes")
    ] = 5,
    level: Annotated[str | None, Query(description="Filter by log level")] = None,
    service: Annotated[str | None, Query(description="Filter by service name")] = None,
    db: Session = Depends(get_db),
) -> JSONResponse:
    """Get log volume aggregated by time buckets.

    Args:
        hours: Number of hours to look back (1-24)
        bucket_minutes: Time bucket size in minutes (1-60)
        level: Optional filter by log level
        service: Optional filter by service name
        db: Database session

    Returns:
        JSON response with volume data aggregated by time buckets
    """
    try:
        # Calculate time range
        end_time = datetime.utcnow()
        start_time = end_time - timedelta(hours=hours)

        # Build base query with filters
        query = db.query(LogEntry).filter(
            LogEntry.timestamp >= start_time, LogEntry.timestamp <= end_time
        )

        if level:
            query = query.filter(LogEntry.level == level.upper())

        if service:
            query = query.filter(LogEntry.service.ilike(f"%{service}%"))

        # For simplicity, we'll fetch all logs and aggregate in Python
        # In production, you might want to use more sophisticated SQL aggregation
        logs = query.all()

        # Create time buckets and aggregate
        bucket_delta = timedelta(minutes=bucket_minutes)
        bucket_map: dict = {}

        for log in logs:
            # Calculate which bucket this log belongs to
            bucket_time = log.timestamp.replace(second=0, microsecond=0)
            bucket_minute = (bucket_time.minute // bucket_minutes) * bucket_minutes
            bucket_time = bucket_time.replace(minute=bucket_minute)

            if bucket_time not in bucket_map:
                bucket_map[bucket_time] = {
                    "count": 0,
                    "ERROR": 0,
                    "WARN": 0,
                    "INFO": 0,
                    "DEBUG": 0,
                }

            bucket_map[bucket_time]["count"] += 1
            if log.level in bucket_map[bucket_time]:
                bucket_map[bucket_time][log.level] += 1

        # Generate all time buckets (including empty ones)
        all_buckets = []
        current_time = start_time

        while current_time <= end_time:
            # Truncate to bucket boundary
            bucket_time = current_time.replace(second=0, microsecond=0)
            bucket_minute = (bucket_time.minute // bucket_minutes) * bucket_minutes
            bucket_time = bucket_time.replace(minute=bucket_minute)

            if bucket_time in bucket_map:
                bucket_data = bucket_map[bucket_time]
                result_data = {
                    "timestamp": bucket_time.isoformat(),
                    "count": bucket_data["count"],
                    "level_breakdown": {
                        "ERROR": bucket_data["ERROR"],
                        "WARN": bucket_data["WARN"],
                        "INFO": bucket_data["INFO"],
                        "DEBUG": bucket_data["DEBUG"],
                    },
                }
            else:
                # Empty bucket
                result_data = {
                    "timestamp": bucket_time.isoformat(),
                    "count": 0,
                    "level_breakdown": {"ERROR": 0, "WARN": 0, "INFO": 0, "DEBUG": 0},
                }

            all_buckets.append(result_data)
            current_time += bucket_delta

        http_requests_total.labels(method="GET", endpoint="/api/v1/logs/volume", status=200).inc()

        return JSONResponse(
            content={
                "volume_data": all_buckets,
                "total_logs": sum(bucket["count"] for bucket in all_buckets),
                "time_range": {
                    "start_time": start_time.isoformat(),
                    "end_time": end_time.isoformat(),
                    "hours": hours,
                    "bucket_minutes": bucket_minutes,
                },
                "filters": {"level": level, "service": service},
            }
        )

    except Exception as e:
        http_requests_total.labels(method="GET", endpoint="/api/v1/logs/volume", status=500).inc()
        raise HTTPException(status_code=500, detail=f"Error retrieving log volume: {str(e)}") from e


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


@router.post("/clustering/run")
async def run_clustering(
    sample_size: Annotated[
        int | None, Query(ge=100, description="Sample size for large datasets")
    ] = None,
    min_cluster_size: Annotated[
        int | None, Query(ge=2, description="Minimum cluster size for HDBSCAN")
    ] = None,
    min_samples: Annotated[
        int | None, Query(ge=1, description="Minimum samples for HDBSCAN")
    ] = None,
    db: Session = Depends(get_db),
) -> JSONResponse:
    """Run HDBSCAN clustering on log embeddings.

    This endpoint triggers clustering of all log embeddings stored in Qdrant.
    Cluster assignments are stored in the AnomalyResult table, and cluster
    metadata is stored in the ClusteringMetadata table.

    Args:
        sample_size: Optional sample size for large datasets (default from config)
        min_cluster_size: Override default min_cluster_size (default from config)
        min_samples: Override default min_samples (default from config)
        db: Database session

    Returns:
        JSON response with clustering results
    """
    try:
        result = clustering_service.perform_clustering(
            sample_size=sample_size,
            min_cluster_size=min_cluster_size,
            min_samples=min_samples,
            db=db,
        )

        if "error" in result:
            http_requests_total.labels(
                method="POST", endpoint="/api/v1/logs/clustering/run", status=500
            ).inc()
            raise HTTPException(status_code=500, detail=result["error"])

        http_requests_total.labels(
            method="POST", endpoint="/api/v1/logs/clustering/run", status=200
        ).inc()

        return JSONResponse(
            content={
                "status": "success",
                "n_clusters": result["n_clusters"],
                "n_outliers": result["n_outliers"],
                "total_logs": len(result["cluster_assignments"]),
                "cluster_metadata": result["cluster_metadata"],
            }
        )

    except HTTPException:
        raise
    except Exception as e:
        http_requests_total.labels(
            method="POST", endpoint="/api/v1/logs/clustering/run", status=500
        ).inc()
        raise HTTPException(status_code=500, detail=f"Error running clustering: {str(e)}") from e


@router.get("/clustering/clusters")
async def list_clusters(
    limit: Annotated[int, Query(ge=1, le=100, description="Maximum number of clusters")] = 50,
    offset: Annotated[int, Query(ge=0, description="Offset for pagination")] = 0,
    db: Session = Depends(get_db),
) -> JSONResponse:
    """List all clusters with their metadata.

    Args:
        limit: Maximum number of clusters to return
        offset: Offset for pagination
        db: Database session

    Returns:
        JSON response with list of clusters
    """
    try:
        clusters = (
            db.query(ClusteringMetadata)
            .order_by(ClusteringMetadata.cluster_size.desc())
            .offset(offset)
            .limit(limit)
            .all()
        )

        result = [
            {
                "cluster_id": cluster.cluster_id,
                "cluster_size": cluster.cluster_size,
                "centroid": cluster.cluster_centroid,
                "representative_logs": cluster.representative_logs,
                "created_at": cluster.created_at.isoformat(),
                "updated_at": cluster.updated_at.isoformat(),
            }
            for cluster in clusters
        ]

        # Get total count
        total_count = db.query(ClusteringMetadata).count()

        http_requests_total.labels(
            method="GET", endpoint="/api/v1/logs/clustering/clusters", status=200
        ).inc()

        return JSONResponse(
            content={
                "clusters": result,
                "total": total_count,
                "limit": limit,
                "offset": offset,
            }
        )

    except Exception as e:
        http_requests_total.labels(
            method="GET", endpoint="/api/v1/logs/clustering/clusters", status=500
        ).inc()
        raise HTTPException(status_code=500, detail=f"Error listing clusters: {str(e)}") from e


@router.get("/clustering/clusters/{cluster_id}")
async def get_cluster(
    cluster_id: int,
    db: Session = Depends(get_db),
) -> JSONResponse:
    """Get detailed information about a specific cluster.

    Args:
        cluster_id: Cluster ID to retrieve
        db: Database session

    Returns:
        JSON response with cluster information including sample logs
    """
    try:
        cluster_info = clustering_service.get_cluster_info(cluster_id, db)

        if not cluster_info:
            http_requests_total.labels(
                method="GET", endpoint="/api/v1/logs/clustering/clusters/{cluster_id}", status=404
            ).inc()
            raise HTTPException(status_code=404, detail=f"Cluster {cluster_id} not found")

        http_requests_total.labels(
            method="GET", endpoint="/api/v1/logs/clustering/clusters/{cluster_id}", status=200
        ).inc()

        return JSONResponse(content=cluster_info)

    except HTTPException:
        raise
    except Exception as e:
        http_requests_total.labels(
            method="GET", endpoint="/api/v1/logs/clustering/clusters/{cluster_id}", status=500
        ).inc()
        raise HTTPException(status_code=500, detail=f"Error retrieving cluster: {str(e)}") from e


@router.get("/clustering/clusters/by-log/{log_id}")
async def get_cluster_by_log_id(
    log_id: UUID,
    db: Session = Depends(get_db),
) -> JSONResponse:
    """Get cluster information for a specific log entry by its log_id.

    Args:
        log_id: UUID of the log entry
        db: Database session

    Returns:
        JSON response with cluster information for the log entry
    """
    try:
        cluster_info = clustering_service.get_cluster_info_by_log_id(log_id, db)

        if not cluster_info:
            http_requests_total.labels(
                method="GET",
                endpoint="/api/v1/logs/clustering/clusters/by-log/{log_id}",
                status=404,
            ).inc()
            raise HTTPException(
                status_code=404,
                detail=f"Log entry {log_id} not found or not assigned to a cluster",
            )

        http_requests_total.labels(
            method="GET", endpoint="/api/v1/logs/clustering/clusters/by-log/{log_id}", status=200
        ).inc()

        return JSONResponse(content=cluster_info)

    except HTTPException:
        raise
    except Exception as e:
        http_requests_total.labels(
            method="GET",
            endpoint="/api/v1/logs/clustering/clusters/by-log/{log_id}",
            status=500,
        ).inc()
        raise HTTPException(
            status_code=500, detail=f"Error retrieving cluster for log: {str(e)}"
        ) from e


@router.get("/clustering/outliers")
async def get_outliers(
    limit: Annotated[int, Query(ge=1, le=1000, description="Maximum number of outliers")] = 100,
    offset: Annotated[int, Query(ge=0, description="Offset for pagination")] = 0,
    db: Session = Depends(get_db),
) -> JSONResponse:
    """Get outlier logs (cluster_id = -1).

    Args:
        limit: Maximum number of outliers to return
        offset: Offset for pagination
        db: Database session

    Returns:
        JSON response with list of outlier logs
    """
    try:
        # Get anomaly results with cluster_id = -1
        outlier_results = (
            db.query(AnomalyResult)
            .filter(AnomalyResult.cluster_id == -1)
            .offset(offset)
            .limit(limit)
            .all()
        )

        # Get corresponding log entries
        log_ids = [result.log_entry_id for result in outlier_results]
        log_entries = db.query(LogEntry).filter(LogEntry.id.in_(log_ids)).all()

        # Create a mapping for quick lookup
        log_dict = {log.id: log for log in log_entries}

        result = []
        for outlier_result in outlier_results:
            log_entry = log_dict.get(outlier_result.log_entry_id)
            if log_entry:
                # Redact PII from message
                redacted_message, pii_entities = pii_service.redact_pii(log_entry.message)

                result.append(
                    {
                        "id": str(log_entry.id),
                        "timestamp": log_entry.timestamp.isoformat(),
                        "level": log_entry.level,
                        "service": log_entry.service,
                        "message": redacted_message,
                        "anomaly_score": outlier_result.anomaly_score,
                        "created_at": log_entry.created_at.isoformat(),
                    }
                )

        # Get total count
        total_count = db.query(AnomalyResult).filter(AnomalyResult.cluster_id == -1).count()

        http_requests_total.labels(
            method="GET", endpoint="/api/v1/logs/clustering/outliers", status=200
        ).inc()

        return JSONResponse(
            content={
                "outliers": result,
                "total": total_count,
                "limit": limit,
                "offset": offset,
            }
        )

    except Exception as e:
        http_requests_total.labels(
            method="GET", endpoint="/api/v1/logs/clustering/outliers", status=500
        ).inc()
        raise HTTPException(status_code=500, detail=f"Error retrieving outliers: {str(e)}") from e


@router.post("/anomaly-detection/isolation-forest")
async def detect_anomalies_isolation_forest(
    contamination: Annotated[
        float, Query(ge=0.0, le=0.5, description="Expected proportion of anomalies")
    ] = 0.1,
    n_estimators: Annotated[int, Query(ge=10, description="Number of trees")] = 100,
    db: Session = Depends(get_db),
) -> JSONResponse:
    """Detect anomalies using IsolationForest algorithm.

    Args:
        contamination: Expected proportion of anomalies (0.0 to 0.5)
        n_estimators: Number of trees in the forest
        db: Database session

    Returns:
        JSON response with anomaly detection results
    """
    try:
        result = anomaly_detection_service.detect_with_isolation_forest(
            contamination=contamination,
            n_estimators=n_estimators,
            db=db,
        )

        http_requests_total.labels(
            method="POST",
            endpoint="/api/v1/logs/anomaly-detection/isolation-forest",
            status=200,
        ).inc()

        return JSONResponse(content=result)

    except Exception as e:
        http_requests_total.labels(
            method="POST",
            endpoint="/api/v1/logs/anomaly-detection/isolation-forest",
            status=500,
        ).inc()
        raise HTTPException(
            status_code=500, detail=f"Error running IsolationForest: {str(e)}"
        ) from e


@router.post("/anomaly-detection/z-score")
async def detect_anomalies_zscore(
    threshold: Annotated[float, Query(ge=1.0, le=5.0, description="Z-score threshold")] = 3.0,
    db: Session = Depends(get_db),
) -> JSONResponse:
    """Detect anomalies using Z-score method.

    Args:
        threshold: Z-score threshold (default 3.0 = 3 standard deviations)
        db: Database session

    Returns:
        JSON response with anomaly detection results
    """
    try:
        result = anomaly_detection_service.detect_with_zscore(threshold=threshold, db=db)

        http_requests_total.labels(
            method="POST", endpoint="/api/v1/logs/anomaly-detection/z-score", status=200
        ).inc()

        return JSONResponse(content=result)

    except Exception as e:
        http_requests_total.labels(
            method="POST", endpoint="/api/v1/logs/anomaly-detection/z-score", status=500
        ).inc()
        raise HTTPException(status_code=500, detail=f"Error running Z-score: {str(e)}") from e


@router.post("/anomaly-detection/iqr")
async def detect_anomalies_iqr(
    multiplier: Annotated[float, Query(ge=0.5, le=3.0, description="IQR multiplier")] = 1.5,
    db: Session = Depends(get_db),
) -> JSONResponse:
    """Detect anomalies using Interquartile Range (IQR) method.

    Args:
        multiplier: IQR multiplier (default 1.5)
        db: Database session

    Returns:
        JSON response with anomaly detection results
    """
    try:
        result = anomaly_detection_service.detect_with_iqr(multiplier=multiplier, db=db)

        http_requests_total.labels(
            method="POST", endpoint="/api/v1/logs/anomaly-detection/iqr", status=200
        ).inc()

        return JSONResponse(content=result)

    except Exception as e:
        http_requests_total.labels(
            method="POST", endpoint="/api/v1/logs/anomaly-detection/iqr", status=500
        ).inc()
        raise HTTPException(status_code=500, detail=f"Error running IQR: {str(e)}") from e


@router.post("/anomaly-detection/score/{log_id}")
async def score_log_entry(
    log_id: UUID,
    method: Annotated[
        str, Query(description="Detection method: IsolationForest, Z-score, or IQR")
    ] = "IsolationForest",
    db: Session = Depends(get_db),
) -> JSONResponse:
    """Score a single log entry for anomaly detection (real-time scoring).

    Args:
        log_id: UUID of the log entry to score
        method: Detection method to use (IsolationForest, Z-score, IQR)
        db: Database session

    Returns:
        JSON response with anomaly score and is_anomaly flag
    """
    try:
        if method not in ["IsolationForest", "Z-score", "IQR"]:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid method: {method}. Must be one of: IsolationForest, Z-score, IQR",
            )

        result = anomaly_detection_service.score_log_entry(log_id=log_id, method=method, db=db)

        if result is None:
            raise HTTPException(
                status_code=404, detail=f"Log entry {log_id} not found or no embedding available"
            )

        http_requests_total.labels(
            method="POST", endpoint="/api/v1/logs/anomaly-detection/score", status=200
        ).inc()

        return JSONResponse(content=result)

    except HTTPException:
        raise
    except Exception as e:
        http_requests_total.labels(
            method="POST", endpoint="/api/v1/logs/anomaly-detection/score", status=500
        ).inc()
        raise HTTPException(status_code=500, detail=f"Error scoring log entry: {str(e)}") from e
