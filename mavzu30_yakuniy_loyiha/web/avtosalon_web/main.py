"""web — Avtosalon boshqaruv paneli (BFF). Ma'lumotlarni servislardan HTTP API orqali oladi (o'z biznes bazasi yo'q).

Qo'shimcha: kirish + rollar (RBAC), audit jurnali, hisobotlar, kuzatuv (metrikalar, taqsimlangan iz, chaos).
"""
from __future__ import annotations

import os
import re
import secrets
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from functools import wraps
from pathlib import Path
from typing import Any, Callable

from flask import Flask, abort, flash, g, redirect, render_template, request, session, url_for

from avtosalon_web.analytics import STATUS_LABEL, short_som
from avtosalon_web.extra import register_extra
from avtosalon_web.auth import ROLES, AuditLog, LoginThrottle, load_users, verify
from svc_common.http import ServiceClient, ServiceError, ServiceUnavailable
from svc_common.observability import Metrics, Span, Tracer

ROOT = Path(__file__).resolve().parents[2]
SALE_STYLE = {"boshlangan": "info", "kredit_tasdiqlangan": "accent", "kredit_rad_etilgan": "danger",
              "yakunlangan": "success", "bekor_qilingan": ""}
CAR_STYLE = {"sotuvda": "success", "band": "warning", "sotilgan": ""}


def create_app() -> Flask:
    app = Flask(__name__)
    env = os.getenv("APP_ENV", "development")
    if env == "production" and not os.getenv("SECRET_KEY"):
        raise RuntimeError("Production'da SECRET_KEY muhit o'zgaruvchisi majburiy")
    app.config.update(
        SECRET_KEY=os.getenv("SECRET_KEY") or secrets.token_hex(32), SERVICE_NAME="web",
        SESSION_COOKIE_HTTPONLY=True, SESSION_COOKIE_SAMESITE="Lax", SESSION_COOKIE_SECURE=env == "production",
        PERMANENT_SESSION_LIFETIME=timedelta(hours=8))
    users, throttle, audit = load_users(), LoginThrottle(), AuditLog(os.getenv("AUDIT_LOG_PATH"))
    metrics, tracer = Metrics("web"), Tracer("web")
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

    PUBLIC = {"login", "static", "health"}

    @app.before_request
    def _security():  # type: ignore[no-untyped-def]
        g.request_id = request.headers.get("X-Request-ID") or uuid.uuid4().hex[:12]
        g.t0, g.t_start = time.perf_counter(), time.time()
        if request.method == "POST" and not secrets.compare_digest(request.form.get("_csrf", ""), session.get("_csrf", "")):
            abort(400, description="CSRF token noto'g'ri — sahifani yangilang.")
        g.user = users.get(session.get("user", ""))
        if g.user is None and request.endpoint not in PUBLIC:
            return redirect(url_for("login", next=request.full_path.rstrip("?")))
        return None

    @app.after_request
    def _observe(resp):  # type: ignore[no-untyped-def]
        resp.headers["X-Request-ID"] = g.get("request_id", "")
        resp.headers.setdefault("X-Content-Type-Options", "nosniff")
        resp.headers.setdefault("X-Frame-Options", "DENY")
        resp.headers.setdefault("Referrer-Policy", "same-origin")
        if request.endpoint not in ("static", "health", None):
            ms = (time.perf_counter() - g.get("t0", time.perf_counter())) * 1000
            route = request.url_rule.rule if request.url_rule else "<topilmadi>"
            metrics.observe(request.method, route, resp.status_code, ms)
            tracer.record(Span(g.get("request_id", ""), "web", request.method, request.full_path.rstrip("?"), resp.status_code,
                               g.get("t_start", time.time()), round(ms, 2), "brauzer"))
        return resp

    def requires(perm: str) -> Callable:  # type: ignore[type-arg]
        def deco(fn):  # type: ignore[no-untyped-def]
            @wraps(fn)
            def inner(*a, **kw):  # type: ignore[no-untyped-def]
                if not g.user.can(perm):
                    audit.write(g.user.login, "ruxsat_rad", f"{request.method} {request.path}", False, g.request_id, request.remote_addr or "")
                    abort(403, description=f"“{g.user.role_title}” rolida bu amal uchun ruxsat yo'q ({perm}).")
                return fn(*a, **kw)
            return inner
        return deco

    def log_action(action: str, detail: str, ok: bool) -> None:
        audit.write(g.user.login if g.get("user") else "—", action, detail, ok, g.get("request_id", ""), request.remote_addr or "")

    @app.template_filter("som")
    def som(v: Any) -> str:
        return f"{int(v or 0):,}".replace(",", " ") + " so'm"

    app.jinja_env.filters["short"] = short_som
    app.jinja_env.globals.update(csrf_token=csrf_token, SALE_STYLE=SALE_STYLE, CAR_STYLE=CAR_STYLE, STATUS_LABEL=STATUS_LABEL,
                                 APP_ENV=env, APP_VERSION=os.getenv("APP_VERSION", "2.0.0"))

    @app.context_processor
    def _ctx() -> dict[str, Any]:
        return {"user": g.get("user"), "can": (lambda p: bool(g.get("user")) and g.user.can(p))}

    def safe(client: ServiceClient, path: str, default: Any) -> tuple[Any, str | None]:
        try:
            return client.get(path), None
        except (ServiceUnavailable, ServiceError) as e:
            return default, str(e)

    def submit(fn, ok_msg: str, action: str):  # type: ignore[no-untyped-def]
        try:
            result = fn()
            msg = ok_msg.format(**result) if isinstance(result, dict) else ok_msg
            flash(msg, "success")
            log_action(action, msg, True)
            return result
        except ServiceError as e:
            fields = e.payload.get("fields")
            msg = f"{e}" + (": " + "; ".join(fields.values()) if fields else "")
        except ServiceUnavailable as e:
            msg = f"Servis mavjud emas: {e}"
        flash(msg, "error")
        log_action(action, msg, False)
        return None

    # ---------------- Kirish ----------------
    @app.route("/login", methods=["GET", "POST"])
    def login():  # type: ignore[no-untyped-def]
        nxt = request.values.get("next") or "/"
        if not nxt.startswith("/") or nxt.startswith("//"):     # open redirect himoyasi
            nxt = "/"
        if request.method == "POST":
            login_name = request.form.get("login", "").strip().lower()
            key = f"{request.remote_addr}|{login_name}"
            wait = throttle.blocked_for(key)
            if wait:
                flash(f"Juda ko'p urinish. {wait} soniyadan keyin qayta urinib ko'ring.", "error")
                audit.write(login_name, "kirish_bloklandi", "", False, g.request_id, request.remote_addr or "")
            else:
                user = verify(users, login_name, request.form.get("password", ""))
                if user:
                    throttle.reset(key)
                    session.clear()                          # session fixation'dan himoya
                    session.permanent = True
                    session["user"] = user.login
                    g.user = user
                    log_action("kirish", user.role_title, True)
                    return redirect(nxt)
                throttle.fail(key)
                audit.write(login_name, "kirish_xato", "", False, g.request_id, request.remote_addr or "")
                flash("Login yoki parol noto'g'ri", "error")
        return render_template("login.html", next=nxt, demo=env != "production", roles=ROLES)

    @app.post("/logout")
    def logout():  # type: ignore[no-untyped-def]
        log_action("chiqish", "", True)
        session.clear()
        return redirect(url_for("login"))

    # ---------------- Sahifalar ----------------
    @app.get("/")
    @requires("dashboard")
    def dashboard():  # type: ignore[no-untyped-def]
        def probe(name: str) -> dict[str, Any]:
            c = svc[name]
            h, err = safe(c, "/health", {})
            r, _ = safe(c, "/ready", {})
            m, _ = safe(c, "/metrics.json", {})
            return {"name": name, "url": c.base_url, "up": not err, "ready": bool(r.get("ready")),
                    "db": r.get("database", "—"), "version": h.get("version", "—"), "uptime": h.get("uptime_s"), "error": err,
                    "instance": h.get("instance", "—"), "git_sha": h.get("git_sha", "—"),
                    "build_date": h.get("build_date", "—"), "environment": h.get("environment", "—"),
                    "chaos": (m.get("chaos") or {}).get("mode", "off"), "requests": m.get("requests"), "error_rate": m.get("error_rate")}
        with ThreadPoolExecutor(5) as ex:
            health = list(ex.map(probe, svc))
        car_stats, _ = safe(cars, "/stats", {})
        sale_stats, _ = safe(sales, "/stats", {})
        recent, _ = safe(sales, "/sales", [])
        return render_template("dashboard.html", active="dashboard", health=health, car_stats=car_stats,
                               sale_stats=sale_stats, recent=recent[:6])

    @app.route("/cars", methods=["GET", "POST"])
    @requires("cars:read")
    def cars_page():  # type: ignore[no-untyped-def]
        if request.method == "POST":
            if not g.user.can("cars:write"):
                abort(403, description="Avtomobil qo'shish uchun ruxsat yo'q")
            f = request.form
            submit(lambda: cars.post("/cars", {k: f.get(k, "") for k in ("vin", "make", "model", "year", "price", "color")}),
                   "Avtomobil qo'shildi: {make} {model}", "avtomobil_qoshish")
            return redirect(url_for("cars_page"))
        rows, err = safe(cars, "/cars" + (f"?status={request.args['status']}" if request.args.get("status") else ""), [])
        return render_template("cars.html", active="cars", cars=rows, error=err, selected=request.args.get("status", ""))

    @app.route("/customers", methods=["GET", "POST"])
    @requires("customers:read")
    def customers_page():  # type: ignore[no-untyped-def]
        if request.method == "POST":
            if not g.user.can("customers:write"):
                abort(403, description="Mijoz qo'shish uchun ruxsat yo'q")
            f = request.form
            submit(lambda: customers.post("/customers", {k: f.get(k, "") for k in ("full_name", "phone", "passport", "monthly_income")}),
                   "Mijoz qo'shildi: {full_name}", "mijoz_qoshish")
            return redirect(url_for("customers_page"))
        rows, err = safe(customers, "/customers", [])
        return render_template("customers.html", active="customers", customers=rows, error=err)

    @app.get("/sales")
    @requires("sales:read")
    def sales_page():  # type: ignore[no-untyped-def]
        rows, err = safe(sales, "/sales", [])
        available, _ = safe(cars, "/cars?status=sotuvda", [])
        people, _ = safe(customers, "/customers", [])
        return render_template("sales.html", active="sales", sales=rows, error=err, cars=available, customers=people,
                               form=request.args)

    @app.post("/sales")
    @requires("sales:write")
    def create_sale():  # type: ignore[no-untyped-def]
        f = request.form
        body = {"car_id": f.get("car_id"), "customer_id": f.get("customer_id"), "payment_method": f.get("payment_method"),
                "down_payment": f.get("down_payment") or 0, "term_months": f.get("term_months") or 36,
                "annual_rate": f.get("annual_rate") or 24}
        sale = submit(lambda: sales.post("/sales", body), "Sotuv {ref} yaratildi — holati: {status}", "sotuv_yaratish")
        if sale:
            return redirect(url_for("sale_detail", sale_id=sale["id"]))
        return redirect(url_for("sales_page", **{k: v for k, v in f.items() if k != "_csrf"}))

    @app.get("/sales/<int:sale_id>")
    @requires("sales:read")
    def sale_detail(sale_id: int):  # type: ignore[no-untyped-def]
        sale, err = safe(sales, f"/sales/{sale_id}", None)
        if sale is None:
            abort(404, description=err or "Sotuv topilmadi")
        application = None
        if sale.get("application_id"):
            application, _ = safe(financing, f"/applications/{sale['application_id']}", None)
        saga, _ = safe(sales, f"/sales/{sale_id}/saga", {"steps": []})
        return render_template("sale.html", active="sales", sale=sale, application=application, saga=saga)

    @app.post("/sales/<int:sale_id>/<action>")
    @requires("sales:write")
    def sale_action(sale_id: int, action: str):  # type: ignore[no-untyped-def]
        if action == "complete":
            submit(lambda: sales.post(f"/sales/{sale_id}/complete", {"paid": request.form.get("paid", 0)}),
                   f"Sotuv #{sale_id} yakunlandi — avtomobil “sotilgan”", "sotuv_yakunlash")
        elif action == "cancel":
            submit(lambda: sales.post(f"/sales/{sale_id}/cancel", {"reason": request.form.get("reason", "")}),
                   f"Sotuv #{sale_id} bekor qilindi — avtomobil yana sotuvda", "sotuv_bekor")
        else:
            abort(404)
        return redirect(url_for("sale_detail", sale_id=sale_id))

    @app.get("/financing")
    @requires("financing:read")
    def financing_page():  # type: ignore[no-untyped-def]
        rows, err = safe(financing, "/applications", [])
        return render_template("financing.html", active="financing", apps=rows, error=err)

    @app.get("/release")
    @requires("ops")
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
    @requires("ops")
    def events_page():  # type: ignore[no-untyped-def]
        items, err = safe(notifier, "/notifications", [])
        stats, _ = safe(notifier, "/stats", {})
        return render_template("events.html", active="events", items=items, stats=stats, error=err)

    @app.get("/architecture")
    @requires("docs")
    def architecture():  # type: ignore[no-untyped-def]
        path = Path(os.getenv("COMPOSE_FILE_PATH", str(ROOT / "docker-compose.yml")))
        compose = path.read_text(encoding="utf-8") if path.exists() else ""
        return render_template("architecture.html", active="architecture", compose=compose)

    docs_dir = Path(os.getenv("DOCS_DIR", str(ROOT / "docs")))

    def doc_index() -> list[dict[str, str]]:
        items = [{"key": "ARCHITECTURE", "title": "Arxitektura hujjati (arc42 + C4)", "path": "ARCHITECTURE.md"},
                 {"key": "DEFENSE", "title": "Himoya rejasi va savol-javoblar", "path": "DEFENSE.md"}]
        for f in sorted((docs_dir / "adr").glob("*.md")) if (docs_dir / "adr").exists() else []:
            first = f.read_text(encoding="utf-8").splitlines()[0].lstrip("# ").strip()
            items.append({"key": f.stem, "title": first, "path": f"adr/{f.name}"})
        return items

    @app.get("/docs")
    @app.get("/docs/<key>")
    @requires("docs")
    def docs_page(key: str = "ARCHITECTURE"):  # type: ignore[no-untyped-def]
        index = doc_index()
        current = next((d for d in index if d["key"] == key), None)   # faqat ro'yxatdagi fayllar (path traversal yo'q)
        if current is None:
            abort(404, description="Hujjat topilmadi")
        text = (docs_dir / current["path"]).read_text(encoding="utf-8") if (docs_dir / current["path"]).exists() else ""
        from avtosalon_web.markdown_lite import render

        def link(url: str) -> str:   # hujjatlararo havola: adr/0001-xxx.md → /docs/0001-xxx
            m = re.search(r"(?:^|/)([\w-]+)\.md$", url)
            return url_for("docs_page", key=m.group(1)) if m and not url.startswith("http") else url
        return render_template("docs.html", active="docs", index=index, current=current, html=render(text, link))

    @app.get("/health")
    def health():  # type: ignore[no-untyped-def]
        return {"service": "web", "status": "ok", "version": os.getenv("APP_VERSION", "dev"),
                "git_sha": os.getenv("GIT_SHA", "local")[:7]}

    register_extra(app, svc, safe, submit, requires, log_action, audit, metrics, tracer)

    @app.errorhandler(400)
    @app.errorhandler(403)
    @app.errorhandler(404)
    def _err(e):  # type: ignore[no-untyped-def]
        return render_template("error.html", code=e.code, message=e.description), e.code

    return app
