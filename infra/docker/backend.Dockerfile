FROM python:3.13-slim

WORKDIR /app

# Install UV
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# Copy dependency files
COPY pyproject.toml ./
COPY backend/pyproject.toml ./backend/ 2>/dev/null || true

# Install dependencies
RUN uv sync --frozen || uv sync

# Copy application code
COPY backend/ ./backend/

# Set Python path
ENV PYTHONPATH=/app

# Expose port
EXPOSE 8000

# Default command (can be overridden in docker-compose)
CMD ["uv", "run", "uvicorn", "backend.app.main:app", "--host", "0.0.0.0", "--port", "8000"]

