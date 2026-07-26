# Multi-stage Dockerfile for DevOps Chatbot v2.0
# Chatbot API + colocated Vestige MCP (HTTP) in one image; both use PVC at /data.

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

COPY backend/requirements.prod.txt ./
RUN /opt/venv/bin/pip install --no-cache-dir -r requirements.prod.txt

COPY libs/ ./libs/
RUN /opt/venv/bin/pip install --no-cache-dir -e ./libs/devops-k8s -e ./libs/devops-rag

# Stage 3: Vestige native binaries (spike-validated 2.2.1; linux/x64 gnu)
FROM python:3.11-slim AS vestige-bin
ARG VESTIGE_VERSION=2.2.1
RUN apt-get update && apt-get install -y --no-install-recommends ca-certificates curl \
  && rm -rf /var/lib/apt/lists/* \
  && curl -fsSL \
    "https://github.com/samvallad33/vestige/releases/download/v${VESTIGE_VERSION}/vestige-mcp-x86_64-unknown-linux-gnu.tar.gz" \
    -o /tmp/vestige.tar.gz \
  && tar -xzf /tmp/vestige.tar.gz -C /usr/local/bin \
  && chmod +x /usr/local/bin/vestige /usr/local/bin/vestige-mcp /usr/local/bin/vestige-restore \
  && rm /tmp/vestige.tar.gz \
  && /usr/local/bin/vestige --help >/dev/null

# Stage 4: Production image
FROM python:3.11-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    supervisor curl ca-certificates libssl3 libstdc++6 \
    && rm -rf /var/lib/apt/lists/*

RUN useradd -m -u 1000 -s /bin/bash chatbot
COPY --from=python-builder /opt/venv /opt/venv
COPY --from=vestige-bin /usr/local/bin/vestige /usr/local/bin/vestige
COPY --from=vestige-bin /usr/local/bin/vestige-mcp /usr/local/bin/vestige-mcp
COPY --from=vestige-bin /usr/local/bin/vestige-restore /usr/local/bin/vestige-restore

ENV PATH="/opt/venv/bin:/usr/local/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PYTHONOPTIMIZE=1 \
    PYTHONPATH="/app/backend" \
    # Colocated Vestige defaults (overridable at runtime)
    MEMORY_BACKEND=vestige \
    VESTIGE_HTTP_URL=http://127.0.0.1:3928 \
    VESTIGE_DATA_DIR=/data/vestige \
    FASTEMBED_CACHE_PATH=/data/vestige/model-cache

WORKDIR /app

COPY docker/supervisord.conf /etc/supervisor/conf.d/supervisord.conf
COPY docker/start-backend.sh /usr/local/bin/start-backend.sh
COPY docker/start-vestige.sh /usr/local/bin/start-vestige.sh
RUN chmod +x /usr/local/bin/start-backend.sh /usr/local/bin/start-vestige.sh

COPY --from=frontend-builder --chown=chatbot:chatbot /app/frontend/build /var/www/html

COPY --chown=chatbot:chatbot libs/ ./libs/

COPY --chown=chatbot:chatbot backend/*.py ./backend/
COPY --chown=chatbot:chatbot backend/api ./backend/api/
COPY --chown=chatbot:chatbot backend/middleware ./backend/middleware/
COPY --chown=chatbot:chatbot backend/utils ./backend/utils/
COPY --chown=chatbot:chatbot backend/skills ./backend/skills/
COPY --chown=chatbot:chatbot backend/memory ./backend/memory/
COPY --chown=chatbot:chatbot backend/kube_policy ./backend/kube_policy/
COPY --chown=chatbot:chatbot backend/prompts ./backend/prompts/

RUN mkdir -p /data /data/vestige /data/vestige/model-cache /data/conversations \
        /tmp/supervisor /var/log/supervisor /var/run \
    && chown -R chatbot:chatbot /app /data /tmp /tmp/supervisor /var/www/html \
        /var/log/supervisor /var/run \
    && chmod -R 755 /app /data /var/www/html

USER chatbot
EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=3s --start-period=60s --retries=3 \
    CMD curl -f http://localhost:8080/api/health || exit 1

CMD ["/usr/bin/supervisord", "-c", "/etc/supervisor/conf.d/supervisord.conf"]
