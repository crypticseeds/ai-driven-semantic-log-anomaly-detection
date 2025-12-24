"""FastAPI application main module."""

import asyncio
import logging
from contextlib import asynccontextmanager, suppress

import sentry_sdk
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from prometheus_client import make_asgi_app

from app.api.v1.agent import router as agent_router
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


# Configure CORS with enhanced settings
cors_origins = settings.cors_origins.copy()
cors_debug_enabled = (
    settings.cors_debug_logging if settings.cors_debug_logging is not None else settings.debug
)

# Add environment-specific origins and regex patterns
if settings.debug:
    # In development, be more permissive with additional localhost variations
    additional_dev_origins = [
        "http://localhost:3001",
        "http://127.0.0.1:3001",
        "http://0.0.0.0:3000",
        "http://0.0.0.0:3001",
        # Add common development ports
        "http://localhost:3002",
        "http://127.0.0.1:3002",
        "http://localhost:5173",  # Vite dev server
        "http://127.0.0.1:5173",
    ]

    # Only add if not already present
    for origin in additional_dev_origins:
        if origin not in cors_origins:
            cors_origins.append(origin)

    # Enhanced regex for development IPs (local network + Docker)
    origin_regex = r"https?://(?:localhost|127\.0\.0\.1|0\.0\.0\.0|host\.docker\.internal|192\.168\.\d+\.\d+|10\.\d+\.\d+\.\d+|172\.(?:1[6-9]|2\d|3[01])\.\d+\.\d+):\d+"

    if cors_debug_enabled:
        logger.info(f"CORS Debug Mode: Allowing {len(cors_origins)} origins: {cors_origins}")
        logger.info(f"CORS Debug Mode: Origin regex pattern: {origin_regex}")
else:
    # In production, be more restrictive
    origin_regex = None
    logger.info(f"CORS Production Mode: Allowing {len(cors_origins)} configured origins")
    if cors_debug_enabled:
        logger.info(f"CORS Production Origins: {cors_origins}")

# Enhanced CORS headers for better debugging and compatibility
cors_headers = [
    "Accept",
    "Accept-Language",
    "Accept-Encoding",
    "Content-Language",
    "Content-Type",
    "Authorization",
    "X-Requested-With",
    "X-CSRF-Token",
    "X-Debug-Mode",
    "X-Client-Version",
    "X-Request-ID",
    "X-Timestamp",
    "Cache-Control",
    "Pragma",
]

cors_expose_headers = [
    "X-Total-Count",
    "X-Request-ID",
    "X-Debug-Info",
    "X-CORS-Debug",
    "X-Origin-Allowed",
    "X-API-Version",
    "X-Rate-Limit-Remaining",
    "X-Rate-Limit-Reset",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_origin_regex=origin_regex,
    allow_credentials=settings.cors_allow_credentials,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS", "PATCH", "HEAD"],
    allow_headers=cors_headers,
    expose_headers=cors_expose_headers,
    max_age=settings.cors_max_age,
)


# Add CORS debugging middleware
@app.middleware("http")
async def cors_debug_middleware(request: Request, call_next):
    """Add CORS debugging information to responses."""
    origin = request.headers.get("origin")
    method = request.method
    user_agent = request.headers.get("user-agent", "")

    # Log CORS-related requests in debug mode
    if cors_debug_enabled and origin:
        logger.info(f"CORS Request: {method} {request.url.path} from origin: {origin}")

        # Check if origin is allowed
        is_allowed = origin in cors_origins
        if not is_allowed and settings.debug:
            # Check regex pattern for development
            import re

            pattern = r"https?://(?:localhost|127\.0\.0\.1|0\.0\.0\.0|host\.docker\.internal|192\.168\.\d+\.\d+|10\.\d+\.\d+\.\d+|172\.(?:1[6-9]|2\d|3[01])\.\d+\.\d+):\d+"
            is_allowed = bool(re.match(pattern, origin))

        if not is_allowed:
            logger.warning(
                f"CORS: Origin '{origin}' not in allowed list. Configured origins: {cors_origins}"
            )
            logger.warning(f"CORS: User-Agent: {user_agent}")

    # Log preflight requests
    if method == "OPTIONS" and cors_debug_enabled:
        logger.info(f"CORS Preflight: {request.url.path} from {origin}")
        logger.info(f"CORS Preflight Headers: {dict(request.headers)}")

    # Process the request
    response = await call_next(request)

    # Add debug headers in development
    if settings.debug:
        response.headers["X-CORS-Debug"] = "enabled"
        response.headers["X-Debug-Info"] = f"origin={origin or 'none'},method={method}"
        response.headers["X-API-Version"] = settings.app_version
        if origin:
            # Check both explicit list and regex
            explicit_allowed = origin in cors_origins
            regex_allowed = False
            if settings.debug:
                import re

                pattern = r"https?://(?:localhost|127\.0\.0\.1|0\.0\.0\.0|host\.docker\.internal|192\.168\.\d+\.\d+|10\.\d+\.\d+\.\d+|172\.(?:1[6-9]|2\d|3[01])\.\d+\.\d+):\d+"
                regex_allowed = bool(re.match(pattern, origin))

            response.headers["X-Origin-Allowed"] = str(explicit_allowed or regex_allowed).lower()
            response.headers["X-Origin-Method"] = (
                "explicit" if explicit_allowed else ("regex" if regex_allowed else "denied")
            )

    return response


# Instrument FastAPI for OpenTelemetry
instrument_fastapi(app)

# Mount Prometheus metrics endpoint
metrics_app = make_asgi_app()
app.mount("/metrics", metrics_app)

# Include API routers
app.include_router(logs_router)
app.include_router(agent_router)


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


@app.get("/health/cors")
async def cors_diagnostic(request: Request):
    """CORS diagnostic endpoint for troubleshooting."""
    origin = request.headers.get("origin")
    user_agent = request.headers.get("user-agent", "")
    referer = request.headers.get("referer", "")

    # Check if origin is allowed
    origin_allowed = False
    origin_method = "none"
    if origin:
        # Check explicit list
        if origin in cors_origins:
            origin_allowed = True
            origin_method = "explicit"
        elif settings.debug:
            # Check regex pattern for development
            import re

            pattern = r"https?://(?:localhost|127\.0\.0\.1|0\.0\.0\.0|host\.docker\.internal|192\.168\.\d+\.\d+|10\.\d+\.\d+\.\d+|172\.(?:1[6-9]|2\d|3[01])\.\d+\.\d+):\d+"
            if re.match(pattern, origin):
                origin_allowed = True
                origin_method = "regex"

    # Analyze potential issues
    issues = []
    suggestions = []

    if not origin:
        issues.append("No Origin header present (direct API access or same-origin)")
    elif not origin_allowed:
        issues.append(f"Origin '{origin}' not in allowed list")
        suggestions.append(f"Add '{origin}' to CORS_ORIGINS environment variable")

    if origin and referer:
        try:
            from urllib.parse import urlparse

            origin_parsed = urlparse(origin)
            referer_parsed = urlparse(referer)
            origin_host = origin_parsed.hostname or ""
            referer_host = referer_parsed.hostname or ""
            if origin_host and referer_host and origin_host != referer_host:
                issues.append("Origin and Referer hosts don't match")
        except Exception:
            # If URL parsing fails, skip this check
            pass

    # Check for mixed content
    if origin and origin.startswith("https://") and str(request.base_url).startswith("http://"):
        issues.append("Mixed content: HTTPS frontend accessing HTTP backend")
        suggestions.append("Use HTTPS for backend or HTTP for frontend in development")

    http_requests_total.labels(method="GET", endpoint="/health/cors", status=200).inc()

    return JSONResponse(
        content={
            "cors_status": "configured",
            "timestamp": str(request.headers.get("date", "")),
            "request_info": {
                "origin": origin,
                "referer": referer,
                "user_agent": user_agent,
                "method": request.method,
                "url": str(request.url),
            },
            "cors_validation": {
                "origin_allowed": origin_allowed,
                "origin_method": origin_method,
                "explicit_origins": cors_origins,
                "regex_enabled": settings.debug,
                "debug_mode": settings.debug,
            },
            "cors_config": {
                "allow_credentials": settings.cors_allow_credentials,
                "allow_methods": ["GET", "POST", "PUT", "DELETE", "OPTIONS", "PATCH", "HEAD"],
                "max_age": settings.cors_max_age,
                "debug_logging": cors_debug_enabled,
            },
            "diagnostics": {
                "issues": issues,
                "suggestions": suggestions
                + [
                    f"Ensure frontend uses API_URL: {request.base_url}",
                    "Check browser developer tools for CORS errors",
                    "Verify backend is accessible from frontend network",
                    "Test with: curl -H 'Origin: your-origin' "
                    + str(request.base_url)
                    + "health/cors",
                ],
            },
            "headers_received": dict(request.headers),
        }
    )


@app.get("/")
async def root():
    """Root endpoint."""
    return JSONResponse(
        content={
            "message": "AI Driven Semantic Log Anomaly Detection",
            "version": settings.app_version,
            "developedBy": settings.developer_name,
        }
    )


@app.get("/sentry-debug")
async def trigger_error():
    """Sentry debug endpoint to verify setup.

    This endpoint intentionally triggers a division by zero error
    to test Sentry error monitoring integration.
    """
    division_by_zero = 1 / 0  # noqa: F841
