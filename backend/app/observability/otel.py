"""OpenTelemetry instrumentation setup."""

import logging

from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

from app.config import get_settings

logger = logging.getLogger(__name__)

settings = get_settings()

# Initialize Langfuse (with error handling for compatibility issues)
langfuse_client = None
try:
    from langfuse import Langfuse

    if settings.langfuse_secret_key and settings.langfuse_public_key:
        langfuse_client = Langfuse(
            secret_key=settings.langfuse_secret_key,
            public_key=settings.langfuse_public_key,
            host=settings.langfuse_host,
        )
except Exception as e:
    logger.warning(f"Failed to initialize Langfuse: {e}. Continuing without Langfuse support.")


def setup_opentelemetry():
    """Setup OpenTelemetry instrumentation."""
    resource = Resource.create(
        {
            "service.name": settings.otel_service_name,
            "service.version": settings.app_version,
        }
    )

    provider = TracerProvider(resource=resource)
    processor = BatchSpanProcessor(OTLPSpanExporter(endpoint=settings.otel_exporter_otlp_endpoint))
    provider.add_span_processor(processor)
    trace.set_tracer_provider(provider)

    return provider


def instrument_fastapi(app):
    """Instrument FastAPI application."""
    FastAPIInstrumentor.instrument_app(app)


def instrument_sqlalchemy(engine):
    """Instrument SQLAlchemy engine."""
    SQLAlchemyInstrumentor().instrument(engine=engine)
