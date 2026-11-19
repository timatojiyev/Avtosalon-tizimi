from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Iterable

from app.domain import Car, DomainEvent, Sale


class CarRepository(ABC):
    @abstractmethod
    def get(self, car_id: int) -> Car | None: ...
    @abstractmethod
    def list(self) -> list[Car]: ...
    @abstractmethod
    def save(self, car: Car) -> None: ...


class SaleRepository(ABC):
    @abstractmethod
    def get(self, sale_id: str) -> Sale | None: ...
    @abstractmethod
    def list(self) -> list[Sale]: ...
    @abstractmethod
    def save(self, sale: Sale) -> None: ...
    @abstractmethod
    def next_id(self) -> str: ...


class EventBus(ABC):
    @abstractmethod
    def publish(self, events: Iterable[DomainEvent]) -> None: ...
