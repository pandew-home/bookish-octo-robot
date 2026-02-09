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

# Install backend requirements once and keep the resulting venv for the final stage
COPY backend/requirements.txt ./backend/requirements.txt
RUN /opt/venv/bin/pip install --upgrade pip setuptools wheel && \
    /opt/venv/bin/pip install -r backend/requirements.txt && \
    /opt/venv/bin/pip list | grep uvicorn && \
    find /opt/venv -type d \( -name "tests" -o -name "test" \) -prune -exec rm -rf {} + 2>/dev/null || true && \
    find /opt/venv -type f \( -name "*.pyc" -o -name "*.pyo" \) -delete && \
    find /opt/venv -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true

# Copy and install shared libraries using editable installs so they can stay slim
COPY libs/ ./libs/
RUN for lib in libs/*/; do \
    if [ -f "$lib/setup.py" ]; then \
        /opt/venv/bin/pip install -e "$lib"; \
    fi; \
    done && \
    find /opt/venv -type f -name "*.pyc" -delete && \
    find /opt/venv -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true

# Stage 3: Minimal nginx builder
FROM nginx:1.25-alpine AS nginx-minimal

# Stage 4: Production image
FROM python:3.11-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    supervisor \
    curl \
    ca-certificates \
    libpcre2-8-0 \
    zlib1g \
    && rm -rf /var/lib/apt/lists/* \
    && apt-get clean \
    && rm -rf /var/cache/apt/*

# Copy nginx binary and minimal dependencies from nginx image
COPY --from=nginx-minimal /usr/sbin/nginx /usr/sbin/nginx
COPY --from=nginx-minimal /usr/lib/nginx /usr/lib/nginx
COPY --from=nginx-minimal /etc/nginx /etc/nginx

# Create non-root user
RUN useradd -m -u 1000 -s /bin/bash chatbot

# Copy Python virtual environment from builder
COPY --from=python-builder /opt/venv /opt/venv

# Set environment to use virtual environment
ENV PATH="/opt/venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PYTHONOPTIMIZE=1

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

# Copy nginx and supervisor configs
COPY docker/nginx.conf /etc/nginx/nginx.conf
COPY docker/supervisord.conf /etc/supervisor/conf.d/supervisord.conf

# Create necessary directories with proper permissions
RUN mkdir -p /data /tmp /var/log/nginx /var/log/supervisor /var/cache/nginx /var/run \
    && chown -R chatbot:chatbot /app /data /tmp /var/www/html /var/log/nginx /var/log/supervisor /var/cache/nginx /var/run \
    && chmod -R 755 /app /data /var/www/html \
    # Remove nginx default config and unnecessary files
    && rm -f /etc/nginx/sites-enabled/default \
    && rm -rf /etc/nginx/conf.d/*.default \
    # Remove Python cache files
    && find /app -type f -name "*.pyc" -delete \
    && find /app -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true

# Switch to non-root user
USER chatbot

# Expose port
EXPOSE 80

# Health check with reduced overhead
HEALTHCHECK --interval=30s --timeout=3s --start-period=40s --retries=3 \
    CMD curl -f http://localhost:80/api/health || exit 1

# Start supervisor
CMD ["/usr/bin/supervisord", "-c", "/etc/supervisor/conf.d/supervisord.conf"]
