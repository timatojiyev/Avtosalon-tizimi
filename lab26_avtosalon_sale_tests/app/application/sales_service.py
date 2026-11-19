"""SalesService — use case'lar: agregatni yuklaydi, amalni bajaradi, saqlaydi, hodisalarni nashr qiladi."""
from __future__ import annotations

from decimal import Decimal

from app.application.ports import CarRepository, EventBus, SaleRepository
from app.domain import DomainError, Money, PaymentMethod, Sale


class SaleNotFound(DomainError):
    pass


class SalesService:
    def __init__(self, cars: CarRepository, sales: SaleRepository, bus: EventBus):
        self._cars, self._sales, self._bus = cars, sales, bus

    def initiate_sale(self, car_id: int, customer_name: str, method: str, down_payment: int = 0) -> Sale:
        car = self._cars.get(car_id)
        if car is None:
            raise DomainError(f"Avtomobil #{car_id} topilmadi")
        sale = Sale.initiate(self._sales.next_id(), car, customer_name, PaymentMethod(method),
                             Money(down_payment) if method == PaymentMethod.CREDIT.value else None)
        return self._commit(sale)

    def request_financing(self, sale_id: str, term_months: int, annual_rate: Decimal) -> Sale:
        sale = self._load(sale_id)
        sale.request_financing(term_months, annual_rate)
        return self._commit(sale)

    def approve_financing(self, sale_id: str, amount: int | None = None, annual_rate: Decimal | None = None,
                          term_months: int | None = None) -> Sale:
        sale = self._load(sale_id)
        sale.approve_financing(Money(amount) if amount else None, annual_rate, term_months)
        return self._commit(sale)

    def reject_financing(self, sale_id: str, reason: str) -> Sale:
        sale = self._load(sale_id)
        sale.reject_financing(reason)
        return self._commit(sale)

    def switch_to_cash(self, sale_id: str) -> Sale:
        sale = self._load(sale_id)
        sale.switch_to_cash()
        return self._commit(sale)

    def complete_sale(self, sale_id: str, paid: int) -> Sale:
        sale = self._load(sale_id)
        sale.complete(Money(paid))
        return self._commit(sale)

    def cancel_sale(self, sale_id: str, reason: str = "") -> Sale:
        sale = self._load(sale_id)
        sale.cancel(reason)
        return self._commit(sale)

    def _load(self, sale_id: str) -> Sale:
        sale = self._sales.get(sale_id)
        if sale is None:
            raise SaleNotFound(f"Sotuv {sale_id} topilmadi")
        return sale

    def _commit(self, sale: Sale) -> Sale:
        self._cars.save(sale.car)
        self._sales.save(sale)
        self._bus.publish(sale.pull_events())
        return sale
