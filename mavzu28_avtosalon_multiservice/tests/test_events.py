"""Hodisalar: Redis Streams consumer group mantig'i (FakeRedis bilan) va HTTP rejimdagi to'liq oqim."""
import json
import socket

from notification_worker.main import NotificationStore, create_app as worker_app
from svc_common.events import HttpEventBus, RedisStreamBus, make_event


class FakeRedis:
    """Redis Streams'ning kerakli qismi: xadd, xgroup_create, xreadgroup (pending + '>'), xack."""

    def __init__(self):
        self.entries, self.groups, self.seq = [], {}, 0

    def xadd(self, stream, fields, maxlen=None, approximate=True):
        self.seq += 1
        self.entries.append((f"{self.seq}-0", fields))
        return f"{self.seq}-0"

    def xgroup_create(self, stream, group, id="0", mkstream=True):
        if group in self.groups:
            raise Exception("BUSYGROUP Consumer Group name already exists")
        self.groups[group] = {"last": 0, "pending": {}}

    def xreadgroup(self, group, consumer, streams, count=20, block=0):
        g = self.groups[group]
        (stream, last_id), = streams.items()
        if last_id == "0":
            items = [(mid, f) for mid, f in self.entries if mid in g["pending"]]
        else:
            items = [(mid, f) for mid, f in self.entries if int(mid.split("-")[0]) > g["last"]][:count]
            for mid, _ in items:
                g["pending"][mid] = consumer
                g["last"] = int(mid.split("-")[0])
        return [(stream, items)] if items else []

    def xack(self, stream, group, msg_id):
        self.groups[group]["pending"].pop(msg_id, None)


def ev(t="sale.completed", **data):
    return make_event(t, "sales-service", {"ref": "S-00001", "customer_name": "Aziz", "car_title": "BYD", "price": 100, **data})


def test_consumer_group_ack_and_redelivery():
    r = FakeRedis()
    bus = RedisStreamBus(client=r)
    for e in (ev(), ev("sale.cancelled")):
        bus.publish(e)

    seen, calls = [], {"n": 0}

    def flaky(event):          # birinchi hodisada worker "qulaydi"
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("crash")
        seen.append(event["type"])

    bus.consume("g", flaky, stop=lambda: calls["n"] >= 2)
    assert seen == ["sale.cancelled"]
    assert len(r.groups["g"]["pending"]) == 1            # ack qilinmagan hodisa pending'da qoldi

    bus.consume("g", lambda e: seen.append(e["type"]), stop=lambda: len(seen) >= 2)   # qayta ishga tushish
    assert seen == ["sale.cancelled", "sale.completed"] and r.groups["g"]["pending"] == {}


def test_store_is_idempotent():
    store = NotificationStore()
    e = ev()
    assert store.handle(e) is True and store.handle(e) is False
    assert store.revenue == 100 and "BYD" in store.items[0]["text"]


def test_http_mode_full_flow(tmp_path, monkeypatch):
    """Lokal rejim: sales-service hodisani HTTP orqali worker'ga yuboradi."""
    from car_service.main import create_app as car_app
    from customer_service.main import create_app as customer_app
    from financing_service.main import create_app as fin_app
    from run_local import serve
    from sales_service.main import create_app as sales_app
    from svc_common import ServiceClient

    def port():
        s = socket.socket(); s.bind(("127.0.0.1", 0)); p = s.getsockname()[1]; s.close(); return p

    ports = {n: port() for n in ["car", "cust", "fin", "worker"]}
    worker = worker_app(start_consumer=False)
    servers = serve({"car": car_app(f"sqlite:///{tmp_path}/c.db"), "cust": customer_app(f"sqlite:///{tmp_path}/u.db"),
                     "fin": fin_app(f"sqlite:///{tmp_path}/f.db"), "worker": worker}, ports)
    try:
        url = lambda n: f"http://127.0.0.1:{ports[n]}"  # noqa: E731
        sales = sales_app(f"sqlite:///{tmp_path}/s.db", ServiceClient("car", url("car")), ServiceClient("cust", url("cust")),
                          ServiceClient("fin", url("fin")), HttpEventBus(url("worker"))).test_client()
        sale = sales.post("/sales", json={"car_id": 3, "customer_id": 1, "payment_method": "kredit", "down_payment": 80_000_000}).json
        sales.post(f"/sales/{sale['id']}/complete", json={"paid": sale["down_payment"]})
        types = [n["type"] for n in worker.test_client().get("/notifications").json]
        assert types == ["sale.completed", "sale.financing_approved", "sale.initiated"]
        assert worker.test_client().get("/stats").json["revenue"] == sale["price"]
    finally:
        for s in servers:
            s.shutdown()


def test_event_payload_is_json_serializable():
    assert json.loads(json.dumps(ev()))["type"] == "sale.completed"
