"""Har bir servis uchun bir xil Flask “karkas”: /health, /ready, JSON xatoliklar, strukturali log, X-Request-ID."""
from __future__ import annotations

import json
import logging
import os
import socket
import sys
import time
import uuid
from typing import Any, Callable

from flask import Flask, g, jsonify, request

from svc_common.db import Database


class ApiError(Exception):
    def __init__(self, message: str, status: int = 400, **extra: Any):
        super().__init__(message)
        self.message, self.status, self.extra = message, status, extra


class JsonFormatter(logging.Formatter):
    def __init__(self, service: str):
        super().__init__()
        self.service = service

    def format(self, record: logging.LogRecord) -> str:
        data = {"ts": self.formatTime(record, "%Y-%m-%dT%H:%M:%S"), "level": record.levelname,
                "service": self.service, "logger": record.name, "msg": record.getMessage()}
        rid = getattr(record, "request_id", None)
        if rid:
            data["request_id"] = rid
        return json.dumps(data, ensure_ascii=False)


def configure_logging(service: str) -> None:
    root = logging.getLogger()
    if any(isinstance(h.formatter, JsonFormatter) for h in root.handlers):
        return
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter(service) if os.getenv("LOG_FORMAT", "json") == "json"
                         else logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    root.handlers = [handler]
    root.setLevel(os.getenv("LOG_LEVEL", "INFO"))


def json_body() -> dict[str, Any]:
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        raise ApiError("JSON obyekt kutilgan")
    return data


def create_service_app(name: str, db: Database, register: Callable[[Flask], None], version: str = "1.0.0") -> Flask:
    configure_logging(name)
    log = logging.getLogger(name)
    app = Flask(name)
    app.json.ensure_ascii = False  # type: ignore[attr-defined]
    app.extensions["db"] = db
    started = time.time()

    @app.before_request
    def _start() -> None:
        g.request_id = request.headers.get("X-Request-ID") or uuid.uuid4().hex[:12]
        g.t0 = time.perf_counter()

    @app.after_request
    def _finish(resp):  # type: ignore[no-untyped-def]
        resp.headers["X-Request-ID"] = g.get("request_id", "")
        resp.headers["X-Service"] = name
        resp.headers["X-Instance"] = socket.gethostname()
        if request.path not in ("/health", "/ready"):
            log.info("%s %s → %s (%.1f ms)", request.method, request.path, resp.status_code,
                     (time.perf_counter() - g.get("t0", time.perf_counter())) * 1000,
                     extra={"request_id": g.get("request_id")})
        return resp

    @app.get("/health")
    def health():  # type: ignore[no-untyped-def]
        """Liveness: jarayon tirikmi (Docker HEALTHCHECK)."""
        return jsonify(service=name, status="ok", version=os.getenv("APP_VERSION", version),
                       git_sha=os.getenv("GIT_SHA", "local")[:7], build_date=os.getenv("BUILD_DATE", "—"),
                       environment=os.getenv("APP_ENV", "development"),
                       instance=socket.gethostname(), uptime_s=round(time.time() - started))

    @app.get("/ready")
    def ready():  # type: ignore[no-untyped-def]
        """Readiness: DB ulanishi ishlayaptimi."""
        ok = db.ping()
        return jsonify(service=name, ready=ok, database=db.dialect), (200 if ok else 503)

    @app.errorhandler(ApiError)
    def _api_error(e: ApiError):  # type: ignore[no-untyped-def]
        return jsonify(error=e.message, **e.extra), e.status

    @app.errorhandler(404)
    def _nf(_):  # type: ignore[no-untyped-def]
        return jsonify(error="Topilmadi"), 404

    @app.errorhandler(405)
    def _na(_):  # type: ignore[no-untyped-def]
        return jsonify(error="Metod ruxsat etilmagan"), 405

    @app.errorhandler(Exception)
    def _unexpected(e: Exception):  # type: ignore[no-untyped-def]
        from werkzeug.exceptions import HTTPException

        from svc_common.http import ServiceError, ServiceUnavailable
        if isinstance(e, HTTPException):
            return jsonify(error=e.description), e.code
        if isinstance(e, ServiceUnavailable):
            return jsonify(error=str(e)), 503
        if isinstance(e, ServiceError):
            return jsonify(error=str(e)), e.status
        log.exception("Kutilmagan xatolik", extra={"request_id": g.get("request_id")})
        return jsonify(error="Ichki server xatoligi", request_id=g.get("request_id")), 500

    register(app)
    return app
