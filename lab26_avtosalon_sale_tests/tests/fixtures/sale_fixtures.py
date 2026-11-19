"""Test ma'lumotlari fabrikalari (Factory pattern) — testlarda takrorlanishni kamaytiradi."""
from __future__ import annotations

import itertools

from app.domain import VIN, Car, CarStatus, Money, PaymentMethod, Sale

_ids = itertools.count(1)
DEFAULT_PRICE = 200_000_000


def make_car(price: int = DEFAULT_PRICE, status: CarStatus = CarStatus.AVAILABLE, make: str = "Chevrolet",
             model: str = "Tracker", year: int = 2025) -> Car:
    n = next(_ids)
    return Car(n, VIN(f"XWBJA11CVPN{n:06d}"), make, model, year, Money(price), status)


def make_cash_sale(car: Car | None = None, customer: str = "Aziz Karimov") -> Sale:
    car = car or make_car()
    return Sale.initiate(f"S-{car.id}", car, customer, PaymentMethod.CASH)


def make_credit_sale(car: Car | None = None, down_payment: int | None = None, customer: str = "Aziz Karimov") -> Sale:
    car = car or make_car()
    down = Money(down_payment) if down_payment is not None else car.price.percent(20)
    return Sale.initiate(f"S-{car.id}", car, customer, PaymentMethod.CREDIT, down)
