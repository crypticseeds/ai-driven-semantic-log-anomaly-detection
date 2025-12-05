"""FastAPI application main module."""

import asyncio
from contextlib import asynccontextmanager, suppress

from fastapi import FastAPI
from fastapi.responses import JSONResponse
from prometheus_client import make_asgi_app
from starlette.routing import Mount

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

settings = get_settings()


@asynccontextmanager
async def lifespan(_app: FastAPI):
    """Application lifespan events."""
    # Startup
    setup_opentelemetry()
    instrument_sqlalchemy(engine)

    # Create database tables
    Base.metadata.create_all(bind=engine)

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


@app.get("/")
async def root():
    """Root endpoint."""
    return JSONResponse(
        content={
            "message": f"Welcome to {settings.app_name}",
            "version": settings.app_version,
        }
    )
