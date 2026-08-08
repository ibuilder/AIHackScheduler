# Multi-stage production Dockerfile for BBSchedule Platform
FROM python:3.11-slim as builder

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# Install system dependencies
RUN apt-get update && apt-get install -y \
    build-essential \
    curl \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Create non-root user
RUN groupadd -r bbschedule && useradd -r -g bbschedule bbschedule

# Set work directory
WORKDIR /app

# Install from the single dependency list at the repository root, plus the
# extras a production deployment needs. Build from the repo root:
#   docker build -f deployment/Dockerfile -t bbschedule .
#
# The whole source is copied before the install because pyproject declares its
# packages explicitly, so setuptools needs those directories to exist. Copying
# only pyproject.toml gave better layer caching but failed the build outright.
COPY . .
RUN pip install --no-cache-dir ".[postgres,async,integrations]"

# Production stage
FROM python:3.11-slim as production

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    FLASK_ENV=production \
    GUNICORN_WORKERS=4 \
    GUNICORN_TIMEOUT=120

# Install runtime dependencies
RUN apt-get update && apt-get install -y \
    libpq5 \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Create non-root user
RUN groupadd -r bbschedule && useradd -r -g bbschedule bbschedule

# Set work directory
WORKDIR /app

# Copy Python dependencies from builder stage
COPY --from=builder /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

# Copy application code
COPY . .

# Create necessary directories
RUN mkdir -p logs uploads temp && \
    chmod +x deployment/entrypoint.sh && \
    chown -R bbschedule:bbschedule /app

# Switch to non-root user
USER bbschedule

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD curl -f http://localhost:5000/health/health || exit 1

# Expose port
EXPOSE 5000

# The entrypoint creates the schema before handing off. Schema creation stopped
# being an import side effect — it used to race across gunicorn workers — so a
# deployment has to do it deliberately. Set SKIP_DB_INIT=1 for processes that
# should not touch it, such as the Celery workers.
ENTRYPOINT ["/app/deployment/entrypoint.sh"]

# Default command
CMD ["gunicorn", "--bind", "0.0.0.0:5000", "--workers", "4", "--timeout", "120", "--keep-alive", "2", "--max-requests", "1000", "--max-requests-jitter", "100", "--preload", "main:app"]