"""What a farm offers, at what price, and how much of it may actually be sold.

Modelled on ``micyte/core/crypto/channel.py``: the platform declares the shape of the
thing and refuses without it; whoever runs the deployment supplies the parts that are not
the platform's to choose. There is no permissive mode, because the failure this exists to
prevent is a number that *looks* like availability.

Two ledgers, and the subtraction lives here
-------------------------------------------
``available_to_sell = on_hand - reserved`` — and the two sides are different kinds of fact
that must never be stored together:

* **on_hand** is the farm's own assertion about what it grew and holds. It lives in datum
  documents, changes at the speed of farm work, and is appended rather than retracted.
* **reserved** is an external claim on that stock. It is made by strangers, in sub-second
  time, without the operator present, and a failed payment must **vacate** it.

Putting a stranger's abandoned cart into a datum document would make MOS a record of
things the farm never asserted, and reservations expire while datum rows do not. So the
subtraction happens in :class:`AvailabilityQuote` and nowhere else.

No degraded answer
------------------
:func:`require_reservation_ledger` raises rather than assuming zero reservations, for the
same reason ``require_cipher`` raises rather than sending plaintext: a degraded mode would
look like the port working. Zero is the single most plausible wrong answer here — it is
true right up until the first order exists, and from then on it oversells.

The catalog is a still; availability is not
-------------------------------------------
An :class:`OfferingCatalog` is a snapshot: it changes when the operator edits prices, and
it is published as a still whose ``mss_hash`` lets a consumer decide *not* to refetch. An
:class:`AvailabilityQuote` is answered live, per request, and is deliberately not part of
that hash — publishing them together would make every sale a corpus event.

Deliberately NOT here: where offers are stored, how stock is computed, who the payment
provider is, or how anything is transported. Those are host concerns. This module owns the
question and the shape of the answer.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol, runtime_checkable

#: The longest description an offered item may carry. It is the TITLE babelette width the
#: record layer stores it in, checked here so an over-long description is refused by the
#: contract rather than silently truncated three layers down — two products whose
#: descriptions truncate to the same text are two products a consumer cannot tell apart.
DESCRIPTION_MAX = 64


def _as_text(value: object) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _required(value: object, *, field_name: str) -> str:
    token = _as_text(value)
    if not token:
        raise ValueError(f"{field_name} is required")
    return token


def _as_units(value: object, *, field_name: str) -> int:
    """A non-negative whole count of sellable units.

    ``None`` is refused rather than read as zero. "I could not derive this" and "there are
    none" are different facts, and a stock figure that conflates them sells goods that do
    not exist.
    """
    if value is None or isinstance(value, bool):
        raise ValueError(f"{field_name} must be a whole number of units")
    try:
        units = int(value)
    except (TypeError, ValueError):
        raise ValueError(f"{field_name} must be a whole number of units") from None
    if units < 0:
        raise ValueError(f"{field_name} must not be negative")
    return units


def _as_cents(value: object, *, field_name: str) -> int:
    """A whole number of cents.

    Refuses a float outright rather than rounding one. ``4.10`` is not exactly
    representable in binary, and the moment a price is allowed to arrive as one, the
    difference between what the farm typed and what a buyer is charged becomes a rounding
    mode nobody chose. Callers convert text to cents with
    ``core.datum_ops.fiat_datum.parse_cents``, which refuses the same cases for the same
    reason.
    """
    if value is None or isinstance(value, (bool, float)):
        raise OfferingError(f"{field_name} must be a whole number of cents")
    try:
        cents = int(value)
    except (TypeError, ValueError):
        raise OfferingError(f"{field_name} must be a whole number of cents") from None
    if cents <= 0:
        raise OfferingError(f"{field_name} must be greater than zero")
    return cents


class OfferingError(ValueError):
    """An offering is malformed."""


class AvailabilityUnavailable(RuntimeError):
    """Availability cannot be reported, so it is not reported.

    Raised instead of returning a quote whenever an input is missing — no reservation
    ledger installed, or an on-hand figure that could not be derived. The caller shows the
    reason; it does not substitute a number.
    """


@dataclass(frozen=True)
class OfferedItem:
    """One thing a farm is offering, described completely enough to be sold.

    ``price_cents`` and ``unit`` are both required, and they are required *together*:
    "$4.00" is not an offer and neither is "per bunch". A price whose unit is implied is a
    price two readers will read differently.

    **The price is an integer count of cents, not a rendered string.** A port that hands a
    storefront ``"$4.00"`` has made the storefront parse money out of text, which is the
    same defect as storing it that way — and every provider this port will feed (PayPal,
    Zettle) takes an amount and a currency, never a rendering. The datum layer agrees: a
    price row carries this exact integer as its magnitude against the fiat babelette.

    ``product_node`` is the lcl product leaf. It is the item's identity — one product has
    one live offer — which is why nothing here carries an offer id: re-pricing is an edit
    of this item, not a second one.
    """

    product_node: str
    name: str
    price_cents: int
    unit: str
    description: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "price_cents", _as_cents(self.price_cents, field_name="offered_item.price_cents")
        )
        for field_name in ("product_node", "name", "unit"):
            object.__setattr__(
                self,
                field_name,
                _required(getattr(self, field_name), field_name=f"offered_item.{field_name}"),
            )
        description = _as_text(self.description)
        if len(description) > DESCRIPTION_MAX:
            raise OfferingError(
                f"offered_item.description must be {DESCRIPTION_MAX} characters or fewer"
            )
        object.__setattr__(self, "description", description)

    def to_dict(self) -> dict[str, Any]:
        return {
            "product_node": self.product_node,
            "name": self.name,
            "price_cents": self.price_cents,
            "unit": self.unit,
            "description": self.description,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> OfferedItem:
        if not isinstance(payload, dict):
            raise OfferingError("an offered item is not an object")
        return cls(
            product_node=payload.get("product_node"),
            name=payload.get("name"),
            price_cents=payload.get("price_cents"),
            unit=payload.get("unit"),
            description=payload.get("description", ""),
        )


@dataclass(frozen=True)
class OfferingCatalog:
    """Everything one farm offers — the publishable snapshot.

    One product appears at most once. A duplicate is refused rather than resolved by
    picking the last, because the two entries disagree about the price and there is no
    reading of "the last one wins" that a consumer could verify.
    """

    sandbox_id: str
    items: tuple[OfferedItem, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "sandbox_id", _required(self.sandbox_id, field_name="offering_catalog.sandbox_id")
        )
        items = tuple(
            item if isinstance(item, OfferedItem) else OfferedItem.from_dict(item)
            for item in (self.items or ())
        )
        seen: set[str] = set()
        for item in items:
            if item.product_node in seen:
                raise OfferingError(
                    f"{item.product_node} is offered twice in {self.sandbox_id} — a product "
                    "has one live price, and two rows do not say which"
                )
            seen.add(item.product_node)
        object.__setattr__(self, "items", items)

    def item_for(self, product_node: str) -> OfferedItem | None:
        token = _as_text(product_node)
        return next((item for item in self.items if item.product_node == token), None)

    def to_dict(self) -> dict[str, Any]:
        return {
            "sandbox_id": self.sandbox_id,
            "items": [item.to_dict() for item in self.items],
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> OfferingCatalog:
        if not isinstance(payload, dict):
            raise OfferingError("an offering catalog is not an object")
        raw = payload.get("items") or []
        if not isinstance(raw, list):
            raise OfferingError("offering_catalog.items is not a list")
        return cls(sandbox_id=payload.get("sandbox_id"), items=tuple(raw))


@dataclass(frozen=True)
class AvailabilityRequest:
    """"How much of this may I sell right now?" — asked of one farm about one product."""

    sandbox_id: str
    product_node: str

    def __post_init__(self) -> None:
        for field_name in ("sandbox_id", "product_node"):
            object.__setattr__(
                self,
                field_name,
                _required(
                    getattr(self, field_name), field_name=f"availability_request.{field_name}"
                ),
            )


@dataclass(frozen=True)
class AvailabilityQuote:
    """The answer, with both ledgers shown and the subtraction done here.

    Both figures are required and neither defaults. A quote that could be constructed
    without stating where ``reserved`` came from is one that can be constructed by
    forgetting to ask — which is the same bug as guessing zero, arrived at more quietly.

    ``reservation_source`` names the ledger that supplied ``reserved`` so a wrong number is
    attributable. It is not decoration: with a POS and a website both reserving stock, the
    first question about a bad figure is which writer produced it.
    """

    product_node: str
    on_hand: int
    reserved: int
    reservation_source: str

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "product_node",
            _required(self.product_node, field_name="availability_quote.product_node"),
        )
        object.__setattr__(
            self, "on_hand", _as_units(self.on_hand, field_name="availability_quote.on_hand")
        )
        object.__setattr__(
            self, "reserved", _as_units(self.reserved, field_name="availability_quote.reserved")
        )
        object.__setattr__(
            self,
            "reservation_source",
            _required(
                self.reservation_source, field_name="availability_quote.reservation_source"
            ),
        )

    @property
    def available_to_sell(self) -> int:
        """``on_hand - reserved``, floored at zero.

        The floor is a selling decision, not an accounting one: you cannot sell a negative
        head of lettuce. The accounting fact that produced it is not thrown away — see
        :attr:`oversold`, which stays true while this reads 0.
        """
        return max(0, self.on_hand - self.reserved)

    @property
    def oversold(self) -> bool:
        """More is claimed than is held. Surfaced, never smoothed over.

        This is the state two writers to one stock produce (a market sale and a website
        order for the same lettuce), and it is exactly the state a clamped number would
        hide.
        """
        return self.reserved > self.on_hand

    def to_dict(self) -> dict[str, Any]:
        return {
            "product_node": self.product_node,
            "on_hand": self.on_hand,
            "reserved": self.reserved,
            "reservation_source": self.reservation_source,
            "available_to_sell": self.available_to_sell,
            "oversold": self.oversold,
        }


@runtime_checkable
class ReservationLedger(Protocol):
    """External claims on stock — the right-hand ledger, supplied by the deployment.

    Implemented in Phase 6 by the ``order_intake`` journal (an append-only instance file
    with dedup by provider id, never MOS). Declared here so the offering port can state
    what it needs without depending on how orders arrive.
    """

    @property
    def source_id(self) -> str:
        """Which ledger this is, for attribution on the quote."""

    def reserved_units(self, sandbox_id: str, product_node: str) -> int:
        """Units of ``product_node`` currently claimed and not yet vacated."""


def require_reservation_ledger(ledger: ReservationLedger | None) -> ReservationLedger:
    """Return ``ledger``, or refuse to quote availability at all.

    The ``require_cipher`` discipline. Without a ledger the only numbers on hand are
    ``on_hand`` and an assumption, and an assumption here is specifically the assumption
    that nobody has ordered anything — true exactly until the moment it matters most.

    A caller that wants to show stock anyway should show **on-hand**, labelled as on-hand.
    That is a datum fact and it is honest; what is not available is *availability*.
    """
    if ledger is None:
        raise AvailabilityUnavailable(
            "no reservation ledger is installed, so availability cannot be reported — "
            "on-hand is known, but what has been claimed against it is not"
        )
    return ledger


def quote_availability(
    *,
    product_node: str,
    on_hand: int | None,
    ledger: ReservationLedger | None,
    sandbox_id: str,
) -> AvailabilityQuote:
    """The one place a quote is built, so the refusals cannot be skipped one call site at a time.

    ``on_hand=None`` means the farm's own stock figure could not be derived — an unknown
    unit, a batch with no propagule density. That is refused too: a product whose stock is
    unknown is not one whose availability can be reported.
    """
    checked = require_reservation_ledger(ledger)
    if on_hand is None:
        raise AvailabilityUnavailable(
            f"on-hand for {product_node} could not be derived from the farm's own records, "
            "so there is nothing to subtract reservations from"
        )
    return AvailabilityQuote(
        product_node=product_node,
        on_hand=on_hand,
        reserved=checked.reserved_units(sandbox_id, product_node),
        reservation_source=checked.source_id,
    )


@runtime_checkable
class CommerceOfferingPort(Protocol):
    """The outbound seam: what a website, a POS or a payment provider may ask a farm.

    Outbound only. Nothing here writes, and nothing here accepts an order — an order is
    the inbound direction and it enters through ``order_intake``'s journal, never through
    this port and never through a datum write from the web.
    """

    def read_offering_catalog(self, sandbox_id: str) -> OfferingCatalog:
        """What is for sale, described how, at what price."""

    def quote_availability(self, request: AvailabilityRequest) -> AvailabilityQuote:
        """How much may be sold right now. Raises :class:`AvailabilityUnavailable`."""


__all__ = [
    "DESCRIPTION_MAX",
    "AvailabilityQuote",
    "AvailabilityRequest",
    "AvailabilityUnavailable",
    "CommerceOfferingPort",
    "OfferedItem",
    "OfferingCatalog",
    "OfferingError",
    "ReservationLedger",
    "quote_availability",
    "require_reservation_ledger",
]
