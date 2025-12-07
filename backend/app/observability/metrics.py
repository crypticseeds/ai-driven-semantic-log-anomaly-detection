"""Prometheus metrics."""

from prometheus_client import Counter, Gauge, Histogram

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

# Qdrant operation metrics
qdrant_operations_total = Counter(
    "qdrant_operations_total",
    "Total Qdrant operations",
    ["operation", "status"],
)

qdrant_operation_duration_seconds = Histogram(
    "qdrant_operation_duration_seconds",
    "Qdrant operation duration in seconds",
    ["operation"],
)

# OpenAI embedding metrics
openai_embeddings_total = Counter(
    "openai_embeddings_total",
    "Total OpenAI embedding requests",
    ["model", "status"],
)

openai_embedding_duration_seconds = Histogram(
    "openai_embedding_duration_seconds",
    "OpenAI embedding generation duration in seconds",
    ["model"],
)

openai_embedding_cost_usd = Counter(
    "openai_embedding_cost_usd",
    "Total cost of OpenAI embeddings in USD",
    ["model"],
)

openai_embedding_tokens_total = Counter(
    "openai_embedding_tokens_total",
    "Total tokens processed for embeddings",
    ["model"],
)

openai_rate_limit_errors_total = Counter(
    "openai_rate_limit_errors_total",
    "Total OpenAI rate limit errors",
    ["model"],
)

openai_embedding_cache_hits_total = Counter(
    "openai_embedding_cache_hits_total",
    "Total embedding cache hits",
)

openai_budget_exceeded_total = Counter(
    "openai_budget_exceeded_total",
    "Total requests rejected due to budget limit",
    ["model"],
)

openai_daily_spending_usd = Gauge(
    "openai_daily_spending_usd",
    "Current daily spending for OpenAI embeddings in USD",
    ["model"],
)
