import pytest

from app.domain import CarNotAvailable, CarStatus, DomainError
from tests.fixtures.sale_fixtures import make_car

pytestmark = pytest.mark.unit


def test_reserve_release_sell(car):
    car.reserve()
    assert car.status == CarStatus.RESERVED
    car.release()
    assert car.status == CarStatus.AVAILABLE
    car.reserve()
    car.mark_sold()
    assert car.status == CarStatus.SOLD


def test_cannot_reserve_twice(car):
    car.reserve()
    with pytest.raises(CarNotAvailable):
        car.reserve()


@pytest.mark.parametrize("action", ["release", "mark_sold"])
def test_invalid_transitions(car, action):
    with pytest.raises(DomainError):
        getattr(car, action)()


@pytest.mark.parametrize("kwargs", [{"year": 1980}, {"year": 2031}, {"price": 0}])
def test_invalid_car(kwargs):
    with pytest.raises(DomainError):
        make_car(**kwargs)


def test_title():
    assert make_car(make="BYD", model="Song", year=2024).title == "BYD Song (2024)"
