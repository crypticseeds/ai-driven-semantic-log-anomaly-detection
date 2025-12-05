"""Prometheus metrics."""

from prometheus_client import Counter, Histogram, Gauge

# Request metrics
http_requests_total = Counter(
    "http_requests_total",
    "Total HTTP requests",
    ["method", "endpoint", "status"],
)

http_request_duration_seconds = Histogram(
    "http_request_duration_seconds",
    "HTTP request duration in seconds",
    ["method", "endpoint"],
)

# Log processing metrics
logs_processed_total = Counter(
    "logs_processed_total",
    "Total logs processed",
    ["service", "level"],
)

anomalies_detected_total = Counter(
    "anomalies_detected_total",
    "Total anomalies detected",
    ["method"],
)

# System metrics
active_connections = Gauge(
    "active_connections",
    "Active database connections",
)

vector_store_size = Gauge(
    "vector_store_size",
    "Number of vectors in Qdrant",
)

