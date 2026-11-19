from __future__ import annotations

from app.infrastructure.memory import InMemoryCarRepository, InMemorySaleRepository


class MockCarRepository(InMemoryCarRepository):
    """Bo'sh avtomobil repository'si + saqlash chaqiruvlari hisobi."""

    def __init__(self, *cars):  # type: ignore[no-untyped-def]
        super().__init__(seed=False)
        self.saved = 0
        for c in cars:
            super().save(c)

    def save(self, car):  # type: ignore[no-untyped-def]
        self.saved += 1
        super().save(car)


class MockSaleRepository(InMemorySaleRepository):
    pass
