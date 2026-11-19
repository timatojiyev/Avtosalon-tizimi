"""Value object'lar: Money, VIN, CreditTerms."""
from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal

from app.domain.exceptions import DomainError, FinancingError

_VIN_RE = re.compile(r"^[A-HJ-NPR-Z0-9]{17}$")   # I, O, Q harflari VIN'da ishlatilmaydi


@dataclass(frozen=True, order=True)
class Money:
    """Pul miqdori — butun so'mda. O'zgarmas, manfiy bo'lmaydi."""

    amount: int
    currency: str = "UZS"

    def __post_init__(self) -> None:
        if not isinstance(self.amount, int) or isinstance(self.amount, bool):
            raise DomainError("Money.amount butun son bo'lishi kerak")
        if self.amount < 0:
            raise DomainError("Pul miqdori manfiy bo'lishi mumkin emas")

    def __add__(self, other: "Money") -> "Money":
        self._same(other)
        return Money(self.amount + other.amount, self.currency)

    def __sub__(self, other: "Money") -> "Money":
        self._same(other)
        if other.amount > self.amount:
            raise DomainError("Natija manfiy bo'lib qoladi")
        return Money(self.amount - other.amount, self.currency)

    def percent(self, pct: int | float | Decimal) -> "Money":
        value = (Decimal(self.amount) * Decimal(str(pct)) / 100).quantize(Decimal(1), ROUND_HALF_UP)
        return Money(int(value), self.currency)

    def _same(self, other: "Money") -> None:
        if self.currency != other.currency:
            raise DomainError("Valyutalar mos emas")

    def __str__(self) -> str:
        return f"{self.amount:,}".replace(",", " ") + (" so'm" if self.currency == "UZS" else f" {self.currency}")


@dataclass(frozen=True)
class VIN:
    value: str

    def __post_init__(self) -> None:
        v = self.value.strip().upper()
        if not _VIN_RE.match(v):
            raise DomainError(f"VIN noto'g'ri: {self.value!r} (17 belgi, I/O/Q harflarisiz)")
        object.__setattr__(self, "value", v)

    def __str__(self) -> str:
        return self.value


MIN_TERM, MAX_TERM = 6, 60
MAX_RATE = 60


@dataclass(frozen=True)
class CreditTerms:
    """Kredit shartlari: summa, yillik foiz, muddat (oy). Oylik to'lov — annuitet formulasi."""

    principal: Money
    annual_rate: Decimal
    term_months: int

    def __post_init__(self) -> None:
        if self.principal.amount <= 0:
            raise FinancingError("Kredit summasi musbat bo'lishi kerak")
        if not MIN_TERM <= self.term_months <= MAX_TERM:
            raise FinancingError(f"Muddat {MIN_TERM}–{MAX_TERM} oy bo'lishi kerak")
        if not Decimal(0) <= Decimal(self.annual_rate) <= MAX_RATE:
            raise FinancingError(f"Yillik foiz 0–{MAX_RATE}% oralig'ida bo'lishi kerak")
        object.__setattr__(self, "annual_rate", Decimal(str(self.annual_rate)))

    @property
    def monthly_payment(self) -> Money:
        p, n = Decimal(self.principal.amount), self.term_months
        r = self.annual_rate / Decimal(1200)
        payment = p / n if r == 0 else p * r / (1 - (1 + r) ** -n)
        return Money(int(payment.quantize(Decimal(1), ROUND_HALF_UP)))

    @property
    def total_payable(self) -> Money:
        return Money(self.monthly_payment.amount * self.term_months)

    @property
    def overpayment(self) -> Money:
        return self.total_payable - self.principal
