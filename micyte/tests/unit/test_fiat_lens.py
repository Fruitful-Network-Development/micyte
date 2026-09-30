"""The currency lens: a price magnitude made legible without being made editable-by-accident.

The raw datum workbench shows a row's primary value. For a price that value is ``450``,
sitting in a column whose neighbours are bit strings and node addresses, with nothing to
say it is money. This lens is the overlay that says so — and, unlike ``BinaryTextLens``, it
is symmetric: what an operator types goes back as cents.
"""

from __future__ import annotations

import unittest

from micyte.domains.datum_recognition.service import _family_contract
from micyte.state_machine.lens import FiatCentsLens, resolve_datum_lens


class FiatCentsLensTests(unittest.TestCase):
    def setUp(self) -> None:
        self.lens = FiatCentsLens()

    def test_a_magnitude_displays_as_currency(self) -> None:
        for canonical, display in (("450", "$4.50"), ("1", "$0.01"), ("0", "$0.00"),
                                   ("125000", "$1250.00"), ("-450", "-$4.50")):
            with self.subTest(canonical=canonical):
                self.assertEqual(self.lens.decode(canonical), display)

    def test_what_the_operator_types_goes_back_as_cents(self) -> None:
        for display, canonical in (("$4.50", "450"), ("4.5", "450"), ("$1,250.00", "125000")):
            with self.subTest(display=display):
                self.assertEqual(self.lens.encode(display), canonical)

    def test_decode_and_encode_round_trip(self) -> None:
        for display in ("$0.01", "$4.50", "$19.99", "$1250.00"):
            with self.subTest(display=display):
                self.assertEqual(self.lens.decode(self.lens.encode(display)), display)

    def test_a_value_it_cannot_read_is_shown_unchanged(self) -> None:
        # The cell states the row's problem. Rendering "$0.00" for an unreadable magnitude
        # would report a free product, which is a price somebody could act on.
        for canonical in ("not-a-number", "0101010101", "4.5"):
            with self.subTest(canonical=canonical):
                self.assertEqual(self.lens.decode(canonical), canonical)
        self.assertEqual(self.lens.decode(""), "")

    def test_validation_names_the_two_ways_a_price_is_wrong(self) -> None:
        self.assertEqual(self.lens.validate_display(""), ("price_required",))
        self.assertEqual(self.lens.validate_display("free"), ("price_invalid",))
        self.assertEqual(self.lens.validate_display("$4.505"), ("price_invalid",))
        self.assertEqual(self.lens.validate_display("$4.50"), ())

    def test_it_is_stateless(self) -> None:
        a, b = FiatCentsLens(), FiatCentsLens()
        self.assertEqual(a.decode("450"), b.decode("450"))
        self.assertEqual(a.lens_id, "fiat_cents")


class FiatLensBindingTests(unittest.TestCase):
    def test_the_fiat_babelette_label_recognizes_as_a_price(self) -> None:
        self.assertEqual(
            _family_contract("fiat-babelette"), ("fiat_babelette", "fiat_cents", "fiat_babelette"))

    def test_the_gold_rudi_label_is_NOT_a_price(self) -> None:
        # `fiat-currency-unit` is the rudi two layers below — a substance, not an amount.
        # Binding the currency lens to it would render a rudi's `0-0-0` as "$0.00".
        family, value_kind, _overlay = _family_contract("fiat-currency-unit")
        self.assertNotEqual(family, "fiat_babelette")
        self.assertNotEqual(value_kind, "fiat_cents")

    def test_the_registry_resolves_the_lens_three_ways(self) -> None:
        for kwargs in (
            {"recognized_family": "fiat_babelette"},
            {"primary_value_kind": "fiat_cents"},
            {"overlay_kind": "fiat_babelette"},
            {"flag_lens_id": "fiat_cents"},
        ):
            with self.subTest(kwargs=kwargs):
                self.assertEqual(resolve_datum_lens(**kwargs).lens_id, "fiat_cents")

    def test_turning_it_off_falls_back_to_the_passthrough(self) -> None:
        resolution = resolve_datum_lens(
            recognized_family="fiat_babelette", enabled_lens_ids=frozenset({"binary_text"}))
        self.assertEqual(resolution.lens_id, "identity")
        self.assertEqual(resolution.matched_on, "lens_disabled")

    def test_it_appears_in_the_management_catalog(self) -> None:
        from micyte.state_machine.lens import DEFAULT_DATUM_LENS_REGISTRY

        entry = next(
            e for e in DEFAULT_DATUM_LENS_REGISTRY.catalog() if e["lens_id"] == "fiat_cents")
        self.assertTrue(entry["label"])
        self.assertTrue(entry["description"])
        self.assertIn("fiat_babelette", entry["bindings"]["families"])


if __name__ == "__main__":
    unittest.main()
