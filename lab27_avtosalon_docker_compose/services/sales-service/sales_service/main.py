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
import uuid
from datetime import datetime, timezone

from flask import Flask, g, jsonify, request

from svc_common import ApiError, Database, ServiceClient, create_service_app, json_body

log = logging.getLogger("sales-service")
SCHEMA = """
CREATE TABLE IF NOT EXISTS sales (
  id {pk}, ref VARCHAR(20) NOT NULL UNIQUE, car_id INTEGER NOT NULL, car_title VARCHAR(100) NOT NULL,
  customer_id INTEGER NOT NULL, customer_name VARCHAR(80) NOT NULL, payment_method VARCHAR(10) NOT NULL,
  price BIGINT NOT NULL, down_payment BIGINT NOT NULL, financed_amount BIGINT NOT NULL DEFAULT 0,
  application_id INTEGER, monthly_payment BIGINT, status VARCHAR(25) NOT NULL, note VARCHAR(200) NOT NULL DEFAULT '',
  amount_paid BIGINT NOT NULL DEFAULT 0, created_at VARCHAR(32) NOT NULL, updated_at VARCHAR(32) NOT NULL)
"""
MIN_DOWN_PCT = 20


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def create_app(db_url: str | None = None, cars: ServiceClient | None = None, customers: ServiceClient | None = None,
               financing: ServiceClient | None = None) -> Flask:
    db = Database(db_url or os.getenv("DATABASE_URL", "sqlite:///data/sales.db"))
    db.init_schema(SCHEMA)
    cars = cars or ServiceClient("car-service", os.getenv("CAR_SERVICE_URL", "http://localhost:8001"))
    customers = customers or ServiceClient("customer-service", os.getenv("CUSTOMER_SERVICE_URL", "http://localhost:8002"))
    financing = financing or ServiceClient("financing-service", os.getenv("FINANCING_SERVICE_URL", "http://localhost:8004"))

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

            customer = customers.get(f"/customers/{customer_id}", rid)
            car = cars.get(f"/cars/{car_id}", rid)
            price = int(car["price"])
            down = price
            if method == "kredit":
                down = int(d.get("down_payment") or 0)
                if down * 100 < price * MIN_DOWN_PCT or down >= price:
                    raise ApiError(f"Boshlang'ich to'lov narxning {MIN_DOWN_PCT}% idan kam bo'lmasin va narxdan kichik bo'lsin "
                                   f"(kamida {price * MIN_DOWN_PCT // 100:,} so'm)".replace(",", " "), 422)

            cars.post(f"/cars/{car_id}/reserve", request_id=rid)        # 409 bo'lsa — xato yuqoriga uzatiladi
            sale = None
            try:
                with db.connect() as s:
                    sale = s.one(
                        "INSERT INTO sales (ref, car_id, car_title, customer_id, customer_name, payment_method, price,"
                        " down_payment, financed_amount, status, created_at, updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?) RETURNING *",
                        (uuid.uuid4().hex[:20], car_id, f"{car['make']} {car['model']} ({car['year']})", customer_id, customer["full_name"],
                         method, price, down, price - down, "boshlangan", _now(), _now()))
                    sale = s.one("UPDATE sales SET ref = ? WHERE id = ? RETURNING *", (f"S-{sale['id']:05d}", sale["id"]))
                if method == "kredit":
                    application = financing.post("/applications", {
                        "sale_ref": sale["ref"], "customer_id": customer_id, "amount": price - down,
                        "term_months": int(d.get("term_months", 36)), "annual_rate": d.get("annual_rate", 24),
                        "monthly_income": customer.get("monthly_income", 0)}, rid)
                    approved = application["status"] == "tasdiqlandi"
                    with db.connect() as s:
                        sale = s.one("UPDATE sales SET application_id = ?, monthly_payment = ?, status = ?, note = ?, updated_at = ?"
                                     " WHERE id = ? RETURNING *",
                                     (application["id"], application["monthly_payment"],
                                      "kredit_tasdiqlangan" if approved else "kredit_rad_etilgan", application.get("reason", ""),
                                      _now(), sale["id"]))
            except Exception:
                log.warning("Sotuv yaratilmadi — kompensatsiya: avtomobil #%s bo'shatiladi", car_id)
                if sale:
                    with db.connect() as s:
                        s.execute("UPDATE sales SET status = 'bekor_qilingan', note = ?, updated_at = ? WHERE id = ?",
                                  ("Avtomatik bekor: bog'liq servis xatosi (kompensatsiya)", _now(), sale["id"]))
                try:
                    cars.post(f"/cars/{car_id}/release", request_id=rid)
                except Exception:  # noqa: BLE001
                    log.exception("Kompensatsiya bajarilmadi — avtomobil #%s qo'lda bo'shatilishi kerak", car_id)
                raise
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
            cars.post(f"/cars/{sale['car_id']}/sell", request_id=g.request_id)
            with db.connect() as s:
                sale = s.one("UPDATE sales SET status = 'yakunlangan', amount_paid = ?, updated_at = ? WHERE id = ? RETURNING *",
                             (paid, _now(), sale_id))
            return jsonify(sale)

        @app.post("/sales/<int:sale_id>/cancel")
        def cancel(sale_id: int):  # type: ignore[no-untyped-def]
            d = request.get_json(silent=True) or {}
            with db.connect() as s:
                sale = get_sale(s, sale_id)
            if sale["status"] in ("yakunlangan", "bekor_qilingan"):
                raise ApiError("Yakunlangan yoki bekor qilingan sotuvni bekor qilib bo'lmaydi", 409)
            cars.post(f"/cars/{sale['car_id']}/release", request_id=g.request_id)
            with db.connect() as s:
                sale = s.one("UPDATE sales SET status = 'bekor_qilingan', note = ?, updated_at = ? WHERE id = ? RETURNING *",
                             (str(d.get("reason", ""))[:200], _now(), sale_id))
            return jsonify(sale)

        @app.get("/stats")
        def stats():  # type: ignore[no-untyped-def]
            with db.connect() as s:
                rows = s.all("SELECT status, COUNT(*) AS n, SUM(price) AS total FROM sales GROUP BY status")
            return jsonify({r["status"]: {"count": r["n"], "value": int(r["total"] or 0)} for r in rows})

    return create_service_app("sales-service", db, register)
