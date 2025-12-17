"""OpenTelemetry instrumentation setup."""

import logging

from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import ReadableSpan, TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor, SpanExporter

from app.config import get_settings

logger = logging.getLogger(__name__)

settings = get_settings()

# # Initialize Langfuse (with error handling for compatibility issues)
# langfuse_client = None
# try:
#     from langfuse import Langfuse
#
#     if settings.langfuse_secret_key and settings.langfuse_public_key:
#         langfuse_client = Langfuse(
#             secret_key=settings.langfuse_secret_key,
#             public_key=settings.langfuse_public_key,
#             host=settings.langfuse_host,
#         )
# except Exception as e:
#     logger.warning(f"Failed to initialize Langfuse: {e}. Continuing without Langfuse support.")


class FilteringBatchSpanProcessor(BatchSpanProcessor):
    """BatchSpanProcessor that filters out specific spans."""

    def __init__(self, exporter: SpanExporter):
        super().__init__(exporter)

    def on_end(self, span: ReadableSpan) -> None:
        """Process the ended span."""
        if self._should_drop(span):
            return
        super().on_end(span)

    def _should_drop(self, span: ReadableSpan) -> bool:
        """Check if span should be dropped."""
        name = span.name

        # Exact matches
        if name in ["connect", "GET /metrics", "GET /", "GET /docs"]:
            return True

        # Prefix matches
        return any(
            name.startswith(prefix) for prefix in ["SELECT", "INSERT", "OPTIONS ", "GET /health"]
        )


def setup_opentelemetry():
    """Setup OpenTelemetry instrumentation."""
    resource = Resource.create(
        {
            "service.name": settings.otel_service_name,
            "service.version": settings.app_version,
        }
    )

    # 1. Global Provider (for System Logs -> Tempo)
    # This provider is set as the global default, so all auto-instrumentation (FastAPI, SQLAlchemy) uses it.
    global_provider = TracerProvider(resource=resource)

    # Configure Tempo Exporter with Filtering
    tempo_exporter = OTLPSpanExporter(endpoint=settings.otel_exporter_otlp_endpoint)
    tempo_processor = FilteringBatchSpanProcessor(tempo_exporter)
    global_provider.add_span_processor(tempo_processor)

    # Set as GLOBAL provider
    trace.set_tracer_provider(global_provider)

    # 2. Isolated Provider (for Langfuse -> Langfuse)
    # This provider is NOT set as global. It is only used by the Langfuse SDK.
    # This ensures that system logs (which use global_provider) NEVER reach Langfuse.
    # if settings.langfuse_secret_key and settings.langfuse_public_key:
    #     try:
    #         langfuse_provider = TracerProvider(resource=resource)
    #
    #         # Initialize Langfuse with the ISOLATED provider
    #         langfuse = Langfuse(
    #             secret_key=settings.langfuse_secret_key,
    #             public_key=settings.langfuse_public_key,
    #             host=settings.langfuse_host,
    #             tracer_provider=langfuse_provider
    #         )
    #         # Langfuse automatically adds its BatchedSpanProcessor to the provider passed in `tracer_provider`
    #         logger.info("Langfuse initialized with Isolated TracerProvider.")
    #
    #     except Exception as e:
    #         logger.warning(f"Failed to initialize Langfuse: {e}. Continuing without Langfuse support.")

    return global_provider


def instrument_fastapi(app):
    """Instrument FastAPI application."""
    FastAPIInstrumentor.instrument_app(app, excluded_urls="health,metrics")


def instrument_sqlalchemy(engine):
    """Instrument SQLAlchemy engine."""
    SQLAlchemyInstrumentor().instrument(engine=engine)
