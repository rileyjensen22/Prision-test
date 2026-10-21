import hashlib

from isd.interfaces.payments import DepositResult


class MockPaymentProvider:
    """Simulated family deposits: always succeeds; same idempotency key gives the same id."""

    def create_deposit(
        self, resident_ref: str, amount_cents: int, payer_ref: str, idempotency_key: str
    ) -> DepositResult:
        digest = hashlib.sha256(f"{resident_ref}|{idempotency_key}".encode()).hexdigest()[:16]
        return DepositResult(f"mockpay-{digest}", "completed", amount_cents)
