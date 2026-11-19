"""Topshiriq №15: “Avtosalon Tizimi” — Sale aggregate testlari.

Uch asosiy jarayon:
  1. Sotuvni boshlash        — TestInitiateSale
  2. Kredit tasdiqlash       — TestFinancingRequest, TestFinancingApproval, TestFinancingRejection
  3. Sotuvni yakunlash       — TestCompleteSale
Qo'shimcha: bekor qilish, holatlar mashinasi, domen hodisalari.

Tuzilish: Arrange → Act → Assert. Fixture'lar — tests/conftest.py, fabrikalar — tests/fixtures/sale_fixtures.py.
"""
from __future__ import annotations

from decimal import Decimal

import pytest

from app.domain import (CarNotAvailable, CarStatus, DomainError, FinancingApproved, FinancingError,
                        FinancingRejected, FinancingRequested, InvalidStateTransition, Money, PaymentError,
                        PaymentMethod, Sale, SaleCancelled, SaleCompleted, SaleInitiated, SaleStatus)
from tests.fixtures.sale_fixtures import make_car, make_cash_sale, make_credit_sale

pytestmark = pytest.mark.unit

PRICE = 200_000_000          # make_car() standart narxi
MIN_DOWN = 40_000_000        # 20 %


# ====================================================================== #
# 1. Sotuvni boshlash
# ====================================================================== #
class TestInitiateSale:
    def test_cash_sale_starts_and_reserves_car(self, car):
        sale = Sale.initiate("S-1", car, "Aziz Karimov", PaymentMethod.CASH)

        assert sale.status == SaleStatus.INITIATED
        assert sale.price == car.price
        assert sale.down_payment == car.price            # naqdda to'liq summa
        assert sale.financed_amount == Money(0)
        assert car.status == CarStatus.RESERVED

    def test_credit_sale_calculates_financed_amount(self, car):
        sale = Sale.initiate("S-1", car, "Aziz Karimov", PaymentMethod.CREDIT, Money(60_000_000))

        assert sale.down_payment == Money(60_000_000)
        assert sale.financed_amount == Money(PRICE - 60_000_000)

    def test_customer_name_is_normalized(self, car):
        sale = Sale.initiate("S-1", car, "  Aziz    Karimov ", PaymentMethod.CASH)
        assert sale.customer_name == "Aziz Karimov"

    @pytest.mark.parametrize("name", ["", "  ", "Al"])
    def test_invalid_customer_name_raises(self, car, name):
        with pytest.raises(DomainError):
            Sale.initiate("S-1", car, name, PaymentMethod.CASH)
        assert car.status == CarStatus.AVAILABLE        # xato bo'lsa avtomobil band qilinmaydi

    @pytest.mark.parametrize("status", [CarStatus.RESERVED, CarStatus.SOLD])
    def test_unavailable_car_cannot_be_sold(self, status):
        car = make_car(status=status)
        with pytest.raises(CarNotAvailable):
            Sale.initiate("S-1", car, "Aziz Karimov", PaymentMethod.CASH)

    def test_same_car_cannot_be_sold_twice(self, car):
        Sale.initiate("S-1", car, "Aziz Karimov", PaymentMethod.CASH)
        with pytest.raises(CarNotAvailable):
            Sale.initiate("S-2", car, "Malika Yusupova", PaymentMethod.CASH)

    @pytest.mark.parametrize("down_payment, ok", [
        (0, False),
        (MIN_DOWN - 1, False),     # 20 % dan 1 so'm kam
        (MIN_DOWN, True),          # aynan 20 %
        (MIN_DOWN + 1, True),
        (PRICE - 1, True),
        (PRICE, False),            # to'liq summa — kredit ma'nosiz
    ])
    def test_credit_down_payment_boundaries(self, car, down_payment, ok):
        if ok:
            sale = Sale.initiate("S-1", car, "Aziz Karimov", PaymentMethod.CREDIT, Money(down_payment))
            assert sale.financed_amount == Money(PRICE - down_payment)
        else:
            with pytest.raises(FinancingError):
                Sale.initiate("S-1", car, "Aziz Karimov", PaymentMethod.CREDIT, Money(down_payment))
            assert car.status == CarStatus.AVAILABLE

    def test_initiate_records_event(self, car):
        sale = Sale.initiate("S-1", car, "Aziz Karimov", PaymentMethod.CASH)
        (event,) = sale.pull_events()

        assert isinstance(event, SaleInitiated)
        assert (event.sale_id, event.car_id, event.price, event.payment_method) == ("S-1", car.id, PRICE, "naqd")


# ====================================================================== #
# 2. Kredit: so'rash, tasdiqlash, rad etish
# ====================================================================== #
class TestFinancingRequest:
    def test_request_moves_to_pending(self, credit_sale):
        terms = credit_sale.request_financing(term_months=36, annual_rate=24)

        assert credit_sale.status == SaleStatus.FINANCING_PENDING
        assert terms.principal == credit_sale.financed_amount
        assert terms.term_months == 36 and terms.annual_rate == Decimal("24")

    def test_cash_sale_cannot_request_financing(self, cash_sale):
        with pytest.raises(FinancingError):
            cash_sale.request_financing(36, 24)

    @pytest.mark.parametrize("term, rate", [(5, 24), (61, 24), (36, -1), (36, 61)])
    def test_invalid_credit_terms(self, credit_sale, term, rate):
        with pytest.raises(FinancingError):
            credit_sale.request_financing(term, rate)
        assert credit_sale.status == SaleStatus.INITIATED   # holat o'zgarmaydi

    def test_cannot_request_twice(self, pending_sale):
        with pytest.raises(InvalidStateTransition):
            pending_sale.request_financing(36, 24)


class TestFinancingApproval:
    def test_approve_with_requested_terms(self, pending_sale):
        terms = pending_sale.approve_financing()

        assert pending_sale.status == SaleStatus.FINANCING_APPROVED
        assert terms.principal == pending_sale.financed_amount
        assert pending_sale.credit_terms == terms

    @pytest.mark.parametrize("principal, rate, term, expected_monthly", [
        (120_000_000, 0, 12, 10_000_000),          # foizsiz: 120 mln / 12
        (120_000_000, 24, 12, 11_347_152),         # annuitet, oyiga 2 %
        (160_000_000, 24, 36, 6_277_256),
        (100_000_000, 12, 60, 2_224_445),
    ])
    def test_monthly_payment_annuity(self, principal, rate, term, expected_monthly):
        car = make_car(price=principal + 50_000_000)
        sale = make_credit_sale(car=car, down_payment=50_000_000)
        sale.request_financing(term, rate)

        terms = sale.approve_financing()

        assert terms.monthly_payment == Money(expected_monthly)
        assert terms.total_payable.amount == expected_monthly * term
        assert terms.overpayment.amount == expected_monthly * term - principal

    def test_bank_can_approve_less_and_difference_goes_to_down_payment(self, pending_sale):
        requested = pending_sale.financed_amount.amount
        down_before = pending_sale.down_payment.amount

        terms = pending_sale.approve_financing(approved_amount=Money(requested - 20_000_000))

        assert terms.principal == Money(requested - 20_000_000)
        assert pending_sale.down_payment == Money(down_before + 20_000_000)
        assert pending_sale.down_payment.amount + terms.principal.amount == PRICE

    def test_bank_can_change_rate_and_term(self, pending_sale):
        terms = pending_sale.approve_financing(annual_rate=Decimal("18.5"), term_months=48)
        assert terms.annual_rate == Decimal("18.5") and terms.term_months == 48

    def test_cannot_approve_more_than_requested(self, pending_sale):
        with pytest.raises(FinancingError):
            pending_sale.approve_financing(approved_amount=pending_sale.financed_amount + Money(1))
        assert pending_sale.status == SaleStatus.FINANCING_PENDING

    def test_cannot_approve_without_request(self, credit_sale):
        with pytest.raises(InvalidStateTransition):
            credit_sale.approve_financing()

    def test_approval_records_event_with_monthly_payment(self, pending_sale):
        pending_sale.pull_events()
        terms = pending_sale.approve_financing()
        (event,) = pending_sale.pull_events()

        assert isinstance(event, FinancingApproved)
        assert event.monthly_payment == terms.monthly_payment.amount


class TestFinancingRejection:
    def test_reject_with_reason(self, pending_sale):
        pending_sale.reject_financing("Kredit tarixi salbiy")

        assert pending_sale.status == SaleStatus.FINANCING_REJECTED
        assert pending_sale.financing_reject_reason == "Kredit tarixi salbiy"
        assert isinstance(pending_sale.pull_events()[-1], FinancingRejected)

    def test_reason_is_required(self, pending_sale):
        with pytest.raises(FinancingError):
            pending_sale.reject_financing("   ")

    def test_rejected_sale_cannot_be_completed(self, pending_sale):
        pending_sale.reject_financing("Daromad yetarli emas")
        with pytest.raises(InvalidStateTransition):
            pending_sale.complete(Money(PRICE))

    def test_switch_to_cash_after_rejection(self, pending_sale):
        pending_sale.reject_financing("Daromad yetarli emas")

        pending_sale.switch_to_cash()
        pending_sale.complete(Money(PRICE))

        assert pending_sale.payment_method == PaymentMethod.CASH
        assert pending_sale.status == SaleStatus.COMPLETED
        assert pending_sale.credit_terms is None


# ====================================================================== #
# 3. Sotuvni yakunlash
# ====================================================================== #
class TestCompleteSale:
    def test_complete_cash_sale(self, cash_sale):
        cash_sale.complete(Money(PRICE))

        assert cash_sale.status == SaleStatus.COMPLETED
        assert cash_sale.car.status == CarStatus.SOLD
        assert cash_sale.completed_at is not None
        assert cash_sale.change == Money(0)

    def test_overpayment_gives_change(self, cash_sale):
        cash_sale.complete(Money(PRICE + 500_000))
        assert cash_sale.change == Money(500_000)

    @pytest.mark.parametrize("paid", [0, 1, PRICE - 1])
    def test_cash_insufficient_payment(self, cash_sale, paid):
        with pytest.raises(PaymentError):
            cash_sale.complete(Money(paid))
        assert cash_sale.status == SaleStatus.INITIATED
        assert cash_sale.car.status == CarStatus.RESERVED

    def test_complete_credit_sale_requires_only_down_payment(self, approved_sale):
        approved_sale.complete(approved_sale.down_payment)

        assert approved_sale.status == SaleStatus.COMPLETED
        assert approved_sale.car.status == CarStatus.SOLD

    def test_credit_down_payment_not_paid(self, approved_sale):
        with pytest.raises(PaymentError):
            approved_sale.complete(approved_sale.down_payment - Money(1))

    @pytest.mark.parametrize("stage", ["initiated", "pending"])
    def test_credit_sale_cannot_complete_before_approval(self, stage):
        sale = make_credit_sale()
        if stage == "pending":
            sale.request_financing(36, 24)
        with pytest.raises(InvalidStateTransition):
            sale.complete(Money(PRICE))

    def test_cannot_complete_twice(self, cash_sale):
        cash_sale.complete(Money(PRICE))
        with pytest.raises(InvalidStateTransition):
            cash_sale.complete(Money(PRICE))

    def test_completion_event(self, approved_sale):
        approved_sale.pull_events()
        approved_sale.complete(approved_sale.down_payment)
        (event,) = approved_sale.pull_events()

        assert isinstance(event, SaleCompleted)
        assert event.payment_method == "kredit"
        assert event.financed_amount == approved_sale.credit_terms.principal.amount
        assert event.amount_paid == approved_sale.down_payment.amount


# ====================================================================== #
# Bekor qilish
# ====================================================================== #
class TestCancelSale:
    @pytest.mark.parametrize("stage", ["initiated", "pending", "approved", "rejected"])
    def test_cancel_releases_car(self, stage):
        sale = make_credit_sale()
        if stage in ("pending", "approved", "rejected"):
            sale.request_financing(36, 24)
        if stage == "approved":
            sale.approve_financing()
        if stage == "rejected":
            sale.reject_financing("Rad etildi")

        sale.cancel("Mijoz fikridan qaytdi")

        assert sale.status == SaleStatus.CANCELLED
        assert sale.car.status == CarStatus.AVAILABLE
        assert isinstance(sale.pull_events()[-1], SaleCancelled)

    def test_completed_sale_cannot_be_cancelled(self, cash_sale):
        cash_sale.complete(Money(PRICE))
        with pytest.raises(InvalidStateTransition):
            cash_sale.cancel()
        assert cash_sale.car.status == CarStatus.SOLD

    def test_cancelled_car_can_be_sold_again(self, cash_sale):
        cash_sale.cancel()
        new_sale = Sale.initiate("S-2", cash_sale.car, "Malika Yusupova", PaymentMethod.CASH)
        assert new_sale.car.status == CarStatus.RESERVED


# ====================================================================== #
# To'liq jarayonlar va hodisalar ketma-ketligi
# ====================================================================== #
class TestSaleLifecycle:
    def test_full_credit_flow_event_sequence(self, car):
        sale = Sale.initiate("S-9", car, "Aziz Karimov", PaymentMethod.CREDIT, Money(MIN_DOWN))
        sale.request_financing(36, 24)
        sale.approve_financing()
        sale.complete(Money(MIN_DOWN))

        names = [type(e).__name__ for e in sale.pull_events()]
        assert names == ["SaleInitiated", "FinancingRequested", "FinancingApproved", "SaleCompleted"]
        assert sale.pull_events() == []                   # hodisalar bir marta olinadi

    def test_failed_action_does_not_record_event(self, cash_sale):
        cash_sale.pull_events()
        with pytest.raises(PaymentError):
            cash_sale.complete(Money(1))
        assert cash_sale.pending_events == ()

    @pytest.mark.parametrize("factory, final_status", [
        (lambda: make_cash_sale(), SaleStatus.COMPLETED),
        (lambda: make_credit_sale(), SaleStatus.CANCELLED),
    ])
    def test_final_states_are_terminal(self, factory, final_status):
        sale = factory()
        if final_status == SaleStatus.COMPLETED:
            sale.complete(sale.price)
        else:
            sale.cancel()
        assert sale.status.is_final
        with pytest.raises(InvalidStateTransition):
            sale.cancel()

    def test_financing_requested_event_payload(self, credit_sale):
        credit_sale.pull_events()
        credit_sale.request_financing(24, Decimal("19.9"))
        (event,) = credit_sale.pull_events()
        assert isinstance(event, FinancingRequested)
        assert event.to_dict()["event"] == "sale.financing_requested"
        assert event.annual_rate == "19.9" and event.amount == credit_sale.financed_amount.amount
