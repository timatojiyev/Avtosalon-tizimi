# syntax=docker/dockerfile:1
# web — multi-stage build. Build context: loyiha ildizi (docker compose build).

# ---------- 1-bosqich: bog'liqliklarni wheel'ga yig'ish ----------
FROM python:3.12-slim AS builder
WORKDIR /build
COPY web/requirements.txt .
RUN pip wheel --no-cache-dir --wheel-dir /wheels -r requirements.txt

# ---------- 2-bosqich: yengil runtime image ----------
FROM python:3.12-slim AS runtime
ARG APP_VERSION=dev
ARG GIT_SHA=unknown
ARG BUILD_DATE=unknown
LABEL org.opencontainers.image.version="${APP_VERSION}" org.opencontainers.image.revision="${GIT_SHA}" \
      org.opencontainers.image.title="avtosalon-web" org.opencontainers.image.source="avtosalon"
ENV PYTHONDONTWRITEBYTECODE=1 COMPOSE_FILE_PATH=/app/docker-compose.yml \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app \
    PORT=8000 \
    APP_VERSION=${APP_VERSION} \
    GIT_SHA=${GIT_SHA} \
    BUILD_DATE=${BUILD_DATE}
RUN groupadd --system app && useradd --system --gid app --uid 10001 --no-create-home app
WORKDIR /app
COPY --from=builder /wheels /wheels
RUN pip install --no-cache-dir /wheels/* && rm -rf /wheels
COPY libs/svc_common ./svc_common
COPY web/avtosalon_web ./avtosalon_web
COPY docker-compose.yml ./docker-compose.yml
USER app
EXPOSE 8000
HEALTHCHECK --interval=15s --timeout=3s --start-period=20s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=2)" || exit 1
CMD ["gunicorn", "--bind", "0.0.0.0:8000", "--workers", "2", "--threads", "4", "--timeout", "30", \
     "--access-logfile", "-", "avtosalon_web.main:create_app()"]
