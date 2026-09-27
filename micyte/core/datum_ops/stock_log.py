"""What came in and what went out — one log, and the balance derived from it.

TASK-2026-09-12-001 B3. Operator, 2026-09-12:

> a singular log datum doc would contain event entries of supply or output and denote a
> lcl_id to which it refers. The counts would be relative to the product profile defined
> whether it is to be understood by weight or count etc. and the entries would include a
> msn_id for who the supplier was or who the buyer was

So: ONE document per instance, one row per event::

    stock_entry  =  lcl_id , lcl_id , nominal , msn_id , utc , title?
                    ^the product
                             ^the KIND of event
                                      ^how many
                                                ^the supplier or the buyer
                                                         ^when
                                                               ^an optional note

**The count carries no unit.** What twelve of a thing is — twelve pounds, twelve each,
twelve bunches — is the product profile's ``nominal``, so a reader joins the two and
nobody stores the measure twice.

**The kind carries the direction, and the count is never negative.** A magnitude is a
string in a head and a leading minus is a shape nothing else in this corpus writes, so
direction is a fact about the EVENT: `supply` adds, `output` and `spoilage` subtract. The
table lives here, once, and both the writer and the reader import it — so a row whose
direction nobody can decide is refused at the door rather than discovered in a total.

**The kind is a node, not a word.** It names a child of the tree's ``stock_events``
vocabulary, which the convention seeds, so an instance can see its own vocabulary in the
editor and the log cites a thing rather than repeating a string.

Pure: the caller passes the document and the registry it already holds.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from . import archetype_shape as ash
from .datum_resolve import as_text, decode_label, iter_marker_pairs

#: The archetype every row is, and the document that holds them.
ENTRY_ARCHETYPE = "stock_entry"
STOCK_DOCUMENT = "stock_log"
#: The class vocabulary the kinds are children of.
EVENT_KIND = "stock_events"

#: Which way each kind moves the balance. A kind absent from this table cannot be totalled
#: and is refused when written, so a log never holds a row whose direction is unknowable.
#:
#: `output` and `spoilage` are both subtractions and are still two kinds, because "sold"
#: and "lost" are different facts about the same missing stock and an operator asking why
#: the number fell deserves the answer.
DIRECTIONS: dict[str, int] = {
    "supply": +1,
    "return": +1,
    "adjustment_up": +1,
    "output": -1,
    "spoilage": -1,
    "adjustment_down": -1,
}
#: The vocabulary the convention seeds, in the order it seeds it.
EVENT_KINDS: tuple[str, ...] = tuple(DIRECTIONS)


@dataclass(frozen=True)
class StockEvent:
    """One movement."""

    address: str
    product: str
    kind: str
    count: int
    party: str = ""
    day: str = ""
    note: str = ""
    #: The kind's label off the tree when the caller supplied labels, else its node.
    kind_name: str = ""

    @property
    def signed(self) -> int | None:
        """``+count`` or ``-count``, or ``None`` when this kind has no declared direction."""
        way = DIRECTIONS.get(self.kind_name or "")
        return None if way is None else way * self.count

    def to_dict(self) -> dict[str, Any]:
        return {"address": self.address, "product": self.product, "kind": self.kind,
                "kind_name": self.kind_name, "count": self.count, "party": self.party,
                "day": self.day, "note": self.note, "signed": self.signed}


@dataclass(frozen=True)
class StockLog:
    """Every movement the document holds, newest last, and the balances derived."""

    events: tuple[StockEvent, ...] = ()
    unmatched: list[str] = field(default_factory=list)

    def balances(self) -> dict[str, int | None]:
        """``{product node: on hand}``, or ``None`` for a product whose log holds a kind
        with no declared direction.

        ``None`` is not zero. Reporting an underivable figure as zero understates stock
        exactly as confidently as reporting it as available would overstate it — the rule
        `_offering.on_hand_units` already states for a batch bought by mass.
        """
        out: dict[str, int | None] = {}
        for event in self.events:
            if not event.product:
                continue
            signed = event.signed
            if signed is None:
                out[event.product] = None
                continue
            if event.product in out and out[event.product] is None:
                continue
            out[event.product] = int(out.get(event.product) or 0) + signed
        return out

    def for_product(self, product: str) -> tuple[StockEvent, ...]:
        return tuple(e for e in self.events if e.product == as_text(product))

    def to_dict(self) -> dict[str, Any]:
        return {"events": [e.to_dict() for e in self.events],
                "balances": self.balances(), "unmatched": list(self.unmatched)}


def _head(row: Any) -> list[Any]:
    raw = getattr(row, "raw", None)
    if isinstance(raw, list) and raw and isinstance(raw[0], list):
        return list(raw[0])
    return []


def _cells(head: list[Any], *, namespace: str) -> list[tuple[str, str]]:
    return [(ash._field_name(as_text(marker), sandbox=namespace), as_text(magnitude))
            for marker, magnitude in iter_marker_pairs(head)]


def _nth(cells: list[tuple[str, str]], name: str, *, skip: int = 0) -> str:
    seen = 0
    for field_name, value in cells:
        if field_name == name:
            if seen == skip:
                return value
            seen += 1
    return ""


def read_log(document: Any, *, registry: Any, namespace: str,
             labels: dict[str, str] | None = None) -> StockLog:
    """Fold every row and answer the log, in the order the rows were written."""
    events: list[StockEvent] = []
    unmatched: list[str] = []
    for row in getattr(document, "rows", ()) or ():
        address = as_text(getattr(row, "datum_address", ""))
        head = _head(row)
        if len(head) < 3:
            continue
        matches = tuple(registry.match_row(ash.row_shape(row.raw, sandbox=namespace))) \
            if registry is not None else ()
        if ENTRY_ARCHETYPE not in matches:
            unmatched.append(address)
            continue
        cells = _cells(head, namespace=namespace)
        # Two lcl cells, read POSITIONALLY: the product, then the kind — the reading
        # `local_domain_log` and `project_artifact` already established.
        product, kind = _nth(cells, "lcl_id"), _nth(cells, "lcl_id", skip=1)
        count = _nth(cells, "nominal")
        events.append(StockEvent(
            address=address, product=product, kind=kind,
            count=int(count) if count.isdigit() else 0,
            party=_nth(cells, "msn_id"), day=_nth(cells, "utc"),
            note=decode_label(_nth(cells, "title")),
            kind_name=(labels or {}).get(kind, "")))
    return StockLog(events=tuple(events), unmatched=unmatched)


__all__ = [
    "DIRECTIONS",
    "ENTRY_ARCHETYPE",
    "EVENT_KIND",
    "EVENT_KINDS",
    "STOCK_DOCUMENT",
    "StockEvent",
    "StockLog",
    "read_log",
]
