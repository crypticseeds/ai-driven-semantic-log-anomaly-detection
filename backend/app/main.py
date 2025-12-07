"""FastAPI application main module."""

import asyncio
import logging
from contextlib import asynccontextmanager, suppress

import sentry_sdk
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from prometheus_client import make_asgi_app

from app.api.v1.logs import router as logs_router
from app.config import get_settings
from app.db.postgres import Base
from app.db.session import engine
from app.observability.metrics import http_requests_total
from app.observability.otel import (
    instrument_fastapi,
    instrument_sqlalchemy,
    setup_opentelemetry,
)
from app.services.ingestion_service import ingestion_service
from app.services.kafka_service import kafka_service
from app.services.qdrant_service import qdrant_service

settings = get_settings()

# Initialize Sentry SDK before FastAPI app
if settings.sentry_dsn:
    sentry_sdk.init(
        dsn=settings.sentry_dsn,
        send_default_pii=True,
        enable_logs=True,
        traces_sample_rate=1.0,
        profile_session_sample_rate=1.0,
        profile_lifecycle="trace",
    )
    # Configure Python logging to forward to Sentry
    logging.basicConfig(level=logging.INFO)
    logger = logging.getLogger(__name__)
    logger.info("Sentry SDK initialized successfully")
else:
    logger = logging.getLogger(__name__)
    logger.warning("Sentry DSN not configured, skipping Sentry initialization")


@asynccontextmanager
async def lifespan(_app: FastAPI):
    """Application lifespan events."""
    # Startup
    setup_opentelemetry()
    instrument_sqlalchemy(engine)

    # Create database tables
    Base.metadata.create_all(bind=engine)

    # Initialize Qdrant collection
    qdrant_service.ensure_collection()

    # Start ingestion service
    ingestion_task = asyncio.create_task(ingestion_service.start_consuming())

    yield

    # Shutdown
    ingestion_service.stop()
    ingestion_task.cancel()
    with suppress(asyncio.CancelledError):
        await ingestion_task


app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    debug=settings.debug,
    lifespan=lifespan,
)

# Instrument FastAPI for OpenTelemetry
instrument_fastapi(app)

# Mount Prometheus metrics endpoint
metrics_app = make_asgi_app()
app.mount("/metrics", metrics_app)

# Include API routers
app.include_router(logs_router)


@app.get("/health")
async def healthcheck():
    """Health check endpoint."""
    http_requests_total.labels(method="GET", endpoint="/health", status=200).inc()
    return JSONResponse(
        content={
            "status": "healthy",
            "service": settings.app_name,
            "version": settings.app_version,
        }
    )


@app.get("/health/kafka")
async def kafka_healthcheck():
    """Kafka health check endpoint."""
    consumer_healthy = kafka_service.is_consumer_healthy()
    producer_healthy = kafka_service.is_producer_healthy()
    kafka_healthy = consumer_healthy and producer_healthy

    status_code = 200 if kafka_healthy else 503
    http_requests_total.labels(method="GET", endpoint="/health/kafka", status=status_code).inc()

    return JSONResponse(
        content={
            "status": "healthy" if kafka_healthy else "unhealthy",
            "kafka": {
                "consumer": "healthy" if consumer_healthy else "unhealthy",
                "producer": "healthy" if producer_healthy else "unhealthy",
            },
        },
        status_code=status_code,
    )


@app.get("/")
async def root():
    """Root endpoint."""
    return JSONResponse(
        content={
            "message": f"Welcome to {settings.app_name}",
            "version": settings.app_version,
        }
    )


@app.get("/sentry-debug")
async def trigger_error():
    """Sentry debug endpoint to verify setup.

    This endpoint intentionally triggers a division by zero error
    to test Sentry error monitoring integration.
    """
    division_by_zero = 1 / 0  # noqa: F841
