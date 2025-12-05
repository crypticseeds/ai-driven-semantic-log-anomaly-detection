FROM python:3.13-slim

WORKDIR /app

# Install system dependencies for spaCy and build tools
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Install UV
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# Set UV environment variables - venv outside /app to survive volume mounts
ENV UV_PROJECT_ENVIRONMENT=/opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Copy backend package files
COPY backend/pyproject.toml ./
COPY backend/uv.lock* ./

# Install dependencies with system Python preference
RUN uv sync --frozen --python-preference system || uv sync --python-preference system

# Install pip in the venv (required for spaCy model download)
RUN uv pip install pip

# Pre-download spaCy model during build (avoids 400MB download on first request)
RUN python -m spacy download en_core_web_lg

# Copy application code
COPY backend/ ./

# Set Python path
ENV PYTHONPATH=/app:$PYTHONPATH

# Expose port
EXPOSE 8000

# Default command - use venv Python directly instead of uv run
CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
