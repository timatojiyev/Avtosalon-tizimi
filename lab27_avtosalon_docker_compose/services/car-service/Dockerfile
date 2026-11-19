# syntax=docker/dockerfile:1
# car-service — multi-stage build. Build context: loyiha ildizi (docker compose build).

# ---------- 1-bosqich: bog'liqliklarni wheel'ga yig'ish ----------
FROM python:3.12-slim AS builder
WORKDIR /build
COPY services/car-service/requirements.txt .
RUN pip wheel --no-cache-dir --wheel-dir /wheels -r requirements.txt

# ---------- 2-bosqich: yengil runtime image ----------
FROM python:3.12-slim AS runtime
LABEL org.opencontainers.image.title="avtosalon-car-service" org.opencontainers.image.source="avtosalon"
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app \
    PORT=8000
RUN groupadd --system app && useradd --system --gid app --uid 10001 --no-create-home app
WORKDIR /app
COPY --from=builder /wheels /wheels
RUN pip install --no-cache-dir /wheels/* && rm -rf /wheels
COPY libs/svc_common ./svc_common
COPY services/car-service/car_service ./car_service

USER app
EXPOSE 8000
HEALTHCHECK --interval=15s --timeout=3s --start-period=20s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=2)" || exit 1
CMD ["gunicorn", "--bind", "0.0.0.0:8000", "--workers", "2", "--threads", "4", "--timeout", "30", \
     "--access-logfile", "-", "car_service.main:create_app()"]
