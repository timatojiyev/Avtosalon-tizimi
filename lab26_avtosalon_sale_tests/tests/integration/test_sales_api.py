"""Web/HTTP darajasidagi testlar (Flask test client)."""
import re

import pytest

from app.web import create_app

pytestmark = pytest.mark.integration


@pytest.fixture
def client():
    app = create_app()
    app.config["TESTING"] = True
    c = app.test_client()
    c.get("/")
    with c.session_transaction() as s:
        s["_csrf"] = "t"
    return c


def post(c, url, **data):
    return c.post(url, data={"_csrf": "t", **data})


def test_pages(client):
    for url in ["/", "/sales/new?car_id=1", "/architecture", "/api/sales"]:
        assert client.get(url).status_code == 200, url


def test_full_credit_flow_via_http(client):
    r = post(client, "/sales", car_id="3", customer_name="Aziz Karimov", method="kredit", down_payment="60000000")
    assert r.status_code == 302
    sale_url = r.headers["Location"]
    sale_id = sale_url.rsplit("/", 1)[1]
    assert post(client, f"/sales/{sale_id}/financing", term_months="36", annual_rate="24").status_code == 302
    assert post(client, f"/sales/{sale_id}/approve").status_code == 302
    assert post(client, f"/sales/{sale_id}/complete", paid="60000000").status_code == 302
    html = client.get(sale_url).get_data(as_text=True)
    assert "Yakunlangan" in html
    assert client.get("/api/sales").get_json()[0]["status"] == "yakunlangan"


def test_domain_error_is_shown(client):
    r = post(client, "/sales", car_id="1", customer_name="Aziz Karimov", method="kredit", down_payment="1000")
    assert r.status_code == 302
    assert re.search("kamida 20%", client.get(r.headers["Location"]).get_data(as_text=True))


def test_csrf_required(client):
    assert client.post("/sales", data={"car_id": "1"}).status_code == 400
