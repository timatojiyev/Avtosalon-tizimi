"""Sale aggregate — avtomobil sotuvi.

Holatlar oqimi::

    initiate() ─► BOSHLANGAN ──(naqd)──────────────────────────► complete() ─► YAKUNLANGAN
                      │
                      └─(kredit) request_financing() ─► KREDIT_KUTILMOQDA
                                     ├─ approve_financing() ─► KREDIT_TASDIQLANGAN ─► complete() ─► YAKUNLANGAN
                                     └─ reject_financing()  ─► KREDIT_RAD_ETILGAN ─► switch_to_cash() / cancel()
    cancel() — yakunlanmagan istalgan holatdan ─► BEKOR_QILINGAN (avtomobil bo'shatiladi)

Biznes qoidalari:
  * faqat sotuvdagi avtomobil sotilishi mumkin (initiate avtomobilni band qiladi);
  * kreditda boshlang'ich to'lov narxning kamida 20 % i, kredit summasi = narx − boshlang'ich to'lov;
  * bank tasdiqlagan summa so'ralganidan oshmasligi kerak (kam bo'lsa, farq boshlang'ich to'lovga qo'shiladi);
  * yakunlashda to'langan summa yetarli bo'lishi shart: naqd — to'liq narx, kredit — boshlang'ich to'lov;
  * yakunlangan sotuvni o'zgartirib yoki bekor qilib bo'lmaydi.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from enum import Enum

from app.domain.car import Car
from app.domain.events import (DomainEvent, FinancingApproved, FinancingRejected, FinancingRequested,
                               SaleCancelled, SaleCompleted, SaleInitiated)
from app.domain.exceptions import DomainError, FinancingError, InvalidStateTransition, PaymentError
from app.domain.value_objects import CreditTerms, Money

MIN_DOWN_PAYMENT_PCT = 20


class PaymentMethod(str, Enum):
    CASH = "naqd"
    CREDIT = "kredit"


class SaleStatus(str, Enum):
    INITIATED = "boshlangan"
    FINANCING_PENDING = "kredit_kutilmoqda"
    FINANCING_APPROVED = "kredit_tasdiqlangan"
    FINANCING_REJECTED = "kredit_rad_etilgan"
    COMPLETED = "yakunlangan"
    CANCELLED = "bekor_qilingan"

    @property
    def label(self) -> str:
        return {"boshlangan": "Boshlangan", "kredit_kutilmoqda": "Kredit kutilmoqda",
                "kredit_tasdiqlangan": "Kredit tasdiqlangan", "kredit_rad_etilgan": "Kredit rad etilgan",
                "yakunlangan": "Yakunlangan", "bekor_qilingan": "Bekor qilingan"}[self.value]

    @property
    def is_final(self) -> bool:
        return self in (SaleStatus.COMPLETED, SaleStatus.CANCELLED)


def _now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass
class Sale:
    id: str
    car: Car
    customer_name: str
    payment_method: PaymentMethod
    price: Money
    down_payment: Money
    status: SaleStatus = SaleStatus.INITIATED
    credit_terms: CreditTerms | None = None
    financing_reject_reason: str = ""
    amount_paid: Money = field(default_factory=lambda: Money(0))
    created_at: datetime = field(default_factory=_now)
    completed_at: datetime | None = None
    _events: list[DomainEvent] = field(default_factory=list, repr=False)

    # ------------------------------------------------------------------ #
    # 1. Sotuvni boshlash
    # ------------------------------------------------------------------ #
    @classmethod
    def initiate(cls, sale_id: str, car: Car, customer_name: str, payment_method: PaymentMethod,
                 down_payment: Money | None = None) -> "Sale":
        customer_name = " ".join(customer_name.split())
        if len(customer_name) < 3:
            raise DomainError("Mijoz ismi kamida 3 belgidan iborat bo'lishi kerak")
        price = car.price
        if payment_method == PaymentMethod.CREDIT:
            down_payment = down_payment or Money(0)
            minimum = price.percent(MIN_DOWN_PAYMENT_PCT)
            if down_payment < minimum:
                raise FinancingError(f"Boshlang'ich to'lov kamida {MIN_DOWN_PAYMENT_PCT}% ({minimum}) bo'lishi kerak")
            if down_payment >= price:
                raise FinancingError("Boshlang'ich to'lov narxdan kam bo'lishi kerak — aks holda naqd to'lov tanlang")
        else:
            down_payment = price
        car.reserve()  # avtomobil sotuvda bo'lmasa CarNotAvailable
        sale = cls(sale_id, car, customer_name, payment_method, price, down_payment)
        sale._record(SaleInitiated(sale_id, car.id, customer_name, payment_method.value, price.amount))
        return sale

    # ------------------------------------------------------------------ #
    # 2. Kredit
    # ------------------------------------------------------------------ #
    @property
    def financed_amount(self) -> Money:
        return self.price - self.down_payment if self.payment_method == PaymentMethod.CREDIT else Money(0)

    def request_financing(self, term_months: int, annual_rate: Decimal | int | float) -> CreditTerms:
        self._require(SaleStatus.INITIATED)
        if self.payment_method != PaymentMethod.CREDIT:
            raise FinancingError("Naqd sotuv uchun kredit so'rab bo'lmaydi")
        terms = CreditTerms(self.financed_amount, Decimal(str(annual_rate)), term_months)
        self.credit_terms = terms
        self.status = SaleStatus.FINANCING_PENDING
        self._record(FinancingRequested(self.id, terms.principal.amount, term_months, str(terms.annual_rate)))
        return terms

    def approve_financing(self, approved_amount: Money | None = None, annual_rate: Decimal | int | float | None = None,
                          term_months: int | None = None) -> CreditTerms:
        """Bank kreditni tasdiqladi. Shartlar so'ralganidan farq qilishi mumkin (summa kamroq, foiz boshqa)."""
        self._require(SaleStatus.FINANCING_PENDING)
        requested = self.credit_terms
        assert requested is not None
        amount = approved_amount or requested.principal
        if amount > requested.principal:
            raise FinancingError("Tasdiqlangan summa so'ralganidan oshmasligi kerak")
        approved = CreditTerms(amount, Decimal(str(annual_rate if annual_rate is not None else requested.annual_rate)),
                               term_months or requested.term_months)
        shortfall = requested.principal - amount
        if shortfall.amount:
            self.down_payment = self.down_payment + shortfall  # kam berilgan qism boshlang'ich to'lovga qo'shiladi
        self.credit_terms = approved
        self.status = SaleStatus.FINANCING_APPROVED
        self._record(FinancingApproved(self.id, amount.amount, approved.term_months, str(approved.annual_rate),
                                       approved.monthly_payment.amount))
        return approved

    def reject_financing(self, reason: str) -> None:
        self._require(SaleStatus.FINANCING_PENDING)
        if not reason.strip():
            raise FinancingError("Rad etish sababi ko'rsatilishi kerak")
        self.status = SaleStatus.FINANCING_REJECTED
        self.financing_reject_reason = reason.strip()
        self._record(FinancingRejected(self.id, self.financing_reject_reason))

    def switch_to_cash(self) -> None:
        """Kredit rad etilgach mijoz naqd to'lashga rozi bo'lsa."""
        self._require(SaleStatus.FINANCING_REJECTED)
        self.payment_method = PaymentMethod.CASH
        self.down_payment = self.price
        self.credit_terms = None
        self.status = SaleStatus.INITIATED

    # ------------------------------------------------------------------ #
    # 3. Yakunlash / bekor qilish
    # ------------------------------------------------------------------ #
    @property
    def amount_due_at_completion(self) -> Money:
        return self.price if self.payment_method == PaymentMethod.CASH else self.down_payment

    def complete(self, paid: Money) -> None:
        expected = SaleStatus.INITIATED if self.payment_method == PaymentMethod.CASH else SaleStatus.FINANCING_APPROVED
        self._require(expected)
        due = self.amount_due_at_completion
        if paid < due:
            raise PaymentError(f"To'lov yetarli emas: {paid} to'landi, {due} kerak")
        self.amount_paid = paid
        self.car.mark_sold()
        self.status = SaleStatus.COMPLETED
        self.completed_at = _now()
        self._record(SaleCompleted(self.id, self.car.id, self.price.amount, paid.amount, self.payment_method.value,
                                   self.financed_amount.amount if self.credit_terms else 0))

    def cancel(self, reason: str = "") -> None:
        if self.status.is_final:
            raise InvalidStateTransition(f"“{self.status.label}” sotuvni bekor qilib bo'lmaydi")
        self.car.release()
        self.status = SaleStatus.CANCELLED
        self._record(SaleCancelled(self.id, self.car.id, reason.strip()))

    # ------------------------------------------------------------------ #
    @property
    def change(self) -> Money:
        """Qaytim (ortiqcha to'langan summa)."""
        return self.amount_paid - self.amount_due_at_completion if self.status == SaleStatus.COMPLETED else Money(0)

    def pull_events(self) -> list[DomainEvent]:
        events, self._events = self._events, []
        return events

    @property
    def pending_events(self) -> tuple[DomainEvent, ...]:
        return tuple(self._events)

    def _record(self, event: DomainEvent) -> None:
        self._events.append(event)

    def _require(self, *allowed: SaleStatus) -> None:
        if self.status not in allowed:
            names = ", ".join(s.label for s in allowed)
            raise InvalidStateTransition(f"Amal “{self.status.label}” holatida bajarilmaydi (kerak: {names})")
