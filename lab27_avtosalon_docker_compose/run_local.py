"""Docker'siz ishga tushirish (development): 4 servis + web bitta jarayonda, har biri o'z porti va o'z SQLite bazasi bilan.

    python run_local.py
    Panel: http://127.0.0.1:8270   Servislar: 8271 car, 8272 customer, 8273 sales, 8274 financing
"""
from __future__ import annotations

import os
import sys
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
for p in ["libs", "web", "services/car-service", "services/customer-service", "services/sales-service",
          "services/financing-service"]:
    sys.path.insert(0, str(ROOT / p))

from werkzeug.serving import make_server  # noqa: E402

PORTS = {"car-service": 8271, "customer-service": 8272, "sales-service": 8273, "financing-service": 8274, "web": 8270}


def build_apps():  # type: ignore[no-untyped-def]
    os.environ.setdefault("LOG_FORMAT", "text")
    os.environ.update({f"{k.split('-')[0].upper()}_SERVICE_URL": f"http://127.0.0.1:{v}" for k, v in PORTS.items() if k != "web"})
    data = ROOT / "data"
    from car_service.main import create_app as car
    from customer_service.main import create_app as customer
    from financing_service.main import create_app as financing
    from sales_service.main import create_app as sales
    from avtosalon_web.main import create_app as web
    return {
        "car-service": car(f"sqlite:///{data / 'car.db'}"),
        "customer-service": customer(f"sqlite:///{data / 'customer.db'}"),
        "financing-service": financing(f"sqlite:///{data / 'financing.db'}"),
        "sales-service": sales(f"sqlite:///{data / 'sales.db'}"),
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
    print("\n  Avtosalon Tizimi (lokal rejim, SQLite):")
    for name, port in PORTS.items():
        print(f"    {name:<18} http://127.0.0.1:{port}")
    print("\n  Panel: http://127.0.0.1:8270   (to'xtatish: Ctrl+C)\n")
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        for s in servers:
            s.shutdown()


if __name__ == "__main__":
    main()
