# Production-Ready Dockerfile for Supply Chain Management System
# Multi-stage build for optimized image size and security

# ═══════════════════════════════════════════════════════════════════
# STAGE 1: Builder (dependencies compilation)
# ═══════════════════════════════════════════════════════════════════
FROM python:3.9-slim as builder

WORKDIR /build

# Install build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    g++ \
    make \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements
COPY requirements.txt .

# Create wheels for all dependencies (faster installation in final stage)
RUN pip wheel --no-cache-dir --no-deps --wheel-dir /build/wheels -r requirements.txt

# ═══════════════════════════════════════════════════════════════════
# STAGE 2: Runtime (minimal production image)
# ═══════════════════════════════════════════════════════════════════
FROM python:3.9-slim

LABEL maintainer="Supply Chain Team <team@example.com>"
LABEL description="Industrial Supply Chain Management System - Production"
LABEL version="1.0.0"

# Set working directory
WORKDIR /app

# Install runtime dependencies only (no build tools)
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Create non-root user for security
RUN useradd -m -u 1000 appuser

# Copy wheels from builder
COPY --from=builder /build/wheels /wheels
COPY --from=builder /build/requirements.txt .

# Install dependencies from wheels (no compilation needed)
RUN pip install --no-cache /wheels/*

# Copy application code
COPY --chown=appuser:appuser . .

# Create necessary directories
RUN mkdir -p /app/models /app/outputs /app/logs && \
    chown -R appuser:appuser /app

# Set environment variables
ENV FLASK_APP=app_hybrid.py
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1
ENV FLASK_ENV=production

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:5000/health || exit 1

# Switch to non-root user
USER appuser

# Expose port
EXPOSE 5000

# Run application with gunicorn
CMD ["gunicorn", \
     "--bind", "0.0.0.0:5000", \
     "--workers", "4", \
     "--worker-class", "sync", \
     "--timeout", "120", \
     "--access-logfile", "-", \
     "--error-logfile", "-", \
     "app_hybrid:app"]
