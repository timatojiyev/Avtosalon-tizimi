"""Yakuniy loyiha qo'shimchalari: RBAC, audit, kuzatuv (metrika/iz/chaos), saga jurnali, hisobotlar, demo."""

from avtosalon_web.analytics import bar_chart, build_report, donut
from avtosalon_web.auth import LoginThrottle, load_users, verify
from car_service.main import create_app as car_app
from svc_common.observability import Chaos, Metrics, RouteStats
from tests.test_services import login, system  # noqa: F401 — fixture


# ---------------- auth ----------------
def test_password_hashing_and_throttle():
    users = load_users()
    assert users["admin"].password_hash != "admin123"            # parol ochiq saqlanmaydi
    assert verify(users, "ADMIN ", "admin123").login == "admin"
    assert verify(users, "admin", "xato") is None and verify(users, "yoq", "admin123") is None
    t = LoginThrottle(max_failures=3, window_s=60)
    for _ in range(3):
        t.fail("ip|admin")
    assert t.blocked_for("ip|admin") > 0
    t.reset("ip|admin")
    assert t.blocked_for("ip|admin") == 0


def test_login_required_and_rbac(system):  # noqa: F811
    _, web = system
    anon = web.test_client()
    r = anon.get("/sales")
    assert r.status_code == 302 and "/login" in r.headers["Location"]
    assert anon.get("/health").status_code == 200

    kredit = login(web, "kredit")
    assert kredit.get("/financing").status_code == 200
    assert kredit.get("/reports").status_code == 200
    assert kredit.get("/ops").status_code == 403                       # faqat admin
    r = kredit.post("/sales", data={"_csrf": "t", "car_id": "1", "customer_id": "1", "payment_method": "naqd"})
    assert r.status_code == 403                                         # sotuv yaratolmaydi
    assert "Sotuv yaratish" in kredit.get("/sales").get_data(as_text=True)   # forma o'rniga izoh

    menejer = login(web, "menejer")
    assert menejer.get("/cars").status_code == 200
    assert menejer.get("/audit").status_code == 403

    admin = login(web)
    page = admin.get("/audit").get_data(as_text=True)
    assert "ruxsat_rad" in page and "kirish" in page                    # rad etilgan urinishlar ham jurnalda


def test_login_errors_and_open_redirect(system):  # noqa: F811
    _, web = system
    c = web.test_client()
    c.get("/login")
    with c.session_transaction() as s:
        s["_csrf"] = "t"
    assert "noto&#39;g&#39;ri" in c.post("/login", data={"_csrf": "t", "login": "admin", "password": "x"}).get_data(as_text=True)
    r = c.post("/login", data={"_csrf": "t", "login": "admin", "password": "admin123", "next": "//evil.com"})
    assert r.headers["Location"] == "/"
    assert r.headers.get("X-Frame-Options") == "DENY"


# ---------------- observability ----------------
def test_metrics_prometheus_and_percentiles():
    m = Metrics("car-service")
    for ms in (3, 4, 8, 30, 700):
        m.observe("GET", "/cars", 200, ms)
    m.observe("GET", "/cars", 503, 2)
    snap = m.snapshot()
    assert snap["requests"] == 6 and snap["errors"] == 1 and snap["error_rate"] == 16.67
    text = m.prometheus()
    assert 'http_requests_total{service="car-service",method="GET",route="/cars"} 6' in text
    assert 'le="+Inf"} 6' in text
    rs = RouteStats()
    for ms in (1, 1, 1, 1, 400):
        rs.observe(ms, False)
    assert rs.percentile(.5) == 5 and rs.percentile(.95) == 500


def test_service_metrics_traces_and_chaos():
    c = car_app("sqlite:///:memory:").test_client()
    c.get("/cars", headers={"X-Request-ID": "abc123"})
    assert c.get("/metrics.json").json["requests"] == 1
    assert "http_request_duration_ms_bucket" in c.get("/metrics").get_data(as_text=True)
    assert c.get("/traces?request_id=abc123").json[0]["path"] == "/cars"
    assert c.post("/admin/chaos", json={"mode": "error"}).json["mode"] == "error"
    assert c.get("/cars").status_code == 503
    assert c.get("/health").status_code == 200                        # infra endpoint'lar ishlayveradi
    assert c.post("/admin/chaos", json={"mode": "nimadir"}).status_code == 422
    c.post("/admin/chaos", json={"mode": "off"})
    assert c.get("/cars").status_code == 200
    ch = Chaos(allowed=False)
    try:
        ch.set("error")
        raise AssertionError("production'da chaos yoqilmasligi kerak")
    except PermissionError:
        pass


def test_chaos_triggers_compensation_and_saga_log(system):  # noqa: F811
    """financing-service “buzilsa” — sotuv bekor, avtomobil bo'shatiladi, saga jurnalida KOMPENSATSIYA qadami."""
    api, web = system
    fin, sales, cars = api["financing-service"], api["sales-service"], api["car-service"]
    fin.post("/admin/chaos", {"mode": "error"})
    c = login(web)
    page = c.post("/sales", data={"_csrf": "t", "car_id": "3", "customer_id": "1", "payment_method": "kredit",
                                  "down_payment": "100000000", "term_months": "36", "annual_rate": "24"},
                  follow_redirects=True).get_data(as_text=True)
    assert "mavjud emas" in page
    assert cars.get("/cars/3")["status"] == "sotuvda"
    sale = sales.get("/sales")[0]
    saga = sales.get(f"/sales/{sale['id']}/saga")
    outcomes = [s["outcome"] for s in saga["steps"]]
    assert outcomes[-2:] == ["xato", "kompensatsiya"] and outcomes[0] == "ok"
    fin.post("/admin/chaos", {"mode": "off"})

    # taqsimlangan iz: web → sales → customer/car/financing, bitta X-Request-ID bilan
    ops = c.get("/ops").get_data(as_text=True)
    assert "financing-service" in ops
    trace = c.get(f"/ops/trace/{saga['request_id']}").get_data(as_text=True)
    for svc in ("web", "sales-service", "car-service", "financing-service"):
        assert svc in trace, svc
    assert c.get("/ops/trace/yoq-id").status_code == 404


# ---------------- hisobotlar va demo ----------------
def test_demo_reports_and_csv(system):  # noqa: F811
    api, web = system
    c = login(web)
    r = c.post("/admin/demo", data={"_csrf": "t"}, follow_redirects=True)
    assert "Demo ma&#39;lumotlar yaratildi: 8" in r.get_data(as_text=True)
    statuses = {s["status"] for s in api["sales-service"].get("/sales")}
    assert {"yakunlangan", "kredit_rad_etilgan", "bekor_qilingan", "boshlangan"} <= statuses
    page = c.get("/reports").get_data(as_text=True)
    assert "<svg" in page and "Sotuv voronkasi" in page
    csv = c.get("/reports/sales.csv")
    assert csv.mimetype == "text/csv" and csv.get_data(as_text=True).count("\n") == 9    # sarlavha + 8
    detail = c.get("/sales/1").get_data(as_text=True)
    assert "Saga izi" in detail and "Avtomobilni band qilish" in detail


def test_report_math():
    sales = [{"status": "yakunlangan", "price": 100, "payment_method": "naqd", "car_title": "BYD Han", "customer_name": "A",
              "updated_at": "2026-01-01T10:00:00+00:00"},
             {"status": "bekor_qilingan", "price": 50, "payment_method": "kredit", "car_title": "Kia K5", "customer_name": "B"}]
    apps = [{"status": "tasdiqlandi", "pti": 30, "amount": 40}, {"status": "rad_etildi", "pti": 70, "amount": 10}]
    rep = build_report(sales, [{"status": "sotuvda", "price": 7}], apps)
    k = rep["kpi"]
    assert (k["revenue"], k["conversion"], k["approval_rate"], k["avg_pti"], k["stock_value"]) == (100, 50.0, 50.0, 50.0, 7)
    assert rep["brands"][0][0] == "BYD"
    assert "<rect" in bar_chart(rep["daily"]) and "<circle" in donut([("a", 1), ("b", 0)])


def test_production_hardening(monkeypatch):
    assert load_users(production=True) == {}                            # demo parollar production'da yo'q
    monkeypatch.setenv("WEB_ADMIN_PASSWORD", "Kuchli-Parol-2026")
    users = load_users(production=True)
    assert list(users) == ["admin"] and verify(users, "admin", "Kuchli-Parol-2026")
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.delenv("SECRET_KEY", raising=False)
    from avtosalon_web.main import create_app
    try:
        create_app()
        raise AssertionError("SECRET_KEY'siz ishga tushmasligi kerak")
    except RuntimeError:
        pass


def test_gateway_protects_api_with_key():
    from pathlib import Path
    root = Path(__file__).resolve().parents[1]
    conf = (root / "gateway/nginx.conf").read_text()
    api_locations = [ln for ln in conf.splitlines() if ln.strip().startswith("location /api/")]
    assert len(api_locations) == 5 and all("$api_key_ok = 0" in ln for ln in api_locations)
    assert "${GATEWAY_API_KEY}" in (root / "gateway/templates/api-key.conf.template").read_text()
    assert "GATEWAY_API_KEY:?" in (root / "docker-compose.prod.yml").read_text()     # production'da majburiy
