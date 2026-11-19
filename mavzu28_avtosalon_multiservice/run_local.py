"""Docker'siz ishga tushirish (development): 4 servis + web bitta jarayonda, har biri o'z porti va o'z SQLite bazasi bilan.

    python run_local.py
    Panel: http://127.0.0.1:8280   Servislar: 8281 car, 8282 customer, 8283 sales, 8284 financing, 8285 worker
"""
from __future__ import annotations

import os
import sys
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
for p in ["libs", "web", "services/car-service", "services/customer-service", "services/sales-service",
          "services/financing-service", "services/notification-worker"]:
    sys.path.insert(0, str(ROOT / p))

from werkzeug.serving import make_server  # noqa: E402

PORTS = {"car-service": 8281, "customer-service": 8282, "sales-service": 8283, "financing-service": 8284,
         "notification-worker": 8285, "web": 8280}


def build_apps():  # type: ignore[no-untyped-def]
    os.environ.setdefault("LOG_FORMAT", "text")
    os.environ.update({f"{k.split('-')[0].upper()}_SERVICE_URL": f"http://127.0.0.1:{v}" for k, v in PORTS.items()
                       if k.endswith("-service")})
    os.environ.setdefault("NOTIFIER_URL", f"http://127.0.0.1:{PORTS['notification-worker']}")
    os.environ.setdefault("EVENT_BUS_URL", f"http://127.0.0.1:{PORTS['notification-worker']}")   # lokal: Redis o'rniga HTTP
    data = ROOT / "data"
    from car_service.main import create_app as car
    from customer_service.main import create_app as customer
    from financing_service.main import create_app as financing
    from sales_service.main import create_app as sales
    from avtosalon_web.main import create_app as web
    from notification_worker.main import create_app as notifier
    return {
        "car-service": car(f"sqlite:///{data / 'car.db'}"),
        "customer-service": customer(f"sqlite:///{data / 'customer.db'}"),
        "financing-service": financing(f"sqlite:///{data / 'financing.db'}"),
        "sales-service": sales(f"sqlite:///{data / 'sales.db'}"),
        "notification-worker": notifier(),
        "web": web(),
    }


def serve(apps: dict, ports: dict[str, int], host: str = "127.0.0.1") -> list:  # type: ignore[type-arg]
    servers = []
    for name, app in apps.items():
        srv = make_server(host, ports[name], app, threaded=True)
        threading.Thread(target=srv.serve_forever, name=name, daemon=True).start()
        servers.append(srv)
    return servers


def main() -> None:
    servers = serve(build_apps(), PORTS)
    print("\n  Avtosalon Tizimi (lokal rejim: SQLite + HTTP event bus, gateway'siz):")
    for name, port in PORTS.items():
        print(f"    {name:<18} http://127.0.0.1:{port}")
    print("\n  Panel: http://127.0.0.1:8280   (to'xtatish: Ctrl+C)\n")
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        for s in servers:
            s.shutdown()


if __name__ == "__main__":
    main()
