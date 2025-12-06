FROM python:3.13-slim

WORKDIR /app

# Install UV
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# Copy workspace files (uv workspace requires root pyproject.toml and uv.lock)
COPY pyproject.toml ./
COPY uv.lock* ./
COPY backend/pyproject.toml ./backend/

# Install dependencies (include pip for packages that need it)
RUN uv sync --frozen || uv sync && \
    uv pip install pip

# Copy application code (maintain backend/ structure for workspace)
COPY backend/ ./backend/

# Set Python path to backend directory
ENV PYTHONPATH=/app/backend

# Expose port
EXPOSE 8000

# Default command (can be overridden in docker-compose)
# Run from backend directory - uv will auto-detect parent workspace
WORKDIR /app/backend
CMD ["uv", "run", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
