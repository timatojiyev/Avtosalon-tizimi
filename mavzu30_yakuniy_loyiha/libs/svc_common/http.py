"""Servislararo HTTP klient (standart kutubxona): timeout, qayta urinish, X-Request-ID uzatish."""
from __future__ import annotations

import json
import logging
import time
import urllib.error
import urllib.request
from typing import Any

log = logging.getLogger("svc.http")


class ServiceUnavailable(Exception):
    """Boshqa servis javob bermadi (tarmoq xatosi yoki 5xx)."""


class ServiceError(Exception):
    def __init__(self, status: int, payload: dict[str, Any]):
        super().__init__(payload.get("error", f"HTTP {status}"))
        self.status, self.payload = status, payload


class ServiceClient:
    def __init__(self, name: str, base_url: str, timeout: float = 5.0, retries: int = 2):
        self.name, self.base_url, self.timeout, self.retries = name, base_url.rstrip("/"), timeout, retries

    def get(self, path: str, request_id: str = "") -> dict[str, Any] | list[Any]:
        return self._call("GET", path, None, request_id)

    def post(self, path: str, body: dict[str, Any] | None = None, request_id: str = "") -> dict[str, Any]:
        return self._call("POST", path, body or {}, request_id)  # type: ignore[return-value]

    def _call(self, method: str, path: str, body: dict[str, Any] | None, request_id: str) -> Any:
        data = json.dumps(body).encode() if body is not None else None
        headers = {"Content-Type": "application/json", "Accept": "application/json"}
        caller, ctx_rid = _flask_context()
        request_id = request_id or ctx_rid           # so'rov ID'si avtomatik keyingi servisga uzatiladi
        if request_id:
            headers["X-Request-ID"] = request_id
        if caller:
            headers["X-Caller"] = caller
        last: Exception | None = None
        attempts = self.retries + 1 if method == "GET" else 1   # POST idempotent emas — qayta urinmaymiz
        for attempt in range(attempts):
            req = urllib.request.Request(self.base_url + path, data=data, method=method, headers=headers)
            try:
                with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                    raw = resp.read()
                    return json.loads(raw) if raw else {}
            except urllib.error.HTTPError as e:
                payload = _safe_json(e.read())
                if e.code >= 500:
                    last = ServiceUnavailable(f"{self.name}: {payload.get('error') or f'HTTP {e.code}'}")
                else:
                    raise ServiceError(e.code, payload) from e
            except (urllib.error.URLError, TimeoutError, ConnectionError) as e:
                last = ServiceUnavailable(f"{self.name} servisiga ulanib bo'lmadi: {getattr(e, 'reason', e)}")
            if attempt < attempts - 1:
                time.sleep(0.3 * (attempt + 1))
        log.warning("%s %s%s muvaffaqiyatsiz: %s", method, self.base_url, path, last)
        raise last  # type: ignore[misc]


def _flask_context() -> tuple[str, str]:
    """Flask so'rovi ichida chaqirilsa — joriy servis nomi va X-Request-ID (taqsimlangan iz uchun)."""
    try:
        from flask import current_app, g, has_app_context
        if has_app_context():
            return current_app.config.get("SERVICE_NAME", current_app.name), g.get("request_id", "") or ""
    except ImportError:  # pragma: no cover
        pass
    return "", ""


def _safe_json(raw: bytes) -> dict[str, Any]:
    try:
        return json.loads(raw)
    except (ValueError, TypeError):
        return {"error": raw.decode(errors="replace")[:200]}
