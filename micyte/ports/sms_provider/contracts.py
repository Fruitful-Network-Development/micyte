"""SMS provider port — one text message, sent on the instance's behalf. CONTRACT ONLY.

The Oveure refinement (TASK-2026-08-14-002): declared-available and unused by the
operator's explicit wish, exactly as ``email_provider`` — see that module's header for
the whole posture (no peripheral, no route, no HTTP client; external_call_policy
governs whatever arrives later). The SERVICE token is the provider (``aws_sns`` — the
operator named AWS text messages); one operation, the withholdable grain.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable

#: The one operation an SMS grant is written against.
OPERATION_MESSAGE_SEND = "message.send"

#: The provider this deployment would bind — AWS SNS is the named text-message rail.
SERVICE_AWS_SNS = "aws_sns"


class SmsProviderError(ValueError):
    """A message is malformed before any provider is asked."""


@dataclass(frozen=True)
class SmsMessage:
    """What a send WOULD carry: an E.164-shaped number and a body, both required."""

    to: str
    body: str

    def __post_init__(self) -> None:
        for name in ("to", "body"):
            if not str(getattr(self, name) or "").strip():
                raise SmsProviderError(f"sms_message.{name} is required")
        if not str(self.to).strip().startswith("+"):
            raise SmsProviderError(
                "sms_message.to must be E.164 (+<country><number>) — a bare local "
                "number is one two carriers dial differently")


@runtime_checkable
class SmsProviderPort(Protocol):
    """The seam a binding fills. ``provider_id`` is the service token a grant names."""

    @property
    def provider_id(self) -> str: ...

    def send_message(self, message: SmsMessage) -> str:
        """Send; return the provider's message id. authorize_external_call FIRST."""


__all__ = [
    "OPERATION_MESSAGE_SEND",
    "SERVICE_AWS_SNS",
    "SmsMessage",
    "SmsProviderError",
    "SmsProviderPort",
]
