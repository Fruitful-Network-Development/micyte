"""Payment instrument port — FND charging a CLIENT's card on file. CONTRACT ONLY.

The opposite direction from every payment path this stack held before 2026-09-16.
``fnd_routes/paypal.py`` and PIM's Payment tab are a client's own merchant account taking
money on the client's own site; ``commerce_offering`` is a farm publishing what it sells.
This is the hosting relationship's other side: what the client pays FND, taken from an
instrument the client put on file when they signed up.

No peripheral, no route, no HTTP client, no fill. Declared before anything fills it, the
way ``sms_provider`` was, so the seam is on the Ports surface and every surface that
depends on it renders "not connected yet" honestly rather than arriving with its first
use. A fill is the operator's later choice on Ports — PayPal vaulting, Stripe
SetupIntents, anything whose card fields the processor hosts — and until one is bound
nothing on this build can move money.

## The line this contract draws in the TYPE, not in a comment

No operation here takes a card number. :meth:`PaymentInstrumentPort.vault` takes a
``setup_token`` — the one-time token the processor's hosted fields hand the BROWSER after
the card was entered into fields FND never served — and returns a :class:`VaultedInstrument`
whose every string field is passed through :func:`refuse_pan`. A fill that wanted a PAN
would need a method this Protocol does not have, and a fill that returned one as its
"reference" is refused at construction. That is the SAQ-A line: cardholder data is not
merely un-stored, it is un-receivable through this seam.

## Four operations, at the grain worth withholding

* :data:`OPERATION_INSTRUMENT_VAULT` — turn a setup token into an instrument on file.
  The act a signup performs once.
* :data:`OPERATION_INSTRUMENT_DESCRIBE` — read back brand, last four, expiry for a
  reference already held. Discloses only what the client already knows about their own
  card; the one an operator would grant to let a surface DRAW.
* :data:`OPERATION_INSTRUMENT_CHARGE` — a merchant-initiated charge against the
  reference. The operation that moves money and the one to withhold from everything but
  the billing routine.
* :data:`OPERATION_INSTRUMENT_DETACH` — release the reference at the processor. Its own
  operation because it is the client's right to exercise and the one that makes CHARGE
  impossible afterwards.

Write the sales row BEFORE asking for money (the archived 2026-08-24 design): a charge
with no record is the failure mode, so :class:`ChargeRequest.reference` carries the row
the charge is for and a fill echoes it in the receipt.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from micyte.core.payment_instrument import refuse_pan

OPERATION_INSTRUMENT_VAULT = "instrument.vault"
OPERATION_INSTRUMENT_DESCRIBE = "instrument.describe"
OPERATION_INSTRUMENT_CHARGE = "instrument.charge"
OPERATION_INSTRUMENT_DETACH = "instrument.detach"

#: A receipt's ``status`` vocabulary. ``declined`` is a fact the RECORD wants to know
#: (it moves an instrument to ``failing``); ``pending`` is a processor still deciding.
STATUS_CAPTURED = "captured"
STATUS_DECLINED = "declined"
STATUS_PENDING = "pending"
STATUSES: tuple[str, ...] = (STATUS_CAPTURED, STATUS_DECLINED, STATUS_PENDING)


class PaymentInstrumentError(ValueError):
    """A request is malformed before any processor is asked."""


class PaymentInstrumentUnavailable(PaymentInstrumentError):
    """No fill is bound for this instance, so the operation cannot be performed.

    The resting state of this port on every instance today. Raised by the HOST's
    resolver, never by a fill; a surface catching it says "not connected yet".
    """


@dataclass(frozen=True)
class VaultedInstrument:
    """What a processor holds for us, as we may know it: a reference and a recogniser.

    ``vault_ref`` is the processor's opaque token and the only thing a charge needs. It is
    the INSTRUMENT and belongs in a 0600 file; the four recogniser fields are the RECORD
    and belong in the datum row. Both halves are refused if any of them is shaped like a
    card number — a fill cannot smuggle a PAN through as its "reference".
    """

    vault_ref: str
    processor: str
    environment: str
    brand: str = ""
    last4: str = ""
    exp_month: int = 0
    exp_year: int = 0

    def __post_init__(self) -> None:
        for name in ("vault_ref", "processor", "environment"):
            value = refuse_pan(getattr(self, name), field=f"vaulted_instrument.{name}")
            if not value:
                raise PaymentInstrumentError(f"vaulted_instrument.{name} is required")
        refuse_pan(self.brand, field="vaulted_instrument.brand")
        if self.last4 and not (len(self.last4) == 4 and self.last4.isdigit()):
            raise PaymentInstrumentError("vaulted_instrument.last4 must be four digits")


@dataclass(frozen=True)
class ChargeRequest:
    """One merchant-initiated charge: how much, against which reference, for which row."""

    vault_ref: str
    amount_cents: int
    reference: str
    currency: str = "USD"
    description: str = ""

    def __post_init__(self) -> None:
        if not refuse_pan(self.vault_ref, field="charge_request.vault_ref"):
            raise PaymentInstrumentError("charge_request.vault_ref is required")
        if not isinstance(self.amount_cents, int) or self.amount_cents <= 0:
            raise PaymentInstrumentError("charge_request.amount_cents must be a positive whole number")
        if not str(self.reference or "").strip():
            raise PaymentInstrumentError(
                "charge_request.reference is required — write the sales row first and "
                "name it; a charge with no record is the failure mode")
        if not str(self.currency or "").strip():
            raise PaymentInstrumentError("charge_request.currency is required")


@dataclass(frozen=True)
class ChargeReceipt:
    """What the processor said. ``reference`` echoes the request's, so a receipt can be
    filed against the row it paid."""

    processor_ref: str
    reference: str
    amount_cents: int
    currency: str
    status: str
    reason: str = ""

    def __post_init__(self) -> None:
        if self.status not in STATUSES:
            raise PaymentInstrumentError(
                f"charge_receipt.status {self.status!r} is not one of {STATUSES}")


@runtime_checkable
class PaymentInstrumentPort(Protocol):
    """The seam a binding fills. ``processor_id`` is the service token a grant names."""

    @property
    def processor_id(self) -> str: ...

    @property
    def environment(self) -> str: ...

    def vault(self, *, setup_token: str) -> VaultedInstrument:
        """Exchange the hosted fields' one-time token for an instrument on file.
        authorize_external_call FIRST. ``setup_token`` is never a card number."""

    def describe(self, *, vault_ref: str) -> VaultedInstrument:
        """Brand, last four and expiry for a reference already held."""

    def charge(self, request: ChargeRequest) -> ChargeReceipt:
        """A merchant-initiated charge. authorize_external_call FIRST."""

    def detach(self, *, vault_ref: str) -> None:
        """Release the reference at the processor; a later charge against it must fail."""


__all__ = [
    "OPERATION_INSTRUMENT_CHARGE",
    "OPERATION_INSTRUMENT_DESCRIBE",
    "OPERATION_INSTRUMENT_DETACH",
    "OPERATION_INSTRUMENT_VAULT",
    "STATUSES",
    "STATUS_CAPTURED",
    "STATUS_DECLINED",
    "STATUS_PENDING",
    "ChargeReceipt",
    "ChargeRequest",
    "PaymentInstrumentError",
    "PaymentInstrumentPort",
    "PaymentInstrumentUnavailable",
    "VaultedInstrument",
]
