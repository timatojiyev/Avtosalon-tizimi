"""Umumiy fixture'lar."""
from __future__ import annotations

import pytest

from app.domain import Car, Sale
from tests.fixtures.sale_fixtures import make_car, make_cash_sale, make_credit_sale
from tests.mocks.mock_event_bus import MockEventBus


@pytest.fixture
def car() -> Car:
    """Sotuvdagi avtomobil, narxi 200 000 000 so'm."""
    return make_car()


@pytest.fixture
def cash_sale(car: Car) -> Sale:
    return make_cash_sale(car)


@pytest.fixture
def credit_sale(car: Car) -> Sale:
    """Kreditli sotuv: boshlang'ich to'lov 20 %."""
    return make_credit_sale(car)


@pytest.fixture
def pending_sale(credit_sale: Sale) -> Sale:
    """Kredit so'ralgan: 36 oy, yillik 24 %."""
    credit_sale.request_financing(36, 24)
    return credit_sale


@pytest.fixture
def approved_sale(pending_sale: Sale) -> Sale:
    pending_sale.approve_financing()
    return pending_sale


@pytest.fixture
def event_bus() -> MockEventBus:
    return MockEventBus()
