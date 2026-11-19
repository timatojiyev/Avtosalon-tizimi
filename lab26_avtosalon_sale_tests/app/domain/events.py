"""Sale agregati hodisalari."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, ClassVar


@dataclass(frozen=True)
class DomainEvent:
    name: ClassVar[str] = "event"

    def to_dict(self) -> dict[str, Any]:
        return {"event": self.name, **asdict(self)}


def _ts() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass(frozen=True)
class SaleInitiated(DomainEvent):
    name: ClassVar[str] = "sale.initiated"
    sale_id: str
    car_id: int
    customer_name: str
    payment_method: str
    price: int
    at: str = field(default_factory=_ts)


@dataclass(frozen=True)
class FinancingRequested(DomainEvent):
    name: ClassVar[str] = "sale.financing_requested"
    sale_id: str
    amount: int
    term_months: int
    annual_rate: str
    at: str = field(default_factory=_ts)


@dataclass(frozen=True)
class FinancingApproved(DomainEvent):
    name: ClassVar[str] = "sale.financing_approved"
    sale_id: str
    amount: int
    term_months: int
    annual_rate: str
    monthly_payment: int
    at: str = field(default_factory=_ts)


@dataclass(frozen=True)
class FinancingRejected(DomainEvent):
    name: ClassVar[str] = "sale.financing_rejected"
    sale_id: str
    reason: str
    at: str = field(default_factory=_ts)


@dataclass(frozen=True)
class SaleCompleted(DomainEvent):
    name: ClassVar[str] = "sale.completed"
    sale_id: str
    car_id: int
    price: int
    amount_paid: int
    payment_method: str
    financed_amount: int
    at: str = field(default_factory=_ts)


@dataclass(frozen=True)
class SaleCancelled(DomainEvent):
    name: ClassVar[str] = "sale.cancelled"
    sale_id: str
    car_id: int
    reason: str
    at: str = field(default_factory=_ts)
