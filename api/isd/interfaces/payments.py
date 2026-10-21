"""Payment boundary (invariant 10). Real processors plug in here later."""

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class DepositResult:
    external_id: str
    status: str  # completed | failed
    amount_cents: int


class PaymentProvider(Protocol):
    def create_deposit(
        self, resident_ref: str, amount_cents: int, payer_ref: str, idempotency_key: str
    ) -> DepositResult: ...
