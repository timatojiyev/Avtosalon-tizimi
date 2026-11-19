"""notification-worker — hodisalar iste'molchisi (consumer).

sales-service nashr qilgan hodisalarni o'qiydi va mijozga yuboriladigan xabarlarni (SMS/email simulyatsiyasi)
hamda kunlik savdo hisobini hosil qiladi.

* Docker rejimi: Redis Streams consumer group (``notification-workers``) — bir nechta nusxa
  (``--scale notification-worker=2``) hodisalarni o'zaro bo'lishib oladi, har bir hodisa bitta nusxada ishlanadi.
* Lokal rejim: ``POST /events`` (HttpEventBus).

HTTP: GET /health, /ready, /notifications, /stats; POST /events
"""
from __future__ import annotations

import logging
import os
import socket
import threading
from collections import Counter, deque
from typing import Any

from flask import Flask, jsonify, request

from svc_common import ApiError, Database, create_service_app, json_body
from svc_common.events import RedisStreamBus

log = logging.getLogger("notification-worker")
GROUP = "notification-workers"

TEMPLATES = {
    "sale.initiated": "Hurmatli {customer_name}, {car_title} uchun sotuv {ref} rasmiylashtirildi. Avtomobil siz uchun band qilindi.",
    "sale.financing_approved": "Tabriklaymiz, {customer_name}! {ref} bo'yicha kredit tasdiqlandi. Oylik to'lov: {monthly_payment_fmt}.",
    "sale.financing_rejected": "Hurmatli {customer_name}, afsuski {ref} bo'yicha kredit tasdiqlanmadi. Menejerimiz siz bilan bog'lanadi.",
    "sale.completed": "Xaridingiz bilan, {customer_name}! {car_title} endi sizniki. Yo'llaringiz bexatar bo'lsin!",
    "sale.cancelled": "{ref} sotuvi bekor qilindi. Savollar bo'lsa: +998 71 200-00-00",
}


class NotificationStore:
    """So'nggi xabarlar (xotira) + qayta ishlangan hodisalar ID'lari (idempotentlik)."""

    def __init__(self, capacity: int = 200):
        self.items: deque[dict[str, Any]] = deque(maxlen=capacity)
        self.seen: set[str] = set()
        self.counter: Counter[str] = Counter()
        self.revenue = 0
        self._lock = threading.Lock()

    def handle(self, event: dict[str, Any]) -> bool:
        with self._lock:
            if event["id"] in self.seen:        # at-least-once yetkazishda dublikatlarni tashlab yuborish
                return False
            self.seen.add(event["id"])
            d = dict(event.get("data", {}))
            d["monthly_payment_fmt"] = f"{int(d.get('monthly_payment') or 0):,} so'm".replace(",", " ")
            template = TEMPLATES.get(event["type"])
            self.counter[event["type"]] += 1
            if event["type"] == "sale.completed":
                self.revenue += int(d.get("price") or 0)
            if template:
                self.items.appendleft({"event_id": event["id"], "type": event["type"], "at": event.get("occurred_at"),
                                       "channel": "SMS", "to": d.get("customer_name"), "ref": d.get("ref"),
                                       "text": template.format_map(_Safe(d)), "worker": socket.gethostname(),
                                       "request_id": event.get("request_id", "")})
            log.info("Hodisa qayta ishlandi: %s %s", event["type"], d.get("ref"))
            return True


class _Safe(dict):  # type: ignore[type-arg]
    def __missing__(self, key: str) -> str:
        return "—"


def create_app(bus: RedisStreamBus | None = None, start_consumer: bool = True) -> Flask:
    store = NotificationStore()
    url = os.getenv("EVENT_BUS_URL", "")
    if bus is None and url.startswith("redis://"):
        bus = RedisStreamBus(url)
    state = {"consumer": "HTTP POST /events (lokal rejim)", "stop": False}

    if bus is not None and start_consumer:
        def run() -> None:
            state["consumer"] = f"redis-streams · group={GROUP}"
            while not state["stop"]:
                try:
                    bus.consume(GROUP, store.handle, stop=lambda: state["stop"])
                except Exception:  # noqa: BLE001 — Redis vaqtincha yo'q bo'lsa qayta urinish
                    log.exception("Consumer xatosi, 3 s dan keyin qayta ulanadi")
                    threading.Event().wait(3)
        threading.Thread(target=run, name="consumer", daemon=True).start()

    db = Database("sqlite:///:memory:")  # worker'ning doimiy bazasi yo'q; /ready uchun

    def register(app: Flask) -> None:
        app.extensions["store"] = store
        app.extensions["consumer_state"] = state

        @app.post("/events")
        def receive():  # type: ignore[no-untyped-def]
            event = json_body()
            if "id" not in event or "type" not in event:
                raise ApiError("Hodisa formati noto'g'ri", 422)
            return jsonify(accepted=store.handle(event)), 202

        @app.get("/notifications")
        def notifications():  # type: ignore[no-untyped-def]
            limit = min(request.args.get("limit", 50, type=int) or 50, 200)
            return jsonify(list(store.items)[:limit])

        @app.get("/stats")
        def stats():  # type: ignore[no-untyped-def]
            return jsonify(events=dict(store.counter), processed=len(store.seen), revenue=store.revenue,
                           consumer=state["consumer"], instance=socket.gethostname())

    return create_service_app("notification-worker", db, register)
