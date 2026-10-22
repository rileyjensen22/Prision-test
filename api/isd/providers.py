"""Where the app gets its external providers. v1 only ever returns mocks (no real network calls)."""

from isd.interfaces.chess import ChessProvider
from isd.interfaces.messaging import MessagingService
from isd.interfaces.payments import PaymentProvider
from isd.interfaces.sso import SSOProvider
from isd.interfaces.telephony import TelephonyService
from isd.interfaces.verification import ContactVerifier
from isd.interfaces.video import VideoService
from isd.mocks.chess import MockChessProvider
from isd.mocks.messaging import MockMessagingProvider
from isd.mocks.payments import MockPaymentProvider
from isd.mocks.sso import MockSSOProvider
from isd.mocks.telephony import MockTelephonyProvider
from isd.mocks.verification import MockContactVerifier
from isd.mocks.video import MockVideoProvider

_telephony = TelephonyService(MockTelephonyProvider())
_payments: PaymentProvider = MockPaymentProvider()
_messaging = MessagingService(MockMessagingProvider())
_chess: ChessProvider = MockChessProvider()
_sso: SSOProvider = MockSSOProvider()
_video = VideoService(MockVideoProvider())
_verifier: ContactVerifier = MockContactVerifier()


def get_telephony() -> TelephonyService:
    return _telephony


def get_payments() -> PaymentProvider:
    return _payments


def set_telephony(service: TelephonyService) -> None:  # tests
    global _telephony
    _telephony = service


def get_messaging() -> MessagingService:
    return _messaging


def get_chess() -> ChessProvider:
    return _chess


def set_messaging(service: MessagingService) -> None:  # tests
    global _messaging
    _messaging = service


def get_sso() -> SSOProvider:
    return _sso


def get_video() -> VideoService:
    return _video


def set_video(service: VideoService) -> None:  # tests
    global _video
    _video = service


def get_verifier() -> ContactVerifier:
    return _verifier
