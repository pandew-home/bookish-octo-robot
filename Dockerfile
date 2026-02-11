# Multi-stage Dockerfile for DevOps Chatbot v2.0
# Optimized for size (<500MB target) and performance

# Stage 1: Build frontend
FROM node:20-alpine AS frontend-builder

WORKDIR /app/frontend

# Copy package files first for better layer caching
COPY frontend/package*.json ./

# Install dependencies (including devDependencies for build)
RUN npm install --prefer-offline --no-audit

# Copy frontend source
COPY frontend/ ./

# Build frontend with production optimizations
RUN npm run build && \
    # Remove source maps and unnecessary files to reduce size
    find build -name "*.map" -type f -delete && \
    find build -name "*.txt" -type f -delete && \
    # Compress static assets
    find build -type f \( -name "*.js" -o -name "*.css" -o -name "*.html" \) -exec gzip -9 -k {} \;

# Stage 2: Python dependencies builder
FROM python:3.11-slim AS python-builder

WORKDIR /app

# Install build dependencies required to compile wheels
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    g++ \
  && rm -rf /var/lib/apt/lists/*

ENV PATH="/opt/venv/bin:$PATH"

RUN python -m venv /opt/venv

# Copy shared libraries first (needed for editable installs in requirements.txt)
COPY libs/ ./libs/

# Install backend requirements once and keep the resulting venv for the final stage
COPY backend/requirements.txt ./backend/requirements.txt
RUN /opt/venv/bin/pip install --upgrade pip setuptools wheel && \
    /opt/venv/bin/pip install -r backend/requirements.txt && \
    echo "=== Verifying uvicorn installation ===" && \
    /opt/venv/bin/pip list | grep uvicorn && \
    /opt/venv/bin/uvicorn --version && \
    ls -la /opt/venv/bin/uvicorn && \
    find /opt/venv -type d \( -name "tests" -o -name "test" \) -prune -exec rm -rf {} + 2>/dev/null || true && \
    find /opt/venv -type f \( -name "*.pyc" -o -name "*.pyo" \) -delete && \
    find /opt/venv -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true

# Stage 3: Envoy proxy builder
FROM envoyproxy/envoy:v1.29.2 AS envoy-minimal

# Stage 4: Production image
FROM python:3.11-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    supervisor \
    curl \
    ca-certificates \
    libssl3 \
    libstdc++6 \
    && rm -rf /var/lib/apt/lists/* \
    && apt-get clean \
    && rm -rf /var/cache/apt/*

# Copy Envoy binary from Envoy image
COPY --from=envoy-minimal /usr/local/bin/envoy /usr/local/bin/envoy

# Create non-root user
RUN useradd -m -u 1000 -s /bin/bash chatbot

# Copy Python virtual environment from builder
COPY --from=python-builder /opt/venv /opt/venv

# Set environment to use virtual environment
ENV PATH="/opt/venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PYTHONOPTIMIZE=1 \
    PYTHONPATH="/app/backend"

# Set working directory
WORKDIR /app

# Copy backend source (excluding tests and unnecessary files)
COPY --chown=chatbot:chatbot backend/*.py ./backend/
COPY --chown=chatbot:chatbot backend/api ./backend/api/
COPY --chown=chatbot:chatbot backend/middleware ./backend/middleware/
COPY --chown=chatbot:chatbot backend/utils ./backend/utils/

# Copy shared libraries (only necessary files)
COPY --chown=chatbot:chatbot libs/ ./libs/

# Copy frontend build from stage 1
COPY --from=frontend-builder --chown=chatbot:chatbot /app/frontend/build /var/www/html

# Copy Envoy and supervisor configs
COPY docker/envoy.yaml /etc/envoy/envoy.yaml
COPY docker/supervisord.conf /etc/supervisor/conf.d/supervisord.conf

# Create necessary directories with proper permissions
RUN mkdir -p /data /tmp /tmp/envoy /tmp/supervisor /var/log/supervisor /var/run /etc/envoy \
    && chown -R chatbot:chatbot /app /data /tmp /tmp/envoy /tmp/supervisor /var/www/html /var/log/supervisor /var/run /etc/envoy \
    && chmod -R 755 /app /data /var/www/html \
    # Remove Python cache files
    && find /app -type f -name "*.pyc" -delete \
    && find /app -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true

# Switch to non-root user
USER chatbot

# Expose port
EXPOSE 8080

# Health check with reduced overhead
HEALTHCHECK --interval=30s --timeout=3s --start-period=40s --retries=3 \
    CMD curl -f http://localhost:8080/api/health || exit 1

# Start supervisor
CMD ["/usr/bin/supervisord", "-c", "/etc/supervisor/conf.d/supervisord.conf"]
