FROM python:3.14-slim

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

# Create non-root user and set ownership
RUN useradd -m -u 1000 appuser && \
    chown -R appuser:appuser /app

# Set Python path to backend directory
ENV PYTHONPATH=/app/backend

# Switch to non-root user
USER appuser

# Expose port
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health').read()" || exit 1

# Default command (can be overridden in docker-compose)
# Run from backend directory - uv will auto-detect parent workspace
WORKDIR /app/backend
CMD ["uv", "run", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
