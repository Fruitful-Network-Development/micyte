"""The commerce_offering port: what it refuses, and where the subtraction lives.

Three rules are worth a test each, because each has an obvious wrong implementation that
would pass a casual reading:

1. **A price without a unit is not an offer**, and neither is a unit without a price. The
   wrong implementation accepts either and lets a storefront guess.
2. **`available_to_sell = on_hand - reserved` is the PORT's arithmetic.** The wrong
   implementation lets a datum document hold the answer, at which point a stranger's
   abandoned cart is a thing the farm asserted.
3. **No reservation ledger means no availability figure.** The wrong implementation
   defaults `reserved` to zero, which is right until the first order exists and oversells
   from then on — the single most plausible bug in this design.
"""

from __future__ import annotations

import unittest

from micyte.ports.commerce_offering import (
    DESCRIPTION_MAX,
    AvailabilityQuote,
    AvailabilityRequest,
    AvailabilityUnavailable,
    CommerceOfferingPort,
    OfferedItem,
    OfferingCatalog,
    OfferingError,
    quote_availability,
    require_reservation_ledger,
)


class _Ledger:
    """A stand-in for Phase 6's reservation journal."""

    source_id = "test-journal"

    def __init__(self, reserved: int = 0) -> None:
        self._reserved = reserved

    def reserved_units(self, sandbox_id: str, product_node: str) -> int:
        return self._reserved


class OfferedItemTests(unittest.TestCase):
    def _item(self, **kw) -> OfferedItem:
        params = {"product_node": "1-1-5-1", "name": "Buttercrunch lettuce",
                  "price_cents": 400, "unit": "head"}
        params.update(kw)
        return OfferedItem(**params)

    def test_a_price_is_whole_cents_and_a_float_is_refused_outright(self) -> None:
        # 4.10 is not exactly representable in binary. The moment a price is allowed to
        # arrive as a float, the gap between what the farm typed and what a buyer is
        # charged becomes a rounding mode nobody chose.
        for bad in (4.0, 4.10, "4.10", None, True, "abc"):
            with self.subTest(bad=bad):
                with self.assertRaises(ValueError):
                    self._item(price_cents=bad)

    def test_a_free_or_negative_offer_is_not_an_offer(self) -> None:
        for bad in (0, -400):
            with self.subTest(bad=bad):
                with self.assertRaises(ValueError):
                    self._item(price_cents=bad)

    def test_an_integer_string_is_accepted_because_a_datum_magnitude_is_text(self) -> None:
        # The magnitude arrives off a datum row, where every value is a string.
        self.assertEqual(self._item(price_cents="400").price_cents, 400)

    def test_a_priced_item_needs_a_unit_and_a_unit_needs_a_price(self) -> None:
        # Both directions, because accepting either half is the same defect: a price whose
        # unit is implied is one two readers read differently.
        with self.assertRaises(ValueError):
            self._item(price_cents=None)
        with self.assertRaises(ValueError):
            self._item(unit="")

    def test_an_item_needs_the_product_it_names(self) -> None:
        with self.assertRaises(ValueError):
            self._item(product_node="")

    def test_an_over_long_description_is_refused_not_truncated(self) -> None:
        # Same rule as the sale's reference: a silently shortened field is one two records
        # can collide in, and the collision is invisible.
        with self.assertRaises(OfferingError):
            self._item(description="x" * (DESCRIPTION_MAX + 1))
        self.assertEqual(len(self._item(description="x" * DESCRIPTION_MAX).description),
                         DESCRIPTION_MAX)

    def test_round_trip(self) -> None:
        item = self._item(description="crisp, sweet")
        self.assertEqual(OfferedItem.from_dict(item.to_dict()), item)


class OfferingCatalogTests(unittest.TestCase):
    def test_one_product_cannot_be_offered_twice(self) -> None:
        # Refused rather than resolved by taking the last: the two entries disagree about
        # the price, and no reading of "the last one wins" is one a consumer can verify.
        item = OfferedItem(product_node="1-1-5-1", name="lettuce", price_cents=400, unit="head")
        other = OfferedItem(product_node="1-1-5-1", name="lettuce", price_cents=500, unit="head")
        with self.assertRaises(OfferingError):
            OfferingCatalog(sandbox_id="farm", items=(item, other))

    def test_a_catalog_names_the_farm_it_belongs_to(self) -> None:
        with self.assertRaises(ValueError):
            OfferingCatalog(sandbox_id="", items=())

    def test_round_trip(self) -> None:
        catalog = OfferingCatalog(
            sandbox_id="farm",
            items=(OfferedItem(product_node="1-1-5-1", name="lettuce", price_cents=400, unit="head"),),
        )
        self.assertEqual(OfferingCatalog.from_dict(catalog.to_dict()), catalog)
        self.assertIsNotNone(catalog.item_for("1-1-5-1"))
        self.assertIsNone(catalog.item_for("1-1-5-2"))


class AvailabilityTests(unittest.TestCase):
    def test_the_subtraction_is_the_ports(self) -> None:
        quote = AvailabilityQuote(
            product_node="1-1-5-1", on_hand=10, reserved=3, reservation_source="journal")
        self.assertEqual(quote.available_to_sell, 7)
        self.assertFalse(quote.oversold)

    def test_oversold_is_surfaced_while_the_sellable_figure_floors_at_zero(self) -> None:
        # Two writers to one stock (a market sale and a website order for the same lettuce)
        # produce exactly this state. You cannot sell -2 heads, but the accounting fact must
        # not be smoothed away by the clamp that says so.
        quote = AvailabilityQuote(
            product_node="1-1-5-1", on_hand=3, reserved=5, reservation_source="journal")
        self.assertEqual(quote.available_to_sell, 0)
        self.assertTrue(quote.oversold)

    def test_a_quote_cannot_be_built_without_saying_where_reserved_came_from(self) -> None:
        with self.assertRaises(ValueError):
            AvailabilityQuote(
                product_node="1-1-5-1", on_hand=1, reserved=0, reservation_source="")

    def test_none_is_not_zero(self) -> None:
        # "I could not derive this" and "there are none" are different facts, and a stock
        # figure that conflates them sells goods that do not exist.
        with self.assertRaises(ValueError):
            AvailabilityQuote(
                product_node="1-1-5-1", on_hand=None, reserved=0, reservation_source="j")

    def test_no_ledger_refuses_rather_than_assuming_nobody_ordered(self) -> None:
        with self.assertRaises(AvailabilityUnavailable):
            require_reservation_ledger(None)
        with self.assertRaises(AvailabilityUnavailable):
            quote_availability(product_node="1-1-5-1", on_hand=10, ledger=None, sandbox_id="farm")

    def test_an_underivable_on_hand_refuses_too(self) -> None:
        with self.assertRaises(AvailabilityUnavailable):
            quote_availability(
                product_node="1-1-5-1", on_hand=None, ledger=_Ledger(0), sandbox_id="farm")

    def test_with_a_ledger_the_quote_is_attributable(self) -> None:
        quote = quote_availability(
            product_node="1-1-5-1", on_hand=10, ledger=_Ledger(4), sandbox_id="farm")
        self.assertEqual(quote.available_to_sell, 6)
        self.assertEqual(quote.reservation_source, "test-journal")

    def test_a_request_names_both_a_farm_and_a_product(self) -> None:
        with self.assertRaises(ValueError):
            AvailabilityRequest(sandbox_id="farm", product_node="")


class PortShapeTests(unittest.TestCase):
    def test_the_port_stays_implementation_free(self) -> None:
        # A port owns inward-facing contracts only (micyte/ports/module_contract.md). If a
        # provider SDK or a tool ever lands in here, this fails.
        import micyte.ports.commerce_offering.contracts as module

        source = open(module.__file__, encoding="utf-8").read()
        for forbidden in ("micyte.tools", "micyte.adapters", "requests", "paypal", "sqlite3"):
            self.assertNotIn(forbidden, source, f"{forbidden} does not belong in a port")

    def test_a_conforming_object_satisfies_the_protocol(self) -> None:
        class _Port:
            def read_offering_catalog(self, sandbox_id: str) -> OfferingCatalog:
                return OfferingCatalog(sandbox_id=sandbox_id, items=())

            def quote_availability(self, request: AvailabilityRequest) -> AvailabilityQuote:
                return AvailabilityQuote(
                    product_node=request.product_node, on_hand=0, reserved=0,
                    reservation_source="none")

        self.assertIsInstance(_Port(), CommerceOfferingPort)


if __name__ == "__main__":
    unittest.main()
