"""Car entity — avtomobil va uning sotuvdagi holati."""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from app.domain.exceptions import CarNotAvailable, DomainError
from app.domain.value_objects import VIN, Money


class CarStatus(str, Enum):
    AVAILABLE = "sotuvda"
    RESERVED = "band"
    SOLD = "sotilgan"


@dataclass
class Car:
    id: int
    vin: VIN
    make: str
    model: str
    year: int
    price: Money
    status: CarStatus = CarStatus.AVAILABLE

    def __post_init__(self) -> None:
        if not 1990 <= self.year <= 2030:
            raise DomainError("Ishlab chiqarilgan yil noto'g'ri")
        if self.price.amount <= 0:
            raise DomainError("Narx musbat bo'lishi kerak")

    @property
    def title(self) -> str:
        return f"{self.make} {self.model} ({self.year})"

    def reserve(self) -> None:
        if self.status != CarStatus.AVAILABLE:
            raise CarNotAvailable(f"{self.title} sotuvga mavjud emas (holati: {self.status.value})")
        self.status = CarStatus.RESERVED

    def release(self) -> None:
        if self.status != CarStatus.RESERVED:
            raise DomainError("Faqat band qilingan avtomobilni bo'shatish mumkin")
        self.status = CarStatus.AVAILABLE

    def mark_sold(self) -> None:
        if self.status != CarStatus.RESERVED:
            raise DomainError("Avtomobil avval band qilinishi kerak")
        self.status = CarStatus.SOLD
