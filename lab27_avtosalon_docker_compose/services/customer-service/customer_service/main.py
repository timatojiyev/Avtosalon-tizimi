"""customer-service — mijozlar (o'z bazasi: customer-db).

GET /customers?q=   POST /customers   GET /customers/<id>
"""
from __future__ import annotations

import os
import re

from flask import Flask, jsonify, request

from svc_common import ApiError, Database, create_service_app, json_body

SCHEMA = """
CREATE TABLE IF NOT EXISTS customers (
  id {pk}, full_name VARCHAR(80) NOT NULL, phone VARCHAR(13) NOT NULL UNIQUE, passport VARCHAR(9) NOT NULL UNIQUE,
  monthly_income BIGINT NOT NULL DEFAULT 0 CHECK (monthly_income >= 0), created_at VARCHAR(32) NOT NULL DEFAULT '')
"""
SEED = [("Aziz Karimov", "+998901112233", "AA1234567", 25_000_000), ("Malika Yusupova", "+998935554433", "AB7654321", 14_000_000),
        ("Jasur Rahimov", "+998977778899", "AC1112223", 6_000_000)]
PHONE_RE = re.compile(r"^\+998\d{9}$")
PASSPORT_RE = re.compile(r"^[A-Z]{2}\d{7}$")


def create_app(db_url: str | None = None) -> Flask:
    db = Database(db_url or os.getenv("DATABASE_URL", "sqlite:///data/customer.db"))
    db.init_schema(SCHEMA)
    if os.getenv("SEED_DEMO_DATA", "1") == "1":
        with db.connect() as s:
            if not s.scalar("SELECT COUNT(*) AS n FROM customers"):
                for row in SEED:
                    s.execute("INSERT INTO customers (full_name, phone, passport, monthly_income) VALUES (?,?,?,?)", row)

    def register(app: Flask) -> None:
        @app.get("/customers")
        def list_customers():  # type: ignore[no-untyped-def]
            q = request.args.get("q", "").strip().lower()
            with db.connect() as s:
                rows = s.all("SELECT * FROM customers ORDER BY id DESC")
            if q:
                rows = [r for r in rows if q in r["full_name"].lower() or q in r["phone"]]
            return jsonify(rows)

        @app.post("/customers")
        def create_customer():  # type: ignore[no-untyped-def]
            d = json_body()
            name = " ".join(str(d.get("full_name", "")).split())
            phone = "+" + "".join(ch for ch in str(d.get("phone", "")) if ch.isdigit())
            passport = str(d.get("passport", "")).replace(" ", "").upper()
            errors = {}
            if len(name) < 3:
                errors["full_name"] = "F.I.Sh. kamida 3 belgi"
            if not PHONE_RE.match(phone):
                errors["phone"] = "Telefon: +998XXXXXXXXX"
            if not PASSPORT_RE.match(passport):
                errors["passport"] = "Pasport: AA1234567"
            try:
                income = int(d.get("monthly_income", 0) or 0)
                if income < 0:
                    raise ValueError
            except (TypeError, ValueError):
                errors["monthly_income"] = "Daromad musbat son"
                income = 0
            if errors:
                raise ApiError("Validatsiya xatosi", 422, fields=errors)
            with db.connect() as s:
                if s.one("SELECT id FROM customers WHERE phone = ? OR passport = ?", (phone, passport)):
                    raise ApiError("Bunday telefon yoki pasport bilan mijoz mavjud", 409)
                row = s.one("INSERT INTO customers (full_name, phone, passport, monthly_income) VALUES (?,?,?,?) RETURNING *",
                            (name, phone, passport, income))
            return jsonify(row), 201

        @app.get("/customers/<int:customer_id>")
        def get(customer_id: int):  # type: ignore[no-untyped-def]
            with db.connect() as s:
                row = s.one("SELECT * FROM customers WHERE id = ?", (customer_id,))
            if not row:
                raise ApiError(f"Mijoz #{customer_id} topilmadi", 404)
            return jsonify(row)

    return create_service_app("customer-service", db, register)
