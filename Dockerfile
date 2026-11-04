# syntax=docker/dockerfile:1.6
# ============================================================================
# OPTIMIZED MULTI-STAGE BUILD - SanskritiSetu Production
# ============================================================================
# BuildKit Features:
#   - Cache mounts for pip (faster rebuilds)
#   - Parallel stage builds
#   - Better layer caching
#
# Build commands:
#   PRODUCTION:  docker build --target production-api -t sanskritisetu:prod .
#   DEVELOPMENT: docker build --target development -t sanskritisetu:dev .
#   WITH CACHE:  DOCKER_BUILDKIT=1 docker build --target production-api -t sanskritisetu:prod .
#   CLEAN BUILD: docker build --no-cache --pull --target production-api -t sanskritisetu:prod .
# ============================================================================

# ==================== BASE STAGE ====================
# Pinned to specific Debian Bookworm for reproducibility
FROM python:3.11-slim-bookworm AS base

# Labels for image identification
LABEL org.opencontainers.image.title="SanskritiSetu"
LABEL org.opencontainers.image.description="Enterprise AI Agent Orchestration Platform"
LABEL org.opencontainers.image.version="1.0.0"
LABEL org.opencontainers.image.vendor="SanskritiSetu.org"

WORKDIR /app

# Python optimizations for containers
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONFAULTHANDLER=1 \
    PYTHONHASHSEED=random \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_DEFAULT_TIMEOUT=300 \
    PIP_RETRIES=5

# Production-minimal system dependencies (no build tools)
RUN --mount=type=cache,target=/var/cache/apt,sharing=locked \
    --mount=type=cache,target=/var/lib/apt,sharing=locked \
    apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates \
    curl \
    libpq-dev \
    postgresql-client \
    && rm -rf /var/lib/apt/lists/*

# Upgrade pip with cache mount and clean __pycache__
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install --upgrade pip==24.0 setuptools==69.0.3 wheel==0.42.0 && \
    find /usr/local/lib/python3.11/site-packages -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true

# ==================== DEPENDENCIES STAGE (HEAVILY CACHED) ====================
FROM base AS dependencies

# Copy only requirements first (layer cache optimization)
COPY requirements-base.txt requirements-prod.txt requirements-prod.lock ./

# Install production dependencies from the LOCK, met hashes (2026-08-05).
# requirements-prod.txt is een pip-compile-INPUT en zegt dat zelf op regel 1; het bevat
# `>=`-ranges die pip bij elke build opnieuw oploste. Zo kwam mcp 2.0.0 in CI terecht,
# dat Tool.inputSchema hernoemde -- een AttributeError die geen enkele gate ving.
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install --no-compile -r requirements-prod.lock && \
    find /usr/local/lib/python3.11/site-packages -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true

# Verify critical packages installed
RUN python -c "import fastapi, sqlalchemy, pydantic, uvicorn; print('[OK] Core packages verified')"

# ==================== BROWSER WORKER BASE ====================
FROM dependencies AS worker-base

# Install Playwright browsers and dependencies (only for worker)
RUN playwright install --with-deps chromium

# ==================== DEVELOPMENT STAGE ====================
FROM worker-base AS development

# Install dev dependencies with cache mount
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install \
    debugpy==1.8.0 \
    ipython==8.18.1 \
    pytest==7.4.3 \
    pytest-asyncio==0.21.1 \
    pytest-cov==4.1.0 \
    pytest-timeout==2.2.0 && \
    find /usr/local/lib/python3.11/site-packages -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true

# Setup non-root user (before copying to ensure correct ownership)
RUN useradd -m -u 1000 -s /bin/bash appuser && \
    mkdir -p /app/indexes/bm25 /tmp /app/.cache && \
    chmod 755 /app && chmod 755 /app/indexes

# Copy application code with correct ownership
COPY --chown=appuser:appuser src/ ./src/
COPY --chown=appuser:appuser config/ ./config/
COPY --chown=appuser:appuser assets/fonts/ /app/assets/fonts/
COPY --chown=appuser:appuser scripts/ ./scripts/
COPY --chown=appuser:appuser scripts/gunicorn_config.py ./gunicorn_config.py

# Make scripts executable and fix ownership of writable dirs
RUN chmod +x /app/scripts/*.sh 2>/dev/null || true && \
    chown -R appuser:appuser /app /tmp /app/.cache

USER appuser
EXPOSE 8000 5678

# Dev healthcheck (port 8000 inside container; compose maps 8110:8000 externally)
HEALTHCHECK --interval=15s --timeout=5s --start-period=30s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

ENTRYPOINT ["/app/scripts/entrypoint-dev.sh"]

# ==================== PRODUCTION API STAGE ====================
FROM dependencies AS production-api

# Setup non-root user first (before copying to ensure correct ownership)
RUN adduser --uid 10001 --disabled-password --gecos "" --no-create-home appuser && \
    mkdir -p /app/indexes/bm25 /tmp /app/.cache && \
    chmod 755 /app && chmod 755 /app/indexes

# Copy application code with correct ownership
COPY --chown=appuser:appuser src/ ./src/
COPY --chown=appuser:appuser config/ ./config/
COPY --chown=appuser:appuser scripts/ ./scripts/
COPY --chown=appuser:appuser scripts/gunicorn_config.py ./gunicorn_config.py

# Set proper permissions, validate, and clean up
RUN chmod +x /app/scripts/*.sh 2>/dev/null || true && \
    chown -R appuser:appuser /app /tmp /app/.cache && \
    python -m py_compile src/main.py && echo "[OK] Syntax validated" && \
    find /app -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true && \
    find /app -type f -name "*.pyc" -delete 2>/dev/null || true

USER appuser
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=10s --start-period=120s --retries=5 \
    CMD curl -f http://localhost:8000/health || exit 1

ENTRYPOINT ["/app/scripts/entrypoint-prod.sh"]

# ==================== PRODUCTION WORKER STAGE ====================
FROM worker-base AS production-worker

# Setup non-root user first (before copying to ensure correct ownership)
RUN adduser --uid 10001 --disabled-password --gecos "" --no-create-home appuser && \
    mkdir -p /app/indexes/bm25 /tmp /app/.cache && \
    chmod 755 /app && chmod 755 /app/indexes

# Copy application code with correct ownership
COPY --chown=appuser:appuser src/ ./src/
COPY --chown=appuser:appuser config/ ./config/
COPY --chown=appuser:appuser scripts/ ./scripts/

# Set proper permissions and clean up
RUN chmod +x /app/scripts/*.sh 2>/dev/null || true && \
    chown -R appuser:appuser /app /tmp /app/.cache && \
    find /app -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true && \
    find /app -type f -name "*.pyc" -delete 2>/dev/null || true

USER appuser

ENTRYPOINT ["/usr/local/bin/dramatiq"]
# Default modules; override with docker-compose command: or Azure --command
# `:redis_broker` en niet alleen de modulenaam (ADR-036 OP-84). Zonder die verwijzing valt
# dramatiq terug op `get_broker()`, en dat is de StubBroker die workflow_worker.py bij het
# importeren zet: de werker start, meldt zich gezond en consumeert NIETS uit Redis.
CMD ["src.workers.workflow_worker:redis_broker", "src.workers.actors"]


# ==================== BONLEZER WORKER STAGE ====================
# Een EIGEN image voor het lezen van bonnen en facturen (bonlezer dag 2, brief
# docs/agent-briefs/generated/2026-10-15-sprint-dag-bonlezer-dag2-eigen-worker.md).
# Docling, PyTorch (CPU) en Tesseract horen NIET in de andere doelen: dat scheelt het backend-image
# ongeveer twee gigabyte (docs/evidence/bonlezer-meting-2026-10-15.md, sectie Grootte). Bewaakt door
# tests/architecture/test_bonlezer_zit_alleen_in_de_eigen_worker.py.
#
#   docker build --target bonlezer-worker -t sanskritisetu-bonlezer-worker .
#
# Bouwt op `dependencies` (de gelockte productie-afhankelijkheden, ZONDER de Playwright-browser van
# `worker-base`): de actor leeft in `src.core.als.bonlezer` en laadt dus dezelfde pakketten.
FROM dependencies AS bonlezer-worker

RUN --mount=type=cache,target=/var/cache/apt,sharing=locked \
    --mount=type=cache,target=/var/lib/apt,sharing=locked \
    apt-get update && apt-get install -y --no-install-recommends \
    tesseract-ocr \
    tesseract-ocr-nld \
    libgl1 \
    libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

COPY requirements-bonlezer.txt ./

# CPU-torch eerst (het GPU-wiel is ruim een gigabyte groter), daarna de vastgepinde bonlezer-pakketten.
# De Docling-modellen worden NU binnengehaald: tijdens het lezen is er geen netwerk (alleen layout en
# tableformer; de rest van de standaarddownload gebruiken we niet).
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install --no-compile torch==2.14.1+cpu torchvision==0.29.1+cpu \
        --index-url https://download.pytorch.org/whl/cpu && \
    pip install --no-compile -r requirements-bonlezer.txt && \
    docling-tools models download layout tableformer -o /modellen

RUN adduser --uid 10001 --disabled-password --gecos "" --no-create-home appuser && \
    mkdir -p /data/bonnen /app/.cache && \
    chmod -R a+rX /modellen

COPY --chown=appuser:appuser src/ ./src/
COPY --chown=appuser:appuser config/ ./config/

RUN chown -R appuser:appuser /app /app/.cache && \
    find /app -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true

ENV HF_HUB_OFFLINE=1 \
    TRANSFORMERS_OFFLINE=1 \
    BONLEZER_ARTIFACTS=/modellen \
    BONLEZER_UPLOAD_ROOT=/data/bonnen

USER appuser

ENTRYPOINT ["/usr/local/bin/dramatiq"]
# De broker bij NAAM (`:_broker`), niet alleen de module (ADR-036 OP-84, zie het CMD van production-worker).
# Een proces en een draad: Docling is niet bedoeld voor parallelle aanroepen in een proces en
# `geen_netwerk()` is procesbreed.
CMD ["src.core.als.bonlezer.worker:_broker", "--processes", "1", "--threads", "1"]
