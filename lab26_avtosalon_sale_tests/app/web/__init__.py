"""Avtosalon — web interfeys (Flask): sotuv jarayoni va testlarni brauzerdan ishga tushirish."""
from __future__ import annotations

import os
import secrets
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

from flask import Flask, abort, flash, jsonify, redirect, render_template, request, session, url_for

from app.application.sales_service import SalesService
from app.domain import MIN_DOWN_PAYMENT_PCT, CarStatus, DomainError, PaymentMethod, SaleStatus
from app.infrastructure.memory import InMemoryCarRepository, InMemoryEventBus, InMemorySaleRepository

PROJECT_ROOT = Path(__file__).resolve().parents[2]
FLOW = [SaleStatus.INITIATED, SaleStatus.FINANCING_PENDING, SaleStatus.FINANCING_APPROVED, SaleStatus.COMPLETED]
STATUS_STYLE = {"boshlangan": "info", "kredit_kutilmoqda": "warning", "kredit_tasdiqlangan": "accent",
                "kredit_rad_etilgan": "danger", "yakunlangan": "success", "bekor_qilingan": ""}
CAR_STYLE = {CarStatus.AVAILABLE: "success", CarStatus.RESERVED: "warning", CarStatus.SOLD: ""}


def run_pytest(selection: str) -> dict[str, Any]:
    """pytest'ni alohida jarayonda ishga tushiradi, JUnit XML natijasini o'qiydi; pytest-cov bo'lsa — coverage."""
    targets = {"sale": ["tests/unit/test_domain/test_sale.py"], "all": ["tests"]}[selection]
    with tempfile.TemporaryDirectory() as tmp:
        xml_path, cov_path = Path(tmp) / "r.xml", Path(tmp) / "cov.json"
        cmd = [sys.executable, "-m", "pytest", *targets, "-q", "-p", "no:cacheprovider", f"--junitxml={xml_path}"]
        has_cov = subprocess.run([sys.executable, "-c", "import pytest_cov"], capture_output=True).returncode == 0
        if has_cov:
            cmd += ["--cov=app", f"--cov-report=json:{cov_path}", "--cov-config=.coveragerc"]
        proc = subprocess.run(cmd, cwd=PROJECT_ROOT, capture_output=True, text=True, timeout=120)
        cases: list[dict[str, Any]] = []
        if xml_path.exists():
            for tc in ET.parse(xml_path).getroot().iter("testcase"):
                failure = tc.find("failure")
                if failure is None:
                    failure = tc.find("error")
                skipped = tc.find("skipped")
                parts = (tc.get("classname") or "").split(".")
                module = next((p for p in reversed(parts) if p.startswith("test_")), "")
                klass = parts[-1] if parts and parts[-1].startswith("Test") else ""
                cases.append({"file": module, "group": klass, "name": tc.get("name"),
                              "time": float(tc.get("time", 0)),
                              "status": "failed" if failure is not None else "skipped" if skipped is not None else "passed",
                              "message": (failure.get("message") if failure is not None else "") or ""})
        coverage = None
        if cov_path.exists():
            import json
            data = json.loads(cov_path.read_text())
            coverage = {"total": round(data["totals"]["percent_covered"], 1),
                        "files": sorted(((f, round(v["summary"]["percent_covered"], 1)) for f, v in data["files"].items()))}
    groups: dict[str, list[dict[str, Any]]] = {}
    for c in cases:
        groups.setdefault(f"{c['file']}.py" + (f" › {c['group']}" if c["group"] else ""), []).append(c)
    return {"cases": cases, "groups": groups, "passed": sum(c["status"] == "passed" for c in cases),
            "failed": sum(c["status"] == "failed" for c in cases), "skipped": sum(c["status"] == "skipped" for c in cases),
            "duration": round(sum(c["time"] for c in cases), 2), "output": proc.stdout[-4000:] + proc.stderr[-2000:],
            "returncode": proc.returncode, "coverage": coverage, "has_cov": has_cov, "selection": selection}


def create_app() -> Flask:
    app = Flask(__name__)
    app.config["SECRET_KEY"] = os.getenv("SECRET_KEY") or secrets.token_hex(32)
    cars, sales, bus = InMemoryCarRepository(), InMemorySaleRepository(), InMemoryEventBus()
    service = SalesService(cars, sales, bus)

    def csrf_token() -> str:
        if "_csrf" not in session:
            session["_csrf"] = secrets.token_urlsafe(32)
        return session["_csrf"]

    @app.before_request
    def _csrf() -> None:
        if request.method == "POST" and not secrets.compare_digest(request.form.get("_csrf", ""), session.get("_csrf", "")):
            abort(400, description="CSRF token noto'g'ri — sahifani yangilang.")

    @app.template_filter("som")
    def som(v: Any) -> str:
        amount = getattr(v, "amount", v)
        return f"{int(amount or 0):,}".replace(",", " ") + " so'm"

    app.jinja_env.globals.update(csrf_token=csrf_token, STATUS_STYLE=STATUS_STYLE, CAR_STYLE=CAR_STYLE,
                                 MIN_PCT=MIN_DOWN_PAYMENT_PCT)

    # ---------------- Sahifalar ----------------
    @app.get("/")
    def index():  # type: ignore[no-untyped-def]
        all_sales = sales.list()
        done = [s for s in all_sales if s.status == SaleStatus.COMPLETED]
        stats = {"cars": len(cars.list()), "available": sum(c.status == CarStatus.AVAILABLE for c in cars.list()),
                 "active": sum(not s.status.is_final for s in all_sales), "completed": len(done),
                 "revenue": sum(s.price.amount for s in done)}
        return render_template("index.html", active="index", cars=cars.list(), sales=all_sales, stats=stats)

    @app.get("/sales/new")
    def new_sale():  # type: ignore[no-untyped-def]
        car = cars.get(request.args.get("car_id", type=int) or 0)
        if car is None:
            abort(404, description="Avtomobil topilmadi")
        return render_template("new_sale.html", active="index", car=car, form=request.args)

    @app.post("/sales")
    def create_sale():  # type: ignore[no-untyped-def]
        f = request.form
        try:
            sale = service.initiate_sale(f.get("car_id", type=int) or 0, f.get("customer_name", ""),
                                         f.get("method", "naqd"), _int(f.get("down_payment")))
        except (DomainError, ValueError) as e:
            flash(str(e), "error")
            return redirect(url_for("new_sale", car_id=f.get("car_id"), customer_name=f.get("customer_name", ""),
                                    method=f.get("method", ""), down_payment=f.get("down_payment", "")))
        flash(f"{sale.id} sotuvi boshlandi — {sale.car.title} band qilindi", "success")
        return redirect(url_for("sale_detail", sale_id=sale.id))

    @app.get("/sales/<sale_id>")
    def sale_detail(sale_id: str):  # type: ignore[no-untyped-def]
        sale = sales.get(sale_id) or abort(404, description="Sotuv topilmadi")
        events = [e for e in bus.published if getattr(e, "sale_id", None) == sale_id]
        return render_template("sale.html", active="index", sale=sale, events=events, flow=FLOW, S=SaleStatus,
                               PM=PaymentMethod)

    @app.post("/sales/<sale_id>/<action>")
    def sale_action(sale_id: str, action: str):  # type: ignore[no-untyped-def]
        f = request.form
        try:
            if action == "financing":
                service.request_financing(sale_id, int(f.get("term_months", 0)), _dec(f.get("annual_rate")))
                msg = "Kredit arizasi bankka yuborildi"
            elif action == "approve":
                service.approve_financing(sale_id, _int(f.get("amount")) or None,
                                          _dec(f.get("annual_rate")) if f.get("annual_rate") else None,
                                          int(f["term_months"]) if f.get("term_months") else None)
                msg = "Bank kreditni tasdiqladi"
            elif action == "reject":
                service.reject_financing(sale_id, f.get("reason", ""))
                msg = "Kredit rad etildi"
            elif action == "cash":
                service.switch_to_cash(sale_id)
                msg = "To'lov usuli naqdga o'zgartirildi"
            elif action == "complete":
                sale = service.complete_sale(sale_id, _int(f.get("paid")))
                msg = f"Sotuv yakunlandi. Qaytim: {som(sale.change)}"
            elif action == "cancel":
                service.cancel_sale(sale_id, f.get("reason", ""))
                msg = "Sotuv bekor qilindi, avtomobil yana sotuvda"
            else:
                abort(404)
            flash(msg, "success")
        except (DomainError, ValueError) as e:
            flash(str(e), "error")
        return redirect(url_for("sale_detail", sale_id=sale_id))

    @app.get("/tests")
    def tests_page():  # type: ignore[no-untyped-def]
        return render_template("tests.html", active="tests", result=None)

    @app.post("/tests/run")
    def tests_run():  # type: ignore[no-untyped-def]
        result = run_pytest("all" if request.form.get("selection") == "all" else "sale")
        return render_template("tests.html", active="tests", result=result)

    @app.get("/architecture")
    def architecture():  # type: ignore[no-untyped-def]
        return render_template("architecture.html", active="architecture")

    @app.get("/api/sales")
    def api_sales():  # type: ignore[no-untyped-def]
        return jsonify([{"id": s.id, "car": s.car.title, "customer": s.customer_name, "status": s.status.value,
                         "price": s.price.amount, "method": s.payment_method.value} for s in sales.list()])

    @app.errorhandler(400)
    @app.errorhandler(404)
    def _err(e):  # type: ignore[no-untyped-def]
        return render_template("error.html", code=e.code, message=e.description), e.code

    return app


def _int(v: str | None) -> int:
    v = (v or "").replace(" ", "").strip()
    return int(v) if v else 0


def _dec(v: str | None) -> Decimal:
    try:
        return Decimal((v or "0").replace(",", ".").strip())
    except InvalidOperation as e:
        raise ValueError("Foiz son bo'lishi kerak") from e


def main() -> None:
    port = int(os.getenv("PORT", "5026"))
    print(f"\n  Avtosalon Tizimi (Sale aggregate + testlar):  http://127.0.0.1:{port}\n")
    create_app().run(host="127.0.0.1", port=port)
