FROM python:3.13-slim

WORKDIR /app

# Install UV
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# Copy backend package files
COPY backend/pyproject.toml ./
COPY backend/uv.lock* ./

# Install dependencies
RUN uv sync --frozen || uv sync

# Copy application code
COPY backend/ ./

# Set Python path
ENV PYTHONPATH=/app

# Expose port
EXPOSE 8000

# Default command (can be overridden in docker-compose)
CMD ["uv", "run", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
