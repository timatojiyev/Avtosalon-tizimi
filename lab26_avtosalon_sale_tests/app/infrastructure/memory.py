"""Xotiradagi repository va event bus (web demo uchun)."""
from __future__ import annotations

import itertools
import threading
from typing import Iterable

from app.application.ports import CarRepository, EventBus, SaleRepository
from app.domain import VIN, Car, DomainEvent, Money, Sale

DEMO_CARS = [
    (1, "XWBJA11CVPN000101", "Chevrolet", "Cobalt", 2025, 165_000_000),
    (2, "XWBJA11CVPN000102", "Chevrolet", "Onix", 2025, 198_000_000),
    (3, "XWBJA11CVPN000103", "Chevrolet", "Tracker", 2025, 265_000_000),
    (4, "LGWEF4A51RF000104", "BYD", "Song Plus", 2025, 420_000_000),
    (5, "LGWEF4A51RF000105", "BYD", "Chazor", 2024, 310_000_000),
    (6, "KMHL341CBRA000106", "Kia", "K5", 2024, 385_000_000),
    (7, "XWBJA11CVPN000107", "Chevrolet", "Malibu 2", 2025, 395_000_000),
    (8, "WBA11AA0XRCN00108", "BMW", "X5", 2024, 1_350_000_000),
]


class InMemoryCarRepository(CarRepository):
    def __init__(self, seed: bool = True):
        self._cars: dict[int, Car] = {}
        if seed:
            for cid, vin, make, model, year, price in DEMO_CARS:
                self._cars[cid] = Car(cid, VIN(vin), make, model, year, Money(price))

    def get(self, car_id: int) -> Car | None:
        return self._cars.get(car_id)

    def list(self) -> list[Car]:
        return sorted(self._cars.values(), key=lambda c: c.id)

    def save(self, car: Car) -> None:
        self._cars[car.id] = car


class InMemorySaleRepository(SaleRepository):
    def __init__(self) -> None:
        self._sales: dict[str, Sale] = {}
        self._seq = itertools.count(1)
        self._lock = threading.Lock()

    def get(self, sale_id: str) -> Sale | None:
        return self._sales.get(sale_id)

    def list(self) -> list[Sale]:
        return sorted(self._sales.values(), key=lambda s: s.created_at, reverse=True)

    def save(self, sale: Sale) -> None:
        self._sales[sale.id] = sale

    def next_id(self) -> str:
        with self._lock:
            return f"S-{next(self._seq):04d}"


class InMemoryEventBus(EventBus):
    def __init__(self) -> None:
        self.published: list[DomainEvent] = []

    def publish(self, events: Iterable[DomainEvent]) -> None:
        self.published.extend(events)
