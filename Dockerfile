# Multi-stage Dockerfile for DevOps Chatbot v2.0

# Stage 1: Build frontend
FROM node:20-alpine AS frontend-builder
WORKDIR /app/frontend
COPY frontend/package*.json ./
RUN npm install --prefer-offline --no-audit
COPY frontend/ ./
RUN npm run build && \
    find build -name "*.map" -type f -delete && \
    find build -name "*.txt" -type f -delete

# Stage 2: Python dependencies builder
FROM python:3.11-slim AS python-builder
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends gcc g++ \
  && rm -rf /var/lib/apt/lists/*
ENV PATH="/opt/venv/bin:$PATH"
RUN python -m venv /opt/venv

# Install production deps only (no test libs, no JWT/bcrypt)
COPY backend/requirements.prod.txt ./
RUN /opt/venv/bin/pip install --no-cache-dir -r requirements.prod.txt

# Install shared libs (changes more often, but fast)
COPY libs/ ./libs/
RUN /opt/venv/bin/pip install --no-cache-dir -e ./libs/devops-k8s -e ./libs/devops-kb -e ./libs/devops-rag

# Stage 3: Production image
FROM python:3.11-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    supervisor curl ca-certificates libssl3 libstdc++6 \
    && rm -rf /var/lib/apt/lists/*

RUN useradd -m -u 1000 -s /bin/bash chatbot
COPY --from=python-builder /opt/venv /opt/venv

ENV PATH="/opt/venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PYTHONOPTIMIZE=1 \
    PYTHONPATH="/app/backend"

WORKDIR /app

# Configs (rarely change)
COPY docker/supervisord.conf /etc/supervisor/conf.d/supervisord.conf

# Frontend build
COPY --from=frontend-builder --chown=chatbot:chatbot /app/frontend/build /var/www/html

# Shared libs (needed at runtime for editable installs)
COPY --chown=chatbot:chatbot libs/ ./libs/

# Backend source LAST (changes most often = minimal rebuild)
COPY --chown=chatbot:chatbot backend/*.py ./backend/
COPY --chown=chatbot:chatbot backend/api ./backend/api/
COPY --chown=chatbot:chatbot backend/middleware ./backend/middleware/
COPY --chown=chatbot:chatbot backend/utils ./backend/utils/
COPY --chown=chatbot:chatbot backend/skills ./backend/skills/

RUN mkdir -p /data /tmp/supervisor /var/log/supervisor /var/run \
    && chown -R chatbot:chatbot /app /data /tmp /tmp/supervisor /var/www/html /var/log/supervisor /var/run \
    && chmod -R 755 /app /data /var/www/html

USER chatbot
EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=3s --start-period=40s --retries=3 \
    CMD curl -f http://localhost:8080/api/health || exit 1

CMD ["/usr/bin/supervisord", "-c", "/etc/supervisor/conf.d/supervisord.conf"]
