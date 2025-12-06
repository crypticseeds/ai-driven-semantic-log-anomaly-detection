# ==============================================================================
# Stage 1: Builder - Download dependencies and spaCy model
# ==============================================================================
FROM python:3.13-slim AS builder

WORKDIR /app

# Install system dependencies for building packages
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Install UV
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# Set UV environment variables
ENV UV_PROJECT_ENVIRONMENT=/opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Copy workspace root files (contains actual dependencies)
COPY pyproject.toml ./pyproject.toml
COPY uv.lock* ./

# Copy backend package files for workspace structure
COPY backend/pyproject.toml ./backend/pyproject.toml

# Install all dependencies
RUN uv sync --frozen --python-preference system || uv sync --python-preference system

# Install pip in venv (required for spacy download command)
RUN uv pip install pip

# Download spaCy model using native command (better mirror/retry handling)
RUN python -m spacy download en_core_web_lg

# ==============================================================================
# Stage 2: Runtime - Slim final image
# ==============================================================================
FROM python:3.13-slim

WORKDIR /app

# Copy only the virtual environment from builder (no build tools needed)
COPY --from=builder /opt/venv /opt/venv

# Set environment variables
ENV PATH="/opt/venv/bin:$PATH"
ENV PYTHONPATH=/app:$PYTHONPATH

# Copy application code
COPY backend/ ./

# Expose port
EXPOSE 8000

# Run with venv Python
CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
