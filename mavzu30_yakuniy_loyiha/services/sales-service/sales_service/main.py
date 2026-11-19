"""sales-service — sotuvlar (o'z bazasi: sales-db). Boshqa servislar bilan faqat HTTP API orqali gaplashadi.

POST /sales                     {car_id, customer_id, payment_method: naqd|kredit, down_payment, term_months, annual_rate}
GET  /sales  GET /sales/<id>
POST /sales/<id>/complete       {paid}
POST /sales/<id>/cancel         {reason}

Sotuvni boshlash — kichik saga:
  1) customer-service: mijoz bormi   2) car-service: avtomobilni band qilish
  3) sales-db: sotuv yozuvi          4) kredit bo'lsa financing-service: ariza va qaror
  Xato bo'lsa — kompensatsiya: avtomobil band'dan chiqariladi (release).
"""
from __future__ import annotations

import logging
import os
import time
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone

from flask import Flask, g, jsonify, request
from typing import Iterator

from svc_common import (ApiError, Database, EventBus, ServiceClient, ServiceUnavailable, bus_from_env, create_service_app, json_body,
                        make_event)

log = logging.getLogger("sales-service")
SCHEMA = """
CREATE TABLE IF NOT EXISTS sales (
  id {pk}, ref VARCHAR(20) NOT NULL UNIQUE, car_id INTEGER NOT NULL, car_title VARCHAR(100) NOT NULL,
  customer_id INTEGER NOT NULL, customer_name VARCHAR(80) NOT NULL, payment_method VARCHAR(10) NOT NULL,
  price BIGINT NOT NULL, down_payment BIGINT NOT NULL, financed_amount BIGINT NOT NULL DEFAULT 0,
  application_id INTEGER, monthly_payment BIGINT, status VARCHAR(25) NOT NULL, note VARCHAR(200) NOT NULL DEFAULT '',
  amount_paid BIGINT NOT NULL DEFAULT 0, created_at VARCHAR(32) NOT NULL, updated_at VARCHAR(32) NOT NULL,
  request_id VARCHAR(40) NOT NULL DEFAULT '');
CREATE TABLE IF NOT EXISTS saga_steps (
  id {pk}, sale_id INTEGER, request_id VARCHAR(40) NOT NULL, step VARCHAR(40) NOT NULL, service VARCHAR(30) NOT NULL,
  outcome VARCHAR(12) NOT NULL, detail VARCHAR(200) NOT NULL DEFAULT '', ms INTEGER NOT NULL DEFAULT 0, at VARCHAR(32) NOT NULL);
CREATE INDEX IF NOT EXISTS ix_saga_request ON saga_steps (request_id)
"""
MIGRATIONS = ["ALTER TABLE sales ADD COLUMN request_id VARCHAR(40) NOT NULL DEFAULT ''"]   # eski lokal bazalar uchun
MIN_DOWN_PCT = 20


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def create_app(db_url: str | None = None, cars: ServiceClient | None = None, customers: ServiceClient | None = None,
               financing: ServiceClient | None = None, bus: EventBus | None = None) -> Flask:
    db = Database(db_url or os.getenv("DATABASE_URL", "sqlite:///data/sales.db"))
    for stmt in MIGRATIONS:
        try:
            with db.connect() as s:
                s.execute(stmt)
        except Exception:  # noqa: BLE001 — ustun allaqachon bor
            pass
    db.init_schema(SCHEMA)
    cars = cars or ServiceClient("car-service", os.getenv("CAR_SERVICE_URL", "http://localhost:8001"))
    customers = customers or ServiceClient("customer-service", os.getenv("CUSTOMER_SERVICE_URL", "http://localhost:8002"))
    financing = financing or ServiceClient("financing-service", os.getenv("FINANCING_SERVICE_URL", "http://localhost:8004"))
    bus = bus or bus_from_env()

    def emit(event_type: str, sale: dict) -> None:  # type: ignore[type-arg]
        """Holat o'zgarishi haqida hodisa (notification-worker va boshqa obunachilar uchun)."""
        bus.publish(make_event(event_type, "sales-service", {
            k: sale.get(k) for k in ("id", "ref", "car_id", "car_title", "customer_id", "customer_name", "payment_method",
                                     "price", "down_payment", "monthly_payment", "status", "note")}, g.get("request_id", "")))

    @contextmanager
    def step(name: str, service: str, sale_ref: list) -> Iterator[dict]:  # type: ignore[type-arg]
        """Saga qadamini jurnalga yozadi (muvaffaqiyat/xato, davomiylik) — panelda “Saga izi” sifatida ko'rinadi."""
        info: dict = {"detail": ""}  # type: ignore[type-arg]
        t0 = time.perf_counter()
        outcome = "ok"
        try:
            yield info
        except Exception as e:
            outcome, info["detail"] = "xato", str(e)[:200]
            raise
        finally:
            ms = int((time.perf_counter() - t0) * 1000)
            try:
                with db.connect() as s:
                    row = s.one("INSERT INTO saga_steps (sale_id, request_id, step, service, outcome, detail, ms, at)"
                                " VALUES (?,?,?,?,?,?,?,?) RETURNING id", (sale_ref[0], g.request_id, name, service,
                                                                           info.get("outcome", outcome), info["detail"], ms, _now()))
                if sale_ref[0] is None and len(sale_ref) > 1 and row:
                    sale_ref[1].append(row["id"])      # sotuv yozuvi hali yo'q — keyin bog'lanadi
            except Exception:  # noqa: BLE001 — jurnal biznes oqimni buzmasin
                log.exception("Saga jurnaliga yozib bo'lmadi")

    def register(app: Flask) -> None:
        def get_sale(s, sale_id: int) -> dict:  # type: ignore[no-untyped-def]
            row = s.one("SELECT * FROM sales WHERE id = ?", (sale_id,))
            if not row:
                raise ApiError(f"Sotuv #{sale_id} topilmadi", 404)
            return row

        @app.post("/sales")
        def create_sale():  # type: ignore[no-untyped-def]
            d, rid = json_body(), g.request_id
            method = d.get("payment_method", "naqd")
            if method not in ("naqd", "kredit"):
                raise ApiError("payment_method: naqd yoki kredit", 422)
            try:
                car_id, customer_id = int(d["car_id"]), int(d["customer_id"])
            except (KeyError, TypeError, ValueError):
                raise ApiError("car_id va customer_id majburiy", 422)

            sid: list = [None, []]      # [sale_id, sotuvdan oldingi qadamlar id'lari]
            with step("Mijozni tekshirish", "customer-service", sid) as st:
                customer = customers.get(f"/customers/{customer_id}", rid)
                st["detail"] = customer["full_name"]
            with step("Avtomobilni olish", "car-service", sid) as st:
                car = cars.get(f"/cars/{car_id}", rid)
                st["detail"] = f"{car['make']} {car['model']} — {car['status']}"
            price = int(car["price"])
            down = price
            if method == "kredit":
                down = int(d.get("down_payment") or 0)
                if down * 100 < price * MIN_DOWN_PCT or down >= price:
                    raise ApiError(f"Boshlang'ich to'lov narxning {MIN_DOWN_PCT}% idan kam bo'lmasin va narxdan kichik bo'lsin "
                                   f"(kamida {price * MIN_DOWN_PCT // 100:,} so'm)".replace(",", " "), 422)

            with step("Avtomobilni band qilish", "car-service", sid) as st:
                cars.post(f"/cars/{car_id}/reserve", request_id=rid)        # 409 bo'lsa — xato yuqoriga uzatiladi
                st["detail"] = "sotuvda → band"
            sale = None
            try:
                with step("Sotuv yozuvini yaratish", "sales-service", sid) as st:
                    with db.connect() as s:
                        sale = s.one(
                            "INSERT INTO sales (ref, car_id, car_title, customer_id, customer_name, payment_method, price,"
                            " down_payment, financed_amount, status, created_at, updated_at, request_id)"
                            " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?) RETURNING *",
                            (uuid.uuid4().hex[:20], car_id, f"{car['make']} {car['model']} ({car['year']})", customer_id,
                             customer["full_name"], method, price, down, price - down, "boshlangan", _now(), _now(), rid))
                        sale = s.one("UPDATE sales SET ref = ? WHERE id = ? RETURNING *", (f"S-{sale['id']:05d}", sale["id"]))
                        for step_id in sid[1]:
                            s.execute("UPDATE saga_steps SET sale_id = ? WHERE id = ?", (sale["id"], step_id))
                    sid[0] = sale["id"]
                    st["detail"] = sale["ref"]
                if method == "kredit":
                    with step("Kredit qarori", "financing-service", sid) as st:
                        application = financing.post("/applications", {
                            "sale_ref": sale["ref"], "customer_id": customer_id, "amount": price - down,
                            "term_months": int(d.get("term_months", 36)), "annual_rate": d.get("annual_rate", 24),
                            "monthly_income": customer.get("monthly_income", 0)}, rid)
                        approved = application["status"] == "tasdiqlandi"
                        st["detail"] = f"{application['status']} · PTI {application['pti']}%"
                        if not approved:
                            st["outcome"] = "rad"
                    with db.connect() as s:
                        sale = s.one("UPDATE sales SET application_id = ?, monthly_payment = ?, status = ?, note = ?, updated_at = ?"
                                     " WHERE id = ? RETURNING *",
                                     (application["id"], application["monthly_payment"],
                                      "kredit_tasdiqlangan" if approved else "kredit_rad_etilgan", application.get("reason", ""),
                                      _now(), sale["id"]))
            except Exception as e:
                log.warning("Sotuv yaratilmadi — kompensatsiya: avtomobil #%s bo'shatiladi", car_id)
                if sale:
                    with db.connect() as s:
                        s.execute("UPDATE sales SET status = 'bekor_qilingan', note = ?, updated_at = ? WHERE id = ?",
                                  ("Avtomatik bekor: bog'liq servis xatosi (kompensatsiya)", _now(), sale["id"]))
                try:
                    with step("KOMPENSATSIYA: avtomobilni bo'shatish", "car-service", sid) as st:
                        cars.post(f"/cars/{car_id}/release", request_id=rid)
                        st["detail"] = "band → sotuvda"
                        st["outcome"] = "kompensatsiya"
                except Exception:  # noqa: BLE001
                    log.exception("Kompensatsiya bajarilmadi — avtomobil #%s qo'lda bo'shatilishi kerak", car_id)
                    raise
                if isinstance(e, ServiceUnavailable):
                    raise ApiError(f"{e}. Sotuv bekor qilindi, avtomobil qayta sotuvga chiqarildi (saga kompensatsiyasi)", 503) from e
                raise
            emit("sale.initiated", sale)
            if method == "kredit":
                emit("sale.financing_approved" if sale["status"] == "kredit_tasdiqlangan" else "sale.financing_rejected", sale)
            return jsonify(sale), 201

        @app.get("/sales")
        def list_sales():  # type: ignore[no-untyped-def]
            status = request.args.get("status")
            with db.connect() as s:
                if status:
                    return jsonify(s.all("SELECT * FROM sales WHERE status = ? ORDER BY id DESC", (status,)))
                return jsonify(s.all("SELECT * FROM sales ORDER BY id DESC"))

        @app.get("/sales/<int:sale_id>")
        def get(sale_id: int):  # type: ignore[no-untyped-def]
            with db.connect() as s:
                return jsonify(get_sale(s, sale_id))

        @app.post("/sales/<int:sale_id>/complete")
        def complete(sale_id: int):  # type: ignore[no-untyped-def]
            d = json_body()
            with db.connect() as s:
                sale = get_sale(s, sale_id)
            allowed = "boshlangan" if sale["payment_method"] == "naqd" else "kredit_tasdiqlangan"
            if sale["status"] != allowed:
                raise ApiError(f"“{sale['status']}” holatidagi sotuvni yakunlab bo'lmaydi", 409)
            paid = int(d.get("paid") or 0)
            if paid < sale["down_payment"]:
                raise ApiError(f"To'lov yetarli emas: kerak {sale['down_payment']:,} so'm".replace(",", " "), 422)
            with step("Yakunlash: avtomobil sotildi", "car-service", [sale_id]) as st:
                cars.post(f"/cars/{sale['car_id']}/sell", request_id=g.request_id)
                st["detail"] = f"band → sotilgan · to'lov {paid:,} so'm".replace(",", " ")
            with db.connect() as s:
                sale = s.one("UPDATE sales SET status = 'yakunlangan', amount_paid = ?, updated_at = ? WHERE id = ? RETURNING *",
                             (paid, _now(), sale_id))
            emit("sale.completed", sale)
            return jsonify(sale)

        @app.post("/sales/<int:sale_id>/cancel")
        def cancel(sale_id: int):  # type: ignore[no-untyped-def]
            d = request.get_json(silent=True) or {}
            with db.connect() as s:
                sale = get_sale(s, sale_id)
            if sale["status"] in ("yakunlangan", "bekor_qilingan"):
                raise ApiError("Yakunlangan yoki bekor qilingan sotuvni bekor qilib bo'lmaydi", 409)
            with step("Bekor qilish: avtomobilni bo'shatish", "car-service", [sale_id]) as st:
                cars.post(f"/cars/{sale['car_id']}/release", request_id=g.request_id)
                st["detail"] = "band → sotuvda"
            with db.connect() as s:
                sale = s.one("UPDATE sales SET status = 'bekor_qilingan', note = ?, updated_at = ? WHERE id = ? RETURNING *",
                             (str(d.get("reason", ""))[:200], _now(), sale_id))
            emit("sale.cancelled", sale)
            return jsonify(sale)

        @app.get("/sales/<int:sale_id>/saga")
        def saga(sale_id: int):  # type: ignore[no-untyped-def]
            """Sotuv sagasining qadamlari (qaysi servis, natija, davomiylik)."""
            with db.connect() as s:
                sale = get_sale(s, sale_id)
                return jsonify({"sale_id": sale_id, "request_id": sale.get("request_id", ""),
                                "steps": s.all("SELECT step, service, outcome, detail, ms, at FROM saga_steps"
                                               " WHERE sale_id = ? ORDER BY id", (sale_id,))})

        @app.get("/stats")
        def stats():  # type: ignore[no-untyped-def]
            with db.connect() as s:
                rows = s.all("SELECT status, COUNT(*) AS n, SUM(price) AS total FROM sales GROUP BY status")
            return jsonify({r["status"]: {"count": r["n"], "value": int(r["total"] or 0)} for r in rows})

    return create_service_app("sales-service", db, register)
