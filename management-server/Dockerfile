# syntax=docker/dockerfile:1.7
#
# management-server/Dockerfile
#
# Multi-stage build for the sawyer-cloud management-server. Non-root at
# runtime. Stage 1 installs deps into a venv; stage 2 copies the venv +
# the app into a slim runtime image.

# --- stage 1: build ---------------------------------------------------------
FROM python:3.12-slim AS build

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1

RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential \
        libpq-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /build
COPY pyproject.toml README.md ./
COPY app/ ./app/

# Create the venv and install the package + its deps.
RUN python -m venv /venv \
    && /venv/bin/pip install --upgrade pip setuptools wheel \
    && /venv/bin/pip install .

# --- stage 2: runtime -------------------------------------------------------
FROM python:3.12-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH=/venv/bin:$PATH

# Runtime-only shared libs (libpq for asyncpg / psycopg).
RUN apt-get update && apt-get install -y --no-install-recommends \
        libpq5 \
        ca-certificates \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --create-home --shell /usr/sbin/nologin --uid 10001 sawyer

COPY --from=build /venv /venv
WORKDIR /app
COPY app/ ./app/
COPY alembic/ ./alembic/
COPY alembic.ini ./alembic.ini

USER 10001:10001

EXPOSE 8080

# Health check via FastAPI's /health endpoint. Exit non-zero so Docker
# marks the container unhealthy if /health fails.
HEALTHCHECK --interval=15s --timeout=3s --start-period=30s --retries=3 \
    CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8080/health',timeout=2).status==200 else 1)"

# uvicorn runs with --proxy-headers because the server sits behind a TLS
# terminator in prod. Access logs are structured (structlog formats them).
CMD ["uvicorn", "app.main:app", \
     "--host", "0.0.0.0", "--port", "8080", \
     "--proxy-headers", "--forwarded-allow-ips=*"]
