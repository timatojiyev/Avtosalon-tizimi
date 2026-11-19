"""SalesService — mock repository va mock event bus bilan."""
from decimal import Decimal

import pytest

from app.application.sales_service import SaleNotFound, SalesService
from app.domain import CarStatus, DomainError, SaleStatus
from tests.fixtures.sale_fixtures import make_car
from tests.mocks.mock_repository import MockCarRepository, MockSaleRepository

pytestmark = pytest.mark.unit


@pytest.fixture
def setup(event_bus):
    car = make_car(price=100_000_000)
    cars = MockCarRepository(car)
    service = SalesService(cars, MockSaleRepository(), event_bus)
    return service, car, cars, event_bus


def test_credit_flow_publishes_events(setup):
    service, car, cars, bus = setup
    sale = service.initiate_sale(car.id, "Aziz Karimov", "kredit", 30_000_000)
    service.request_financing(sale.id, 24, Decimal(20))
    service.approve_financing(sale.id)
    service.complete_sale(sale.id, 30_000_000)
    assert bus.names == ["sale.initiated", "sale.financing_requested", "sale.financing_approved", "sale.completed"]
    assert cars.get(car.id).status == CarStatus.SOLD and cars.saved == 4


def test_reject_switch_cancel(setup):
    service, car, _, bus = setup
    sale = service.initiate_sale(car.id, "Aziz Karimov", "kredit", 30_000_000)
    service.request_financing(sale.id, 24, Decimal(20))
    service.reject_financing(sale.id, "Rad")
    service.switch_to_cash(sale.id)
    assert service.cancel_sale(sale.id).status == SaleStatus.CANCELLED
    assert bus.names[-1] == "sale.cancelled"


def test_partial_approval(setup):
    service, car, _, _ = setup
    sale = service.initiate_sale(car.id, "Aziz Karimov", "kredit", 30_000_000)
    service.request_financing(sale.id, 24, Decimal(20))
    sale = service.approve_financing(sale.id, amount=60_000_000, annual_rate=Decimal(22), term_months=12)
    assert sale.down_payment.amount == 40_000_000


def test_errors(setup):
    service, *_ = setup
    with pytest.raises(DomainError):
        service.initiate_sale(999, "Aziz Karimov", "naqd")
    with pytest.raises(SaleNotFound):
        service.complete_sale("S-404", 1)
