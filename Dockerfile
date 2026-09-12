# syntax=docker/dockerfile:1
#
# CareBridge API — multi-stage image (builder wheels -> slim runtime).
# Python 3.12-slim satisfies AGENTS.md §5 (3.11+) with good wheel availability
# for bcrypt/cryptography.

# ---------------------------------------------------------------------------
# Stage 1: builder — compile/download wheels for all dependencies.
# ---------------------------------------------------------------------------
FROM python:3.12-slim AS builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# Toolchain for any source-only wheels.
RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential libffi-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip wheel --no-cache-dir --wheel-dir /wheels -r requirements.txt

# ---------------------------------------------------------------------------
# Stage 2: runtime — slim image, non-root user, wheels installed offline.
# ---------------------------------------------------------------------------
FROM python:3.12-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# Build metadata (override with --build-arg).
ARG BUILD_GIT_SHA=dev
ARG BUILD_TIMESTAMP=""
ENV BUILD_GIT_SHA=${BUILD_GIT_SHA} \
    BUILD_TIMESTAMP=${BUILD_TIMESTAMP}

WORKDIR /app

# curl is required for the container HEALTHCHECK.
RUN apt-get update \
    && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd --system appuser \
    && useradd --system --gid appuser --home-dir /home/appuser --create-home appuser

# Install dependencies from the builder's wheels (offline, no index).
COPY --from=builder /wheels /wheels
RUN pip install --no-index --find-links=/wheels /wheels/*.whl \
    && rm -rf /wheels

# Application code (fixtures are required at runtime; .dockerignore excludes
# secrets, logs, caches, local DBs, tests, and the React UI).
COPY --chown=appuser:appuser . .

USER appuser

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD curl -fsS http://localhost:8000/health || exit 1

CMD ["uvicorn", "src.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
