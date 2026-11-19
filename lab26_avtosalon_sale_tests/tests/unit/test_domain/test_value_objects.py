from decimal import Decimal

import pytest

from app.domain import VIN, CreditTerms, DomainError, FinancingError, Money

pytestmark = pytest.mark.unit


class TestMoney:
    def test_arithmetic_and_format(self):
        assert Money(100) + Money(50) == Money(150)
        assert Money(100) - Money(40) == Money(60)
        assert str(Money(1_500_000)) == "1 500 000 so'm"
        assert Money(200_000_000).percent(20) == Money(40_000_000)

    @pytest.mark.parametrize("bad", [-1, 1.5, True, "100"])
    def test_invalid_amount(self, bad):
        with pytest.raises(DomainError):
            Money(bad)

    def test_negative_result_and_currency_mismatch(self):
        with pytest.raises(DomainError):
            Money(1) - Money(2)
        with pytest.raises(DomainError):
            Money(1) + Money(1, "USD")

    def test_ordering(self):
        assert Money(1) < Money(2) and max(Money(5), Money(3)) == Money(5)


class TestVIN:
    def test_normalized(self):
        assert str(VIN(" xwbja11cvpn000101 ")) == "XWBJA11CVPN000101"

    @pytest.mark.parametrize("bad", ["SHORT", "XWBJA11CVPN0001011", "XWBJA11CVPN00010I", "XWBJA11CVPN00010O"])
    def test_invalid(self, bad):
        with pytest.raises(DomainError):
            VIN(bad)


class TestCreditTerms:
    def test_zero_rate(self):
        t = CreditTerms(Money(60_000_000), Decimal(0), 6)
        assert t.monthly_payment == Money(10_000_000) and t.overpayment == Money(0)

    @pytest.mark.parametrize("principal, rate, term", [(0, 10, 12), (100, 10, 5), (100, 10, 61), (100, -1, 12), (100, 61, 12)])
    def test_invalid(self, principal, rate, term):
        with pytest.raises(FinancingError):
            CreditTerms(Money(principal), Decimal(rate), term)
