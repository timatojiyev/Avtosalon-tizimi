"""car-service — avtomobillar ombori (o'z bazasi: car-db).

Endpoint'lar:
  GET  /cars?status=          ro'yxat
  POST /cars                  yangi avtomobil
  GET  /cars/<id>
  POST /cars/<id>/reserve     sotuv boshlanganda (faqat 'sotuvda' → 'band')
  POST /cars/<id>/release     sotuv bekor bo'lsa ('band' → 'sotuvda')
  POST /cars/<id>/sell        sotuv yakunlanganda ('band' → 'sotilgan')
"""
from __future__ import annotations

import os
import re

from flask import Flask, jsonify, request

from svc_common import ApiError, Database, create_service_app, json_body

SCHEMA = """
CREATE TABLE IF NOT EXISTS cars (
  id {pk}, vin VARCHAR(17) NOT NULL UNIQUE, make VARCHAR(40) NOT NULL, model VARCHAR(40) NOT NULL,
  year INTEGER NOT NULL, price BIGINT NOT NULL CHECK (price > 0), color VARCHAR(30) NOT NULL DEFAULT '',
  status VARCHAR(20) NOT NULL DEFAULT 'sotuvda');
CREATE INDEX IF NOT EXISTS ix_cars_status ON cars (status)
"""
SEED = [
    ("XWBJA11CVPN000101", "Chevrolet", "Cobalt", 2025, 165_000_000, "Oq"),
    ("XWBJA11CVPN000102", "Chevrolet", "Onix", 2025, 198_000_000, "Kulrang"),
    ("XWBJA11CVPN000103", "Chevrolet", "Tracker", 2025, 265_000_000, "Qora"),
    ("LGWEF4A51RF000104", "BYD", "Song Plus", 2025, 420_000_000, "Ko'k"),
    ("LGWEF4A51RF000105", "BYD", "Chazor", 2024, 310_000_000, "Oq"),
    ("KMHL341CBRA000106", "Kia", "K5", 2024, 385_000_000, "Qizil"),
    ("XWBJA11CVPN000107", "Chevrolet", "Malibu 2", 2025, 395_000_000, "Qora"),
    ("WBA11AA0XRCN00108", "BMW", "X5", 2024, 1_350_000_000, "Oq"),
]
VIN_RE = re.compile(r"^[A-HJ-NPR-Z0-9]{17}$")
TRANSITIONS = {"reserve": ("sotuvda", "band"), "release": ("band", "sotuvda"), "sell": ("band", "sotilgan")}


def create_app(db_url: str | None = None) -> Flask:
    db = Database(db_url or os.getenv("DATABASE_URL", "sqlite:///data/car.db"))
    db.init_schema(SCHEMA)
    if os.getenv("SEED_DEMO_DATA", "1") == "1":
        with db.connect() as s:
            if not s.scalar("SELECT COUNT(*) AS n FROM cars"):
                for row in SEED:
                    s.execute("INSERT INTO cars (vin, make, model, year, price, color) VALUES (?,?,?,?,?,?)", row)

    def register(app: Flask) -> None:
        def get_car(s, car_id: int) -> dict:  # type: ignore[no-untyped-def]
            car = s.one("SELECT * FROM cars WHERE id = ?", (car_id,))
            if not car:
                raise ApiError(f"Avtomobil #{car_id} topilmadi", 404)
            return car

        @app.get("/cars")
        def list_cars():  # type: ignore[no-untyped-def]
            status = request.args.get("status")
            with db.connect() as s:
                if status:
                    return jsonify(s.all("SELECT * FROM cars WHERE status = ? ORDER BY id", (status,)))
                return jsonify(s.all("SELECT * FROM cars ORDER BY id"))

        @app.post("/cars")
        def create_car():  # type: ignore[no-untyped-def]
            d = json_body()
            vin = str(d.get("vin", "")).strip().upper()
            errors = {}
            if not VIN_RE.match(vin):
                errors["vin"] = "VIN 17 belgi bo'lishi kerak (I, O, Q harflarisiz)"
            if not str(d.get("make", "")).strip() or not str(d.get("model", "")).strip():
                errors["model"] = "Marka va model majburiy"
            try:
                year, price = int(d.get("year", 0)), int(d.get("price", 0))
                if not 1990 <= year <= 2030:
                    errors["year"] = "Yil 1990–2030"
                if price <= 0:
                    errors["price"] = "Narx musbat bo'lsin"
            except (TypeError, ValueError):
                errors["price"] = "Yil va narx son bo'lishi kerak"
            if errors:
                raise ApiError("Validatsiya xatosi", 422, fields=errors)
            with db.connect() as s:
                if s.one("SELECT id FROM cars WHERE vin = ?", (vin,)):
                    raise ApiError("Bu VIN allaqachon mavjud", 409)
                row = s.one("INSERT INTO cars (vin, make, model, year, price, color) VALUES (?,?,?,?,?,?) RETURNING *",
                            (vin, d["make"].strip(), d["model"].strip(), year, price, str(d.get("color", "")).strip()))
            return jsonify(row), 201

        @app.get("/cars/<int:car_id>")
        def get(car_id: int):  # type: ignore[no-untyped-def]
            with db.connect() as s:
                return jsonify(get_car(s, car_id))

        @app.post("/cars/<int:car_id>/<action>")
        def transition(car_id: int, action: str):  # type: ignore[no-untyped-def]
            if action not in TRANSITIONS:
                raise ApiError("Noma'lum amal", 404)
            frm, to = TRANSITIONS[action]
            with db.connect() as s:
                car = get_car(s, car_id)
                # Shartli UPDATE — bir vaqtda ikki sotuv bir avtomobilni band qila olmaydi (race condition)
                updated = s.execute("UPDATE cars SET status = ? WHERE id = ? AND status = ?", (to, car_id, frm)).rowcount
                if not updated:
                    raise ApiError(f"Amal bajarilmadi: avtomobil holati “{car['status']}”, kerak “{frm}”", 409)
                return jsonify(get_car(s, car_id))

        @app.get("/stats")
        def stats():  # type: ignore[no-untyped-def]
            with db.connect() as s:
                rows = s.all("SELECT status, COUNT(*) AS n, SUM(price) AS total FROM cars GROUP BY status")
            return jsonify({r["status"]: {"count": r["n"], "value": int(r["total"] or 0)} for r in rows})

    return create_service_app("car-service", db, register)
