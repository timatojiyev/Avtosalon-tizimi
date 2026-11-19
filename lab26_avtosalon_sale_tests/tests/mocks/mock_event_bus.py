from __future__ import annotations

from typing import Iterable

from app.application.ports import EventBus
from app.domain import DomainEvent


class MockEventBus(EventBus):
    """Nashr qilingan hodisalarni yozib oladi (assert uchun)."""

    def __init__(self) -> None:
        self.events: list[DomainEvent] = []

    def publish(self, events: Iterable[DomainEvent]) -> None:
        self.events.extend(events)

    @property
    def names(self) -> list[str]:
        return [e.name for e in self.events]
