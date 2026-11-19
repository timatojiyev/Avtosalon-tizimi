"""Har bir servisning API testlari (SQLite xotira bazasi bilan) va to'liq e2e oqim (servislar haqiqiy HTTP orqali)."""
import socket

import pytest

from car_service.main import create_app as car_app
from customer_service.main import create_app as customer_app
from financing_service.main import annuity, create_app as financing_app, decide
from sales_service.main import create_app as sales_app
from svc_common import ServiceClient


def free_port():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


# ---------------- car-service ----------------
def test_car_service_crud_and_transitions():
    c = car_app("sqlite:///:memory:").test_client()
    assert c.get("/health").json["status"] == "ok" and c.get("/ready").json["ready"]
    assert len(c.get("/cars").json) == 8
    r = c.post("/cars", json={"vin": "XWBJA11CVPN000999", "make": "Chevrolet", "model": "Captiva", "year": 2025, "price": 320000000})
    assert r.status_code == 201
    cid = r.json["id"]
    assert c.post("/cars", json={"vin": "XWBJA11CVPN000999", "make": "A", "model": "B", "year": 2025, "price": 1}).status_code == 409
    assert c.post("/cars", json={"vin": "BAD", "make": "", "model": "", "year": 1900, "price": 0}).status_code == 422
    assert c.post(f"/cars/{cid}/reserve").json["status"] == "band"
    assert c.post(f"/cars/{cid}/reserve").status_code == 409         # ikki marta band qilib bo'lmaydi
    assert c.post(f"/cars/{cid}/sell").json["status"] == "sotilgan"
    assert c.post(f"/cars/{cid}/release").status_code == 409
    assert c.get("/cars/9999").status_code == 404
    assert c.get("/stats").json["sotilgan"]["count"] == 1


# ---------------- customer-service ----------------
def test_customer_service():
    c = customer_app("sqlite:///:memory:").test_client()
    r = c.post("/customers", json={"full_name": "Sardor Aliyev", "phone": "+998 90 123 45 67", "passport": "ad1234567",
                                   "monthly_income": 15000000})
    assert r.status_code == 201 and r.json["phone"] == "+998901234567" and r.json["passport"] == "AD1234567"
    assert c.post("/customers", json={"full_name": "X", "phone": "1", "passport": "1"}).status_code == 422
    assert c.post("/customers", json={"full_name": "Boshqa", "phone": "+998901234567", "passport": "AE1234567"}).status_code == 409
    assert c.get("/customers?q=sardor").json[0]["full_name"] == "Sardor Aliyev"


# ---------------- financing-service ----------------
def test_financing_rules():
    assert annuity(120_000_000, __import__("decimal").Decimal(0), 12) == 10_000_000
    assert decide(5_000_000, 10_000_000)[0] == "tasdiqlandi"
    assert decide(6_000_000, 10_000_000)[0] == "rad_etildi"
    c = financing_app("sqlite:///:memory:").test_client()
    body = {"sale_ref": "S-1", "customer_id": 1, "amount": 100_000_000, "term_months": 36, "annual_rate": 24,
            "monthly_income": 20_000_000}
    r = c.post("/applications", json=body)
    assert r.status_code == 201 and r.json["status"] == "tasdiqlandi"
    assert c.post("/applications", json=body).status_code == 200      # idempotent
    assert c.post("/applications", json={**body, "sale_ref": "S-2", "term_months": 100}).status_code == 422


# ---------------- e2e: barcha servislar haqiqiy HTTP orqali ----------------
@pytest.fixture
def system(tmp_path):
    from run_local import serve
    ports = {n: free_port() for n in ["car-service", "customer-service", "financing-service", "sales-service", "web"]}
    url = {n: f"http://127.0.0.1:{p}" for n, p in ports.items()}
    clients = {n: ServiceClient(n, url[n]) for n in ["car-service", "customer-service", "financing-service"]}
    apps = {
        "car-service": car_app(f"sqlite:///{tmp_path / 'car.db'}"),
        "customer-service": customer_app(f"sqlite:///{tmp_path / 'customer.db'}"),
        "financing-service": financing_app(f"sqlite:///{tmp_path / 'fin.db'}"),
        "sales-service": sales_app(f"sqlite:///{tmp_path / 'sales.db'}", clients["car-service"], clients["customer-service"],
                                   clients["financing-service"]),
    }
    import os
    os.environ.update({"CAR_SERVICE_URL": url["car-service"], "CUSTOMER_SERVICE_URL": url["customer-service"],
                       "SALES_SERVICE_URL": url["sales-service"], "FINANCING_SERVICE_URL": url["financing-service"]})
    from avtosalon_web.main import create_app as web_app
    apps["web"] = web_app()
    servers = serve(apps, ports)
    yield {n: ServiceClient(n, u) for n, u in url.items()}, apps["web"]
    for s in servers:
        s.shutdown()


def test_e2e_cash_and_credit_flow(system):
    api, web = system
    sales, cars = api["sales-service"], api["car-service"]

    cash = sales.post("/sales", {"car_id": 1, "customer_id": 1, "payment_method": "naqd"})
    assert cash["status"] == "boshlangan" and cars.get("/cars/1")["status"] == "band"
    done = sales.post(f"/sales/{cash['id']}/complete", {"paid": cash["price"]})
    assert done["status"] == "yakunlangan" and cars.get("/cars/1")["status"] == "sotilgan"

    # Aziz: daromad 25 mln → kredit tasdiqlanadi
    credit = sales.post("/sales", {"car_id": 3, "customer_id": 1, "payment_method": "kredit", "down_payment": 80_000_000,
                                   "term_months": 36, "annual_rate": 24})
    assert credit["status"] == "kredit_tasdiqlangan" and credit["monthly_payment"] > 0
    assert len(api["financing-service"].get("/applications")) == 1

    # Jasur: daromad 6 mln, BMW X5 → rad etiladi; bekor qilinganda avtomobil bo'shaydi
    rejected = sales.post("/sales", {"car_id": 8, "customer_id": 3, "payment_method": "kredit", "down_payment": 300_000_000})
    assert rejected["status"] == "kredit_rad_etilgan" and "PTI" not in rejected["note"]
    sales.post(f"/sales/{rejected['id']}/cancel", {"reason": "Kredit rad etildi"})
    assert cars.get("/cars/8")["status"] == "sotuvda"

    # Band qilingan avtomobilni ikkinchi marta sotib bo'lmaydi
    from svc_common.http import ServiceError
    with pytest.raises(ServiceError) as e:
        sales.post("/sales", {"car_id": 3, "customer_id": 2, "payment_method": "naqd"})
    assert e.value.status == 409

    # Web panel barcha sahifalarni servislardan yig'adi
    c = web.test_client()
    for url in ["/", "/cars", "/customers", "/sales", f"/sales/{credit['id']}", "/financing", "/architecture"]:
        assert c.get(url).status_code == 200, url
    assert "ishlayapti" in c.get("/").get_data(as_text=True)


def test_compensation_when_financing_down(tmp_path):
    """financing-service ishlamasa — sotuv yaratilmaydi va avtomobil qayta bo'shatiladi (saga kompensatsiyasi)."""
    car = car_app(f"sqlite:///{tmp_path / 'c.db'}")
    customer = customer_app(f"sqlite:///{tmp_path / 'u.db'}")
    from run_local import serve
    pc, pu = free_port(), free_port()
    servers = serve({"car": car, "cust": customer}, {"car": pc, "cust": pu})
    try:
        sales = sales_app(f"sqlite:///{tmp_path / 's.db'}", ServiceClient("car", f"http://127.0.0.1:{pc}"),
                          ServiceClient("cust", f"http://127.0.0.1:{pu}"),
                          ServiceClient("fin", f"http://127.0.0.1:{free_port()}", timeout=0.5, retries=0)).test_client()
        r = sales.post("/sales", json={"car_id": 2, "customer_id": 1, "payment_method": "kredit", "down_payment": 50_000_000})
        assert r.status_code == 503
        assert car.test_client().get("/cars/2").json["status"] == "sotuvda"
        assert [x["status"] for x in sales.get("/sales").json] == ["bekor_qilingan"]
    finally:
        for s in servers:
            s.shutdown()


def test_web_forms_via_dashboard(system):
    """Panel formalari: avtomobil, mijoz, sotuv yaratish, yakunlash, bekor qilish, xatolarni ko'rsatish."""
    _, web = system
    c = web.test_client()
    c.get("/")
    with c.session_transaction() as s:
        s["_csrf"] = "t"

    def post(url, **data):
        return c.post(url, data={"_csrf": "t", **data}, follow_redirects=True)

    assert "Avtomobil qo&#39;shildi" in post("/cars", vin="XWBJA11CVPN000777", make="Chevrolet", model="Captiva",
                                             year="2025", price="320000000", color="Oq").get_data(as_text=True)
    assert "Validatsiya xatosi" in post("/cars", vin="BAD").get_data(as_text=True)
    assert "Mijoz qo&#39;shildi" in post("/customers", full_name="Sardor Aliyev", phone="+998901234500",
                                         passport="AD1234500", monthly_income="20000000").get_data(as_text=True)
    page = post("/sales", car_id="2", customer_id="2", payment_method="naqd").get_data(as_text=True)
    assert "yaratildi" in page
    assert "yakunlandi" in post("/sales/1/complete", paid="198000000").get_data(as_text=True)
    post("/sales", car_id="5", customer_id="1", payment_method="naqd")
    assert "bekor qilindi" in post("/sales/2/cancel", reason="test").get_data(as_text=True)
    assert "kamida" in post("/sales", car_id="6", customer_id="1", payment_method="kredit", down_payment="1").get_data(as_text=True)
    assert c.get("/sales/999").status_code == 404
    assert c.post("/cars", data={}).status_code == 400          # CSRF
    for url in ["/release", "/events", "/cars?status=sotilgan"]:
        assert c.get(url).status_code == 200, url
