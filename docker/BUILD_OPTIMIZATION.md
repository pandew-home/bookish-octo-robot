# Docker Build Optimization Guide

## Target: <500MB Image Size

This document explains the optimizations applied to achieve a production-ready Docker image under 500MB.

## Optimization Strategies

### 1. Multi-Stage Build (3 stages)

**Stage 1: Frontend Builder (node:20-alpine)**
- Uses Alpine Linux for minimal size (~180MB base)
- Builds React app with production optimizations
- Removes source maps and unnecessary files
- Pre-compresses static assets with gzip

**Stage 2: Python Builder (python:3.11-slim)**
- Installs Python dependencies in isolated virtual environment
- Removes test files and __pycache__ directories
- Cleans up build artifacts

**Stage 3: Production (python:3.11-slim + nginx-alpine)**
- Copies only runtime artifacts from builders
- Uses minimal nginx from Alpine image
- No build tools in final image

### 2. Layer Optimization

- Package installation in single RUN commands
- Aggressive cleanup in same layer (rm -rf)
- Strategic COPY ordering for cache efficiency
- Minimal file copying (exclude tests, docs)

### 3. Python Optimizations

```dockerfile
ENV PYTHONUNBUFFERED=1          # No buffering (faster logs)
ENV PYTHONDONTWRITEBYTECODE=1   # No .pyc files
ENV PYTHONOPTIMIZE=1            # Optimize bytecode
ENV PIP_NO_CACHE_DIR=1          # No pip cache
```

**Dependency Cleanup:**
- Remove test directories from packages
- Delete .pyc and .pyo files
- Remove __pycache__ directories
- Install with --no-deps first, then resolve

### 4. Frontend Optimizations

**Build Time:**
```bash
npm ci --prefer-offline --no-audit  # Faster, reproducible
npm run build                        # Production build
find build -name "*.map" -delete     # Remove source maps
gzip -9 -k *.js *.css *.html        # Pre-compress
```

**Result:** ~2-5MB frontend bundle (compressed)

### 5. Nginx Optimizations

**Size:**
- Copy nginx binary from nginx:alpine (~10MB vs ~50MB from apt)
- Minimal nginx modules
- Remove default configs

**Performance:**
- gzip_static on (serve pre-compressed files)
- Upstream keepalive connections
- Open file cache
- Optimized buffer sizes

### 6. .dockerignore

Excludes from build context:
- Tests (backend/tests/, *.test.*)
- Documentation (.md files, docs/)
- IDE files (.vscode/, .idea/)
- Git history (.git/)
- Node modules (rebuilt in container)
- Python cache (__pycache__/)

**Impact:** 50-70% reduction in build context size

## Expected Image Sizes

| Component | Size |
|-----------|------|
| Base python:3.11-slim | ~130MB |
| Python dependencies | ~200MB |
| Nginx binary | ~10MB |
| Backend code | ~5MB |
| Frontend build | ~3MB |
| Supervisor + curl | ~5MB |
| **Total** | **~350-450MB** |

## Build Commands

### Standard Build
```bash
docker build -t devops-chatbot:v2.0 .
```

### Build with BuildKit (faster)
```bash
DOCKER_BUILDKIT=1 docker build -t devops-chatbot:v2.0 .
```

### Build with Cache Mount (fastest)
```bash
docker buildx build \
  --cache-from type=registry,ref=myregistry/devops-chatbot:cache \
  --cache-to type=registry,ref=myregistry/devops-chatbot:cache \
  -t devops-chatbot:v2.0 \
  .
```

### Check Image Size
```bash
docker images devops-chatbot:v2.0
docker history devops-chatbot:v2.0
```

### Analyze Layers
```bash
docker run --rm -it \
  -v /var/run/docker.sock:/var/run/docker.sock \
  wagoodman/dive:latest devops-chatbot:v2.0
```

## Performance Optimizations

### Uvicorn Settings
```bash
uvicorn backend.main:app \
  --host 127.0.0.1 \
  --port 8000 \
  --workers 2 \
  --loop uvloop \        # Faster event loop
  --http httptools \     # Faster HTTP parser
  --no-access-log        # Reduce I/O
```

### Nginx Settings
- worker_processes auto (use all CPUs)
- worker_connections 2048 (handle more concurrent)
- keepalive connections to backend
- gzip_static on (serve pre-compressed)
- open_file_cache (cache file descriptors)

### Supervisor Settings
- Log rotation (maxbytes, backups)
- Proper signal handling (killasgroup, stopasgroup)
- Resource limits (minfds, minprocs)

## Further Optimization Ideas

### If Still Over 500MB:

1. **Use Alpine Python** (saves ~50MB)
   ```dockerfile
   FROM python:3.11-alpine
   ```
   Note: Requires additional build dependencies

2. **Reduce Python Dependencies**
   - Review requirements.txt
   - Remove unused packages
   - Use lighter alternatives

3. **Split into Separate Images**
   - Frontend: nginx:alpine + React build (~80MB)
   - Backend: python:3.11-slim + FastAPI (~300MB)
   - Deploy as separate containers

4. **Use Distroless** (saves ~100MB)
   ```dockerfile
   FROM gcr.io/distroless/python3-debian11
   ```
   Note: No shell, harder to debug

## Monitoring Image Size

### CI/CD Integration
```yaml
# GitHub Actions example
- name: Check image size
  run: |
    SIZE=$(docker images devops-chatbot:v2.0 --format "{{.Size}}")
    echo "Image size: $SIZE"
    # Fail if over 500MB
    docker images devops-chatbot:v2.0 --format "{{.Size}}" | \
      awk '{if ($1 > 500) exit 1}'
```

## Troubleshooting

### Image Too Large?

1. Check layer sizes:
   ```bash
   docker history devops-chatbot:v2.0 --human --no-trunc
   ```

2. Find large files:
   ```bash
   docker run --rm devops-chatbot:v2.0 \
     find / -type f -size +10M 2>/dev/null
   ```

3. Check Python packages:
   ```bash
   docker run --rm devops-chatbot:v2.0 \
     pip list --format=freeze | wc -l
   ```

### Build Slow?

1. Use BuildKit
2. Add cache mounts
3. Optimize layer ordering
4. Use .dockerignore

### Runtime Issues?

1. Check logs:
   ```bash
   docker logs <container-id>
   ```

2. Exec into container:
   ```bash
   docker exec -it <container-id> /bin/bash
   ```

3. Check resource usage:
   ```bash
   docker stats <container-id>
   ```

## References

- [Docker Best Practices](https://docs.docker.com/develop/dev-best-practices/)
- [Multi-stage Builds](https://docs.docker.com/build/building/multi-stage/)
- [BuildKit](https://docs.docker.com/build/buildkit/)
- [Dive - Image Analysis](https://github.com/wagoodman/dive)
