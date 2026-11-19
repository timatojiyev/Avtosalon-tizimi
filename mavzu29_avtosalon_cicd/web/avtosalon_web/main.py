"""web — Avtosalon boshqaruv paneli. Ma'lumotlarni 4 ta servisdan HTTP API orqali oladi (o'z bazasi yo'q)."""
from __future__ import annotations

import os
import secrets
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

from flask import Flask, abort, flash, redirect, render_template, request, session, url_for

from svc_common.http import ServiceClient, ServiceError, ServiceUnavailable

ROOT = Path(__file__).resolve().parents[2]
SALE_STYLE = {"boshlangan": "info", "kredit_tasdiqlangan": "accent", "kredit_rad_etilgan": "danger",
              "yakunlangan": "success", "bekor_qilingan": ""}
CAR_STYLE = {"sotuvda": "success", "band": "warning", "sotilgan": ""}


def create_app() -> Flask:
    app = Flask(__name__)
    app.config["SECRET_KEY"] = os.getenv("SECRET_KEY") or secrets.token_hex(32)
    svc = {
        "car-service": ServiceClient("car-service", os.getenv("CAR_SERVICE_URL", "http://localhost:8001"), timeout=3),
        "customer-service": ServiceClient("customer-service", os.getenv("CUSTOMER_SERVICE_URL", "http://localhost:8002"), timeout=3),
        "sales-service": ServiceClient("sales-service", os.getenv("SALES_SERVICE_URL", "http://localhost:8003"), timeout=8),
        "financing-service": ServiceClient("financing-service", os.getenv("FINANCING_SERVICE_URL", "http://localhost:8004"), timeout=3),
        "notification-worker": ServiceClient("notification-worker", os.getenv("NOTIFIER_URL", "http://localhost:8005"), timeout=3),
    }
    cars, customers, sales, financing, notifier = (svc[k] for k in ("car-service", "customer-service", "sales-service",
                                                                    "financing-service", "notification-worker"))

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
        return f"{int(v or 0):,}".replace(",", " ") + " so'm"

    app.jinja_env.globals.update(csrf_token=csrf_token, SALE_STYLE=SALE_STYLE, CAR_STYLE=CAR_STYLE)

    def safe(client: ServiceClient, path: str, default: Any) -> tuple[Any, str | None]:
        try:
            return client.get(path), None
        except (ServiceUnavailable, ServiceError) as e:
            return default, str(e)

    def submit(fn, ok_msg: str, back: str):  # type: ignore[no-untyped-def]
        try:
            result = fn()
            flash(ok_msg.format(**result) if isinstance(result, dict) else ok_msg, "success")
            return result
        except ServiceError as e:
            fields = e.payload.get("fields")
            flash(f"{e}" + (": " + "; ".join(fields.values()) if fields else ""), "error")
        except ServiceUnavailable as e:
            flash(f"Servis mavjud emas: {e}", "error")
        return None

    # ---------------- Sahifalar ----------------
    @app.get("/")
    def dashboard():  # type: ignore[no-untyped-def]
        def probe(name: str) -> dict[str, Any]:
            c = svc[name]
            h, err = safe(c, "/health", {})
            r, _ = safe(c, "/ready", {})
            return {"name": name, "url": c.base_url, "up": not err, "ready": bool(r.get("ready")),
                    "db": r.get("database", "—"), "version": h.get("version", "—"), "uptime": h.get("uptime_s"), "error": err,
                    "instance": h.get("instance", "—"), "git_sha": h.get("git_sha", "—"),
                    "build_date": h.get("build_date", "—"), "environment": h.get("environment", "—")}
        with ThreadPoolExecutor(5) as ex:
            health = list(ex.map(probe, svc))
        car_stats, _ = safe(cars, "/stats", {})
        sale_stats, _ = safe(sales, "/stats", {})
        recent, _ = safe(sales, "/sales", [])
        return render_template("dashboard.html", active="dashboard", health=health, car_stats=car_stats,
                               sale_stats=sale_stats, recent=recent[:6])

    @app.route("/cars", methods=["GET", "POST"])
    def cars_page():  # type: ignore[no-untyped-def]
        if request.method == "POST":
            f = request.form
            submit(lambda: cars.post("/cars", {k: f.get(k, "") for k in ("vin", "make", "model", "year", "price", "color")}),
                   "Avtomobil qo'shildi: {make} {model}", "cars_page")
            return redirect(url_for("cars_page"))
        rows, err = safe(cars, "/cars" + (f"?status={request.args['status']}" if request.args.get("status") else ""), [])
        return render_template("cars.html", active="cars", cars=rows, error=err, selected=request.args.get("status", ""))

    @app.route("/customers", methods=["GET", "POST"])
    def customers_page():  # type: ignore[no-untyped-def]
        if request.method == "POST":
            f = request.form
            submit(lambda: customers.post("/customers", {k: f.get(k, "") for k in ("full_name", "phone", "passport", "monthly_income")}),
                   "Mijoz qo'shildi: {full_name}", "customers_page")
            return redirect(url_for("customers_page"))
        rows, err = safe(customers, "/customers", [])
        return render_template("customers.html", active="customers", customers=rows, error=err)

    @app.get("/sales")
    def sales_page():  # type: ignore[no-untyped-def]
        rows, err = safe(sales, "/sales", [])
        available, _ = safe(cars, "/cars?status=sotuvda", [])
        people, _ = safe(customers, "/customers", [])
        return render_template("sales.html", active="sales", sales=rows, error=err, cars=available, customers=people,
                               form=request.args)

    @app.post("/sales")
    def create_sale():  # type: ignore[no-untyped-def]
        f = request.form
        body = {"car_id": f.get("car_id"), "customer_id": f.get("customer_id"), "payment_method": f.get("payment_method"),
                "down_payment": f.get("down_payment") or 0, "term_months": f.get("term_months") or 36,
                "annual_rate": f.get("annual_rate") or 24}
        sale = submit(lambda: sales.post("/sales", body), "Sotuv {ref} yaratildi — holati: {status}", "sales_page")
        if sale:
            return redirect(url_for("sale_detail", sale_id=sale["id"]))
        return redirect(url_for("sales_page", **{k: v for k, v in f.items() if k != "_csrf"}))

    @app.get("/sales/<int:sale_id>")
    def sale_detail(sale_id: int):  # type: ignore[no-untyped-def]
        sale, err = safe(sales, f"/sales/{sale_id}", None)
        if sale is None:
            abort(404, description=err or "Sotuv topilmadi")
        application = None
        if sale.get("application_id"):
            application, _ = safe(financing, f"/applications/{sale['application_id']}", None)
        return render_template("sale.html", active="sales", sale=sale, application=application)

    @app.post("/sales/<int:sale_id>/<action>")
    def sale_action(sale_id: int, action: str):  # type: ignore[no-untyped-def]
        if action == "complete":
            submit(lambda: sales.post(f"/sales/{sale_id}/complete", {"paid": request.form.get("paid", 0)}),
                   "Sotuv yakunlandi — avtomobil “sotilgan”", "")
        elif action == "cancel":
            submit(lambda: sales.post(f"/sales/{sale_id}/cancel", {"reason": request.form.get("reason", "")}),
                   "Sotuv bekor qilindi — avtomobil yana sotuvda", "")
        else:
            abort(404)
        return redirect(url_for("sale_detail", sale_id=sale_id))

    @app.get("/financing")
    def financing_page():  # type: ignore[no-untyped-def]
        rows, err = safe(financing, "/applications", [])
        return render_template("financing.html", active="financing", apps=rows, error=err)

    @app.get("/release")
    def release_page():  # type: ignore[no-untyped-def]
        def probe(name: str) -> dict[str, Any]:
            h, err = safe(svc[name], "/health", {})
            return {"name": name, "error": err, **h}
        with ThreadPoolExecutor(5) as ex:
            services = list(ex.map(probe, svc))
        web_info = {"name": "web", "version": os.getenv("APP_VERSION", "dev"), "git_sha": os.getenv("GIT_SHA", "local")[:7],
                    "build_date": os.getenv("BUILD_DATE", "—"), "environment": os.getenv("APP_ENV", "development")}
        versions = {s.get("version") for s in services if not s["error"]} | {web_info["version"]}
        return render_template("release.html", active="release", services=services, web_info=web_info,
                               consistent=len(versions) == 1)

    @app.get("/events")
    def events_page():  # type: ignore[no-untyped-def]
        items, err = safe(notifier, "/notifications", [])
        stats, _ = safe(notifier, "/stats", {})
        return render_template("events.html", active="events", items=items, stats=stats, error=err)

    @app.get("/architecture")
    def architecture():  # type: ignore[no-untyped-def]
        path = Path(os.getenv("COMPOSE_FILE_PATH", str(ROOT / "docker-compose.yml")))
        compose = path.read_text(encoding="utf-8") if path.exists() else ""
        return render_template("architecture.html", active="architecture", compose=compose)

    @app.get("/health")
    def health():  # type: ignore[no-untyped-def]
        return {"service": "web", "status": "ok", "version": os.getenv("APP_VERSION", "dev"),
                "git_sha": os.getenv("GIT_SHA", "local")[:7]}

    @app.errorhandler(400)
    @app.errorhandler(404)
    def _err(e):  # type: ignore[no-untyped-def]
        return render_template("error.html", code=e.code, message=e.description), e.code

    return app
