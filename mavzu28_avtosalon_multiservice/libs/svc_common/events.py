"""Servislararo asinxron hodisalar (event bus).

* ``RedisStreamBus`` — Docker'da: Redis Streams (XADD / XREADGROUP / XACK, consumer group). Hodisa yo'qolmaydi:
  worker o'chiq bo'lsa ham stream'da qoladi, qayta ishga tushganda o'qiladi (at-least-once).
* ``HttpEventBus`` — Redis'siz lokal rejim: hodisa to'g'ridan-to'g'ri worker'ning ``POST /events`` ga yuboriladi.
* ``NullEventBus`` — hodisalar o'chirilgan.

Tanlov ``EVENT_BUS_URL`` muhit o'zgaruvchisi orqali: ``redis://redis:6379/0`` | ``http://...`` | bo'sh.
"""
from __future__ import annotations

import json
import logging
import os
import socket
import uuid
from datetime import datetime, timezone
from typing import Any, Callable

log = logging.getLogger("svc.events")
STREAM = os.getenv("EVENT_STREAM", "avtosalon.events")


def make_event(event_type: str, source: str, data: dict[str, Any], request_id: str = "") -> dict[str, Any]:
    return {"id": uuid.uuid4().hex, "type": event_type, "source": source, "request_id": request_id,
            "occurred_at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "data": data}


class EventBus:
    name = "null"

    def publish(self, event: dict[str, Any]) -> None:  # pragma: no cover - interfeys
        raise NotImplementedError


class NullEventBus(EventBus):
    def publish(self, event: dict[str, Any]) -> None:
        log.debug("Hodisa (o'chirilgan bus): %s", event["type"])


class HttpEventBus(EventBus):
    name = "http"

    def __init__(self, url: str):
        from svc_common.http import ServiceClient
        self._client = ServiceClient("event-bus", url, timeout=2, retries=0)

    def publish(self, event: dict[str, Any]) -> None:
        try:
            self._client.post("/events", event)
        except Exception as exc:  # noqa: BLE001 — hodisa yuborilmasa ham asosiy amal to'xtamaydi
            log.warning("Hodisa yuborilmadi (%s): %s", event["type"], exc)


class RedisStreamBus(EventBus):
    name = "redis-streams"

    def __init__(self, url: str | None = None, client: Any = None, stream: str = STREAM, maxlen: int = 10_000):
        if client is None:
            import redis
            client = redis.Redis.from_url(url, decode_responses=True, socket_timeout=3)
        self.r, self.stream, self.maxlen = client, stream, maxlen

    def publish(self, event: dict[str, Any]) -> None:
        try:
            self.r.xadd(self.stream, {"type": event["type"], "payload": json.dumps(event, ensure_ascii=False)},
                        maxlen=self.maxlen, approximate=True)
        except Exception as exc:  # noqa: BLE001
            log.warning("Redis'ga hodisa yozilmadi (%s): %s", event["type"], exc)

    # ----------------------- consumer tomoni -----------------------
    def ensure_group(self, group: str) -> None:
        try:
            self.r.xgroup_create(self.stream, group, id="0", mkstream=True)
        except Exception as exc:  # noqa: BLE001 — BUSYGROUP: guruh allaqachon bor
            if "BUSYGROUP" not in str(exc):
                raise

    def consume(self, group: str, handler: Callable[[dict[str, Any]], None], consumer: str | None = None,
                block_ms: int = 5000, count: int = 20, stop: Callable[[], bool] = lambda: False) -> None:
        """Consumer group orqali o'qish. Avval o'zining tasdiqlanmagan (pending) xabarlari, keyin yangilari."""
        consumer = consumer or socket.gethostname()
        self.ensure_group(group)
        last_id = "0"                      # 0 — pending (qulab qolgan paytdan qolganlar), keyin ">" — yangilari
        while not stop():
            resp = self.r.xreadgroup(group, consumer, {self.stream: last_id}, count=count, block=block_ms)
            entries = resp[0][1] if resp else []
            for msg_id, fields in entries:
                try:
                    handler(json.loads(fields["payload"]))
                    self.r.xack(self.stream, group, msg_id)
                except Exception:  # noqa: BLE001 — ack qilinmaydi, keyingi ishga tushishda qayta o'qiladi
                    log.exception("Hodisani qayta ishlashda xato: %s", msg_id)
            if last_id == "0":
                last_id = ">"      # pending bir marta qayta ko'rildi — endi faqat yangi xabarlar ("zaharli" xabarda aylanib qolmaslik)


def bus_from_env() -> EventBus:
    url = os.getenv("EVENT_BUS_URL", "")
    if url.startswith("redis://"):
        return RedisStreamBus(url)
    if url.startswith("http"):
        return HttpEventBus(url)
    return NullEventBus()
