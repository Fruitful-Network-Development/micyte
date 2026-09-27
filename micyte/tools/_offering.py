"""The farm offering read model — what is for sale, and what is actually on hand.

One read model behind the writable table, the record viewer, the synopsis and the port
projection, for the same reason ``_consumption`` is one read model behind three inventory
surfaces: a catalog and a total that disagree are worse than either alone.

The two halves are deliberately not symmetrical, and that asymmetry is the whole point of
the commerce port:

* **the catalog** — price, unit, description. The farm's own assertion, changing at the
  speed of a catalog edit, and publishable as a still whose hash lets a consumer decide
  not to refetch.
* **availability** — how much may be sold *right now*. Answered live, never published
  inside the still, and **not answerable at all** until a reservation ledger exists.

:func:`on_hand_units` reports the left-hand ledger only. It is a datum fact and it is
honest. Turning it into an availability figure requires subtracting external claims, and
:func:`availability` refuses to do that without a ledger to subtract — see
``micyte/ports/commerce_offering``.
"""

from __future__ import annotations

from typing import Any

from micyte.core.datum_ops.datum_resolve import cached_index, decode_label, marker_buckets
from micyte.core.datum_ops.fiat_datum import FiatChainError, find_fiat_chain, format_cents
from micyte.ports.commerce_offering import (
    AvailabilityQuote,
    OfferedItem,
    OfferingCatalog,
    ReservationLedger,
)
from micyte.ports.commerce_offering import quote_availability as _quote

from ._archetype import find_anchor, find_local_domain, find_named_document
from ._consumption import available_batches
from ._shared.utilities import as_text as _as_text
from ._shared.utilities import row_head as _row_head
from ._shared.utilities import row_tail_label as _row_tail_label

OFFERING_PREFIX = "4-9-"
_RF_LCL = "rf.3-1-5"
_RF_NOMINAL = "rf.3-1-7"
_RF_TITLE = "rf.3-1-2"


def _cents_of(value: Any) -> int | None:
    """A price magnitude as whole cents, or ``None`` if the row does not carry one.

    ``None`` rather than 0, for the same reason on-hand reports ``None``: an unpriced row
    and a free one are different claims, and only one of them may be sold.
    """
    token = _as_text(value)
    if not token:
        return None
    try:
        format_cents(token)
    except FiatChainError:
        return None
    return int(token)


def on_hand_units(docs: list[Any], sandbox: str,
                  stock: dict[str, int | None] | None = None) -> dict[str, int | None]:
    """product node -> units the instance holds, or ``None`` when that cannot be derived.

    ``stock`` is the STOCK LOG's balances where the caller has them
    (`stock_write_runtime.stock_balances`, TASK-2026-09-12-001 B3) — the general model,
    one row per movement, which a non-farm instance has and a farm may also keep. It wins
    for every product it names, because it is the instance's own assertion about what it
    holds; the batch derivation below answers for the products it does not, so a farm that
    has never opened a stock log reads exactly as it did before.

    The two are not summed. A batch consumed by a planting and a movement recorded against
    the same product would double-count, and there is no reading of "add them" that anyone
    could verify — so the more specific statement wins and the other fills the gaps.

    Summed over the sandbox's live supply batches — the same
    :func:`~._consumption.available_batches` read model the contract form draws its options
    from, so the number a storefront would quote and the number the operator plans against
    come from one place.

    ``None`` is not zero. A batch bought by mass with no propagule density on file has no
    derivable unit count, and reporting the products it contributes to as "0 on hand" would
    understate stock exactly as confidently as reporting them as available would overstate
    it. The caller is told it does not know.
    """
    totals: dict[str, int | None] = dict(stock or {})
    for batch in available_batches(docs, sandbox):
        if _as_text(batch.get("product_node")) in totals:
            continue                       # the log already said what this product holds
        node = _as_text(batch.get("product_node"))
        if not node:
            continue
        remaining = batch.get("remaining_units")
        if remaining is None:
            totals[node] = None
            continue
        if node in totals and totals[node] is None:
            continue
        totals[node] = int(totals.get(node) or 0) + int(remaining)
    return totals


def offering_rows(docs: list[Any], sandbox: str,
                  stock: dict[str, int | None] | None = None) -> list[dict[str, Any]]:
    """Every offer in ``sandbox``, with its product resolved and its on-hand figure attached.

    Ordered by the ``4-9-N`` ordinal — the order the operator listed things in. Unlike the
    sale table there is no newest-first reversal, because an offer is not an event: the
    catalog is a standing list, and a list that reshuffles when a price is edited is one
    the operator has to re-find their place in.
    """
    doc = find_named_document(docs, sandbox=sandbox, name="offering")
    lcl = cached_index(find_local_domain(docs, sandbox=sandbox))
    stock = on_hand_units(docs, sandbox, stock)
    # The price marker is this sandbox's own, found by the shape of its abstraction chain.
    # Looked for in the anchor first, then in the offering document's OWN `anchor_rows` —
    # which is how a published still works: it travels without the farm's anchor, carrying
    # instead the minimum closure that defines its markers. Without the fallback a catalog
    # would decode to prices nobody could read, which is the same defect as a catalog whose
    # products nobody could name (Phase 5), one level further down.
    #
    # A farm with no chain anywhere has no priced rows to read, so an absent one is not an
    # error here — it is an empty bucket, and the table shows no prices.
    chain = (find_fiat_chain(find_anchor(docs, sandbox=sandbox))
             or find_fiat_chain(getattr(doc, "anchor_rows", ())))
    price_marker = chain.marker if chain is not None else ""

    out: list[dict[str, Any]] = []
    for row in getattr(doc, "rows", ()) or ():
        addr = _as_text(row.datum_address)
        if not addr.startswith(OFFERING_PREFIX):
            continue
        buckets = marker_buckets(_row_head(row))
        refs = buckets.get(_RF_LCL, [])
        noms = [decode_label(n) for n in buckets.get(_RF_NOMINAL, [])]
        titles = [decode_label(t) for t in buckets.get(_RF_TITLE, [])]
        cents = buckets.get(price_marker, []) if price_marker else []
        price_cents = _cents_of(cents[0]) if cents else None
        offer = _as_text(refs[0]) if refs else ""
        product = _as_text(refs[1]) if len(refs) > 1 else ""
        on_hand = stock.get(product)
        out.append({
            "datum_address": addr,
            "offer": lcl.resolve(offer) or _row_tail_label(row) or offer,
            "offer_node": offer,
            "product": lcl.resolve(product) or product,
            "product_node": product,
            # The magnitude is the fact; the rendering is for the table. Both come from
            # one place so a cell and a published catalog cannot disagree about a price.
            "price_cents": price_cents,
            "price": "" if price_cents is None else format_cents(price_cents),
            "unit": noms[0] if noms else "",
            # The listing NAME is stored on the row, not resolved from the lcl, so a
            # catalog published on its own can still name what it is selling.
            "name": (titles[0] if titles else "") or lcl.resolve(product) or product,
            "description": titles[1] if len(titles) > 1 else "",
            "on_hand": on_hand,
            # What the table prints. "unknown" is a real answer here and reads as one; an
            # empty cell would read as zero.
            "on_hand_text": "unknown" if on_hand is None else str(on_hand),
        })
    out.sort(key=lambda x: int(x["datum_address"].split("-")[-1]))
    return out


def offering_catalog(docs: list[Any], sandbox: str) -> OfferingCatalog:
    """The offering as the port's own object — the thing a storefront consumes.

    Rows the port would refuse (no price, no unit, a product that resolves to nothing) are
    dropped rather than repaired. A catalog is published; a half-formed entry in one is a
    price a stranger acts on.
    """
    items: list[OfferedItem] = []
    for row in offering_rows(docs, sandbox):
        try:
            items.append(OfferedItem(
                product_node=row["product_node"],
                name=row["name"],
                price_cents=row["price_cents"],
                unit=row["unit"],
                description=row["description"],
            ))
        except ValueError:
            continue
    return OfferingCatalog(sandbox_id=sandbox, items=tuple(items))


def availability(
    docs: list[Any],
    sandbox: str,
    product_node: str,
    *,
    ledger: ReservationLedger | None,
    stock: dict[str, int | None] | None = None,
) -> AvailabilityQuote:
    """``on_hand - reserved`` for one product, or raise ``AvailabilityUnavailable``.

    The subtraction is the port's, not this module's — everything here does is supply the
    left-hand number and hand over. With ``ledger=None`` (Phase 5: there is no reservation
    journal yet) this raises, and the surface prints the reason instead of a figure.
    """
    return _quote(
        product_node=_as_text(product_node),
        on_hand=on_hand_units(docs, sandbox, stock).get(_as_text(product_node)),
        ledger=ledger,
        sandbox_id=sandbox,
    )


__all__ = [
    "OFFERING_PREFIX",
    "availability",
    "offering_catalog",
    "offering_rows",
    "on_hand_units",
]
