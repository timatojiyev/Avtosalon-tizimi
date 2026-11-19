"""Domen xatoliklari."""


class DomainError(Exception):
    """Biznes qoidasi buzilganda."""


class InvalidStateTransition(DomainError):
    """Agregat joriy holatida bu amalni bajarib bo'lmaydi."""


class CarNotAvailable(DomainError):
    """Avtomobil sotuvga mavjud emas (band yoki sotilgan)."""


class FinancingError(DomainError):
    """Kredit shartlari noto'g'ri."""


class PaymentError(DomainError):
    """To'lov summasi yetarli emas yoki noto'g'ri."""
