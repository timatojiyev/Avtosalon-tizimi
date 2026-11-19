"""Panelning “yakuniy loyiha” qo'shimchalari: hisobotlar, CSV eksport, kuzatuv (metrikalar, iz, chaos),
audit jurnali va demo-ssenariy."""
from __future__ import annotations

import csv
import io
import random
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Callable

from flask import Flask, Response, abort, flash, redirect, render_template, request, url_for

from avtosalon_web.analytics import bar_chart, build_report, donut
from svc_common.http import ServiceClient, ServiceError, ServiceUnavailable
from svc_common.observability import Metrics, Tracer

CHAOS_MODES = {"off": "Normal", "error": "Ishdan chiqarish (503)", "latency": "Sekinlashtirish"}


def register_extra(app: Flask, svc: dict[str, ServiceClient], safe: Callable, submit: Callable, requires: Callable,  # type: ignore[type-arg]
                   log_action: Callable, audit: Any, metrics: Metrics, tracer: Tracer) -> None:  # type: ignore[type-arg]
    cars, customers, sales, financing = svc["car-service"], svc["customer-service"], svc["sales-service"], svc["financing-service"]

    def parallel(calls: dict[str, tuple[ServiceClient, str, Any]]) -> dict[str, Any]:
        with ThreadPoolExecutor(len(calls)) as ex:
            futures = {k: ex.submit(safe, c, p, d) for k, (c, p, d) in calls.items()}
            return {k: f.result()[0] for k, f in futures.items()}

    # ---------------- Hisobotlar ----------------
    @app.get("/reports")
    @requires("reports")
    def reports():  # type: ignore[no-untyped-def]
        data = parallel({"sales": (sales, "/sales", []), "cars": (cars, "/cars", []), "apps": (financing, "/applications", [])})
        rep = build_report(data["sales"], data["cars"], data["apps"])
        charts = {"daily": bar_chart(rep["daily"]),
                  "methods": donut([("Naqd", rep["methods"].get("naqd", 0)), ("Kredit", rep["methods"].get("kredit", 0))]),
                  "status": donut([(k, rep["status"].get(k, 0)) for k in
                                   ("yakunlangan", "kredit_tasdiqlangan", "boshlangan", "kredit_rad_etilgan", "bekor_qilingan")])}
        return render_template("reports.html", active="reports", rep=rep, charts=charts)

    @app.get("/reports/sales.csv")
    @requires("reports")
    def sales_csv():  # type: ignore[no-untyped-def]
        rows, err = safe(sales, "/sales", [])
        if err:
            abort(503, description=err)
        buf = io.StringIO()
        cols = ["ref", "created_at", "car_title", "customer_name", "payment_method", "price", "down_payment", "financed_amount",
                "monthly_payment", "amount_paid", "status", "note"]
        w = csv.writer(buf, delimiter=";")
        w.writerow(cols)
        for r in rows:
            w.writerow([_csv_safe(r.get(c)) for c in cols])
        log_action("eksport", f"sales.csv ({len(rows)} qator)", True)
        return Response("﻿" + buf.getvalue(), mimetype="text/csv",       # BOM — Excel UTF-8 ni to'g'ri ochishi uchun
                        headers={"Content-Disposition": "attachment; filename=avtosalon-sotuvlar.csv"})

    # ---------------- Kuzatuv ----------------
    def all_clients() -> dict[str, ServiceClient]:
        return {k: v for k, v in svc.items()}

    @app.get("/ops")
    @requires("ops")
    def ops():  # type: ignore[no-untyped-def]
        snaps = parallel({n: (c, "/metrics.json", None) for n, c in all_clients().items()})
        web_snap = {**metrics.snapshot(), "chaos": {"allowed": False, "mode": "off"}}
        services = [{"name": n, "snap": s} for n, s in snaps.items()] + [{"name": "web", "snap": web_snap}]
        spans = collect_spans("")
        groups: dict[str, list[dict[str, Any]]] = {}
        for sp in spans:
            groups.setdefault(sp["request_id"], []).append(sp)
        recent = []
        for rid, items in groups.items():
            root = min(items, key=lambda s: s["start"])
            end = max(s["start"] + s["ms"] / 1000 for s in items)
            recent.append({"request_id": rid, "root": root, "spans": len(items), "services": len({s["service"] for s in items}),
                           "ms": round((end - root["start"]) * 1000, 1), "error": any(s["status"] >= 500 for s in items),
                           "start": root["start"]})
        recent = [r for r in sorted(recent, key=lambda r: -r["start"]) if r["services"] > 1][:15]
        return render_template("ops.html", active="ops", services=services, recent=recent, modes=CHAOS_MODES)

    @app.post("/ops/chaos/<name>")
    @requires("ops")
    def set_chaos(name: str):  # type: ignore[no-untyped-def]
        client = svc.get(name)
        if client is None:
            abort(404)
        mode = request.form.get("mode", "off")
        submit(lambda: client.post("/admin/chaos", {"mode": mode, "latency_ms": request.form.get("latency_ms") or None}),
               f"{name}: rejim → {CHAOS_MODES.get(mode, mode)}", "chaos")
        return redirect(url_for("ops"))

    def collect_spans(request_id: str) -> list[dict[str, Any]]:
        q = f"/traces?limit=300&request_id={request_id}" if request_id else "/traces?limit=300"
        got = parallel({n: (c, q, []) for n, c in all_clients().items()})
        spans = [s for items in got.values() for s in (items or [])]
        spans += tracer.find(request_id, 300)
        return spans

    @app.get("/ops/trace/<request_id>")
    @requires("ops")
    def trace(request_id: str):  # type: ignore[no-untyped-def]
        spans = sorted(collect_spans(request_id), key=lambda s: s["start"])
        if not spans:
            abort(404, description="Bu so'rov izi topilmadi (xotirada oxirgi 1000 ta span saqlanadi)")
        t0 = spans[0]["start"]
        total = max((s["start"] - t0) * 1000 + s["ms"] for s in spans) or 1
        for s in spans:
            s["offset_pct"] = (s["start"] - t0) * 1000 / total * 100
            s["width_pct"] = max(s["ms"] / total * 100, 0.6)
            s["offset_ms"] = round((s["start"] - t0) * 1000, 1)
        return render_template("trace.html", active="ops", spans=spans, request_id=request_id, total=round(total, 1))

    @app.get("/audit")
    @requires("ops")
    def audit_page():  # type: ignore[no-untyped-def]
        return render_template("audit.html", active="audit", items=audit.recent())

    # ---------------- Demo-ssenariy ----------------
    @app.post("/admin/demo")
    @requires("ops")
    def demo():  # type: ignore[no-untyped-def]
        """Tizimni “jonli” ko'rsatish uchun: yangi avtomobillar va har xil yakunlangan saga'lar (naqd, kredit, rad, bekor)."""
        try:
            created = run_demo(cars, customers, sales)
            flash(f"Demo ma'lumotlar yaratildi: {created} ta sotuv (naqd, kredit, rad etilgan, bekor qilingan)", "success")
            log_action("demo", f"{created} ta sotuv", True)
        except (ServiceError, ServiceUnavailable) as e:
            flash(f"Demo to'liq bajarilmadi: {e}", "error")
            log_action("demo", str(e), False)
        return redirect(request.form.get("back") or url_for("reports"))


DEMO_CARS = [("Chevrolet", "Cobalt", 165_000_000, "Oq"), ("Chevrolet", "Tracker", 265_000_000, "Kulrang"),
             ("BYD", "Song Plus", 420_000_000, "Qora"), ("Kia", "Sonet", 245_000_000, "Ko'k"),
             ("Chevrolet", "Onix", 198_000_000, "Qizil"), ("Hyundai", "Tucson", 455_000_000, "Oq"),
             ("BYD", "Han", 560_000_000, "Qora"), ("Chevrolet", "Damas", 98_000_000, "Oq")]
VIN_CHARS = "ABCDEFGHJKLMNPRSTUVWXYZ0123456789"


def run_demo(cars: ServiceClient, customers: ServiceClient, sales: ServiceClient) -> int:
    people = customers.get("/customers")
    rich = max(people, key=lambda c: c["monthly_income"])
    poor = min(people, key=lambda c: c["monthly_income"])
    plan = ["naqd+", "kredit+", "naqd+", "rad", "kredit+", "bekor", "naqd+", "ochiq"]
    done = 0
    for (make, model, price, color), kind in zip(DEMO_CARS, plan):
        vin = "".join(random.choice(VIN_CHARS) for _ in range(17))
        car = cars.post("/cars", {"vin": vin, "make": make, "model": model, "year": 2025, "price": price, "color": color})
        who = poor if kind == "rad" else rich
        if kind in ("kredit+", "rad"):
            body = {"car_id": car["id"], "customer_id": who["id"], "payment_method": "kredit",
                    "down_payment": price * 30 // 100, "term_months": 36 if kind == "kredit+" else 12, "annual_rate": 22}
        else:
            body = {"car_id": car["id"], "customer_id": who["id"], "payment_method": "naqd"}
        sale = sales.post("/sales", body)
        done += 1
        if kind in ("naqd+", "kredit+") and sale["status"] in ("boshlangan", "kredit_tasdiqlangan"):
            sales.post(f"/sales/{sale['id']}/complete", {"paid": sale["down_payment"]})
        elif kind == "bekor":
            sales.post(f"/sales/{sale['id']}/cancel", {"reason": "Mijoz fikridan qaytdi (demo)"})
    return done


def _csv_safe(v: Any) -> Any:
    """CSV injection himoyasi: = + - @ bilan boshlanadigan matnlar Excel'da formula bo'lib ketmasin."""
    if isinstance(v, str) and v[:1] in ("=", "+", "-", "@"):
        return "'" + v
    return "" if v is None else v
