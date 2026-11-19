"""financing-service — kredit arizalari va avtomatik qaror (o'z bazasi: financing-db).

POST /applications   {sale_ref, customer_id, amount, term_months, annual_rate, monthly_income}
GET  /applications   GET /applications/<id>

Qaror qoidasi (scoring): oylik to'lov / oylik daromad (PTI) ≤ 50 % → tasdiqlanadi.
"""
from __future__ import annotations

import os
from decimal import ROUND_HALF_UP, Decimal

from flask import Flask, jsonify

from svc_common import ApiError, Database, create_service_app, json_body

SCHEMA = """
CREATE TABLE IF NOT EXISTS applications (
  id {pk}, sale_ref VARCHAR(20) NOT NULL UNIQUE, customer_id INTEGER NOT NULL, amount BIGINT NOT NULL,
  term_months INTEGER NOT NULL, annual_rate NUMERIC(5,2) NOT NULL, monthly_payment BIGINT NOT NULL,
  monthly_income BIGINT NOT NULL, pti NUMERIC(6,2) NOT NULL, status VARCHAR(20) NOT NULL, reason VARCHAR(200) NOT NULL DEFAULT '')
"""
MAX_PTI = Decimal(50)


def annuity(amount: int, annual_rate: Decimal, months: int) -> int:
    r = annual_rate / Decimal(1200)
    p = Decimal(amount) / months if r == 0 else Decimal(amount) * r / (1 - (1 + r) ** -months)
    return int(p.quantize(Decimal(1), ROUND_HALF_UP))


def decide(monthly_payment: int, income: int) -> tuple[str, Decimal, str]:
    if income <= 0:
        return "rad_etildi", Decimal(0), "Daromad ma'lumoti yo'q"
    pti = (Decimal(monthly_payment) * 100 / income).quantize(Decimal("0.01"))
    if pti <= MAX_PTI:
        return "tasdiqlandi", pti, ""
    return "rad_etildi", pti, f"Oylik to'lov daromadning {pti}% ini tashkil qiladi (ruxsat: {MAX_PTI}%)"


def create_app(db_url: str | None = None) -> Flask:
    db = Database(db_url or os.getenv("DATABASE_URL", "sqlite:///data/financing.db"))
    db.init_schema(SCHEMA)

    def register(app: Flask) -> None:
        def out(row: dict) -> dict:  # type: ignore[type-arg]
            return {**row, "annual_rate": float(row["annual_rate"]), "pti": float(row["pti"])}

        @app.post("/applications")
        def create_application():  # type: ignore[no-untyped-def]
            d = json_body()
            try:
                amount, term, income = int(d["amount"]), int(d["term_months"]), int(d.get("monthly_income", 0))
                rate = Decimal(str(d["annual_rate"]))
                sale_ref, customer_id = str(d["sale_ref"]), int(d["customer_id"])
            except (KeyError, TypeError, ValueError, ArithmeticError):
                raise ApiError("amount, term_months, annual_rate, sale_ref, customer_id majburiy", 422)
            if amount <= 0 or not 6 <= term <= 60 or not 0 <= rate <= 60:
                raise ApiError("Shartlar noto'g'ri: summa > 0, muddat 6–60 oy, foiz 0–60 %", 422)
            payment = annuity(amount, rate, term)
            status, pti, reason = decide(payment, income)
            with db.connect() as s:
                existing = s.one("SELECT * FROM applications WHERE sale_ref = ?", (sale_ref,))
                if existing:  # idempotentlik: bir sotuv uchun bitta ariza
                    return jsonify(out(existing)), 200
                row = s.one("INSERT INTO applications (sale_ref, customer_id, amount, term_months, annual_rate,"
                            " monthly_payment, monthly_income, pti, status, reason) VALUES (?,?,?,?,?,?,?,?,?,?) RETURNING *",
                            (sale_ref, customer_id, amount, term, str(rate), payment, income, str(pti), status, reason))
            return jsonify(out(row)), 201

        @app.get("/applications")
        def list_applications():  # type: ignore[no-untyped-def]
            with db.connect() as s:
                return jsonify([out(r) for r in s.all("SELECT * FROM applications ORDER BY id DESC")])

        @app.get("/applications/<int:app_id>")
        def get(app_id: int):  # type: ignore[no-untyped-def]
            with db.connect() as s:
                row = s.one("SELECT * FROM applications WHERE id = ?", (app_id,))
            if not row:
                raise ApiError("Ariza topilmadi", 404)
            return jsonify(out(row))

    return create_service_app("financing-service", db, register)
