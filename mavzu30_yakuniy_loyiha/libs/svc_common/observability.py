"""Kuzatuvchanlik (observability): metrikalar, taqsimlangan iz (tracing) va nazoratli nosozlik (chaos).

Tashqi kutubxonasiz, har bir servis jarayoni ichida ishlaydi:

* ``Metrics``  — har bir endpoint uchun so'rovlar soni, xatolar, kechikish gistogrammasi.
  ``GET /metrics`` Prometheus matn formatida, ``GET /metrics.json`` — panel uchun.
* ``Tracer``   — har bir so'rov “span” sifatida yoziladi (X-Request-ID bo'yicha bog'lanadi).
  Panel barcha servislardan ``GET /traces?request_id=…`` ni yig'ib, bitta so'rovning servislar
  bo'ylab yo'lini (waterfall) chizadi.
* ``Chaos``    — servisni ataylab “buzish” (503 yoki sekinlashtirish) — saga kompensatsiyasi va
  barqarorlikni himoyada jonli ko'rsatish uchun. Production muhitida o'chiq.
"""
from __future__ import annotations

import threading
import time
from collections import deque
from dataclasses import asdict, dataclass, field
from typing import Any

BUCKETS_MS = (5, 10, 25, 50, 100, 250, 500, 1000, 2500, 5000)


@dataclass
class RouteStats:
    count: int = 0
    errors: int = 0
    total_ms: float = 0.0
    max_ms: float = 0.0
    buckets: list[int] = field(default_factory=lambda: [0] * (len(BUCKETS_MS) + 1))

    def observe(self, ms: float, error: bool) -> None:
        self.count += 1
        self.errors += int(error)
        self.total_ms += ms
        self.max_ms = max(self.max_ms, ms)
        for i, b in enumerate(BUCKETS_MS):
            if ms <= b:
                self.buckets[i] += 1
                return
        self.buckets[-1] += 1

    def percentile(self, p: float) -> float:
        """Gistogramma bo'yicha taxminiy persentil (Prometheus histogram_quantile kabi — bucket yuqori chegarasi)."""
        if not self.count:
            return 0.0
        target, acc = self.count * p, 0
        for i, n in enumerate(self.buckets):
            acc += n
            if acc >= target:
                return float(BUCKETS_MS[i]) if i < len(BUCKETS_MS) else self.max_ms
        return self.max_ms


class Metrics:
    def __init__(self, service: str):
        self.service = service
        self._lock = threading.Lock()
        self._routes: dict[tuple[str, str], RouteStats] = {}
        self.started = time.time()

    def observe(self, method: str, route: str, status: int, ms: float) -> None:
        with self._lock:
            self._routes.setdefault((method, route), RouteStats()).observe(ms, status >= 500)

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            routes = [{"method": m, "route": r, "count": s.count, "errors": s.errors,
                       "avg_ms": round(s.total_ms / s.count, 1) if s.count else 0, "p50_ms": s.percentile(.5),
                       "p95_ms": s.percentile(.95), "max_ms": round(s.max_ms, 1)} for (m, r), s in self._routes.items()]
        total = sum(r["count"] for r in routes)
        errors = sum(r["errors"] for r in routes)
        return {"service": self.service, "uptime_s": round(time.time() - self.started), "requests": total, "errors": errors,
                "error_rate": round(errors / total * 100, 2) if total else 0.0,
                "routes": sorted(routes, key=lambda r: -r["count"])}

    def prometheus(self) -> str:
        lines = ["# HELP http_requests_total HTTP so'rovlar soni", "# TYPE http_requests_total counter"]
        with self._lock:
            items = list(self._routes.items())
        for (m, r), s in items:
            lbl = f'service="{self.service}",method="{m}",route="{r}"'
            lines.append(f"http_requests_total{{{lbl}}} {s.count}")
            lines.append(f"http_requests_errors_total{{{lbl}}} {s.errors}")
        lines += ["# HELP http_request_duration_ms So'rov davomiyligi (ms)", "# TYPE http_request_duration_ms histogram"]
        for (m, r), s in items:
            lbl = f'service="{self.service}",method="{m}",route="{r}"'
            acc = 0
            for b, n in zip((*BUCKETS_MS, "+Inf"), s.buckets):
                acc += n
                lines.append(f'http_request_duration_ms_bucket{{{lbl},le="{b}"}} {acc}')
            lines.append(f"http_request_duration_ms_sum{{{lbl}}} {round(s.total_ms, 3)}")
            lines.append(f"http_request_duration_ms_count{{{lbl}}} {s.count}")
        lines.append(f'process_uptime_seconds{{service="{self.service}"}} {round(time.time() - self.started)}')
        return "\n".join(lines) + "\n"


@dataclass
class Span:
    request_id: str
    service: str
    method: str
    path: str
    status: int
    start: float   # epoch, sekund
    ms: float
    parent: str = ""   # chaqiruvchi servis (X-Caller sarlavhasi)


class Tracer:
    def __init__(self, service: str, capacity: int = 1000):
        self.service = service
        self._spans: deque[Span] = deque(maxlen=capacity)
        self._lock = threading.Lock()

    def record(self, span: Span) -> None:
        with self._lock:
            self._spans.append(span)

    def find(self, request_id: str = "", limit: int = 50) -> list[dict[str, Any]]:
        with self._lock:
            spans = list(self._spans)
        if request_id:
            spans = [s for s in spans if s.request_id == request_id]
        return [asdict(s) for s in spans[-limit:]][::-1]


class Chaos:
    """Nazoratli nosozlik: ``mode`` = off | error | latency."""

    def __init__(self, allowed: bool):
        self.allowed = allowed
        self.mode = "off"
        self.latency_ms = 1500

    def state(self) -> dict[str, Any]:
        return {"allowed": self.allowed, "mode": self.mode, "latency_ms": self.latency_ms}

    def set(self, mode: str, latency_ms: int | None = None) -> dict[str, Any]:
        if not self.allowed:
            raise PermissionError("Chaos rejimi bu muhitda o'chirilgan (APP_ENV=production)")
        if mode not in ("off", "error", "latency"):
            raise ValueError("mode: off | error | latency")
        self.mode = mode
        if latency_ms is not None:
            self.latency_ms = max(0, min(int(latency_ms), 10_000))
        return self.state()
