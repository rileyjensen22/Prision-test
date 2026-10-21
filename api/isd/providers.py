"""Where the app gets its external providers. v1 only ever returns mocks (no real network calls)."""

from isd.interfaces.payments import PaymentProvider
from isd.interfaces.telephony import TelephonyService
from isd.mocks.payments import MockPaymentProvider
from isd.mocks.telephony import MockTelephonyProvider

_telephony = TelephonyService(MockTelephonyProvider())
_payments: PaymentProvider = MockPaymentProvider()


def get_telephony() -> TelephonyService:
    return _telephony


def get_payments() -> PaymentProvider:
    return _payments


def set_telephony(service: TelephonyService) -> None:  # tests
    global _telephony
    _telephony = service
