"""The fiat chain: what a cent is, where a sandbox keeps it, and how money is parsed.

Four things are being pinned here, and each of them is a wrong answer this design refuses:

1. **A price is a magnitude, not text.** ``parse_cents`` is the only door money comes
   through, and it refuses a third decimal place rather than rounding one — because
   rounding decides, silently, which half-cent the operator meant.
2. **The chain is identified by what it is made of.** ``find_fiat_chain`` matches structure,
   never an address or a label, so a sandbox that allocated it elsewhere still reads.
3. **Provisioning refuses a collision.** The same ``3-1-N`` names a different field in every
   namespace; relocating quietly would write prices against another field's meaning.
4. **A closure stands alone.** The rows that DEFINE a price reference travel with a
   published catalog, or the catalog is a number with no unit.
"""

from __future__ import annotations

import unittest

from micyte.core.datum_ops.fiat_datum import (
    FIAT_BABELETTE_LABEL,
    GOLD,
    GOLD_MASS_INCREMENTS,
    MIU,
    PREFERRED_FIAT_FIELD,
    FiatChain,
    FiatChainError,
    abstraction_closure,
    chain_rows_for_anchor,
    find_fiat_chain,
    format_cents,
    parse_cents,
    referenced_addresses,
)


class _Row:
    def __init__(self, datum_address: str, raw) -> None:
        self.datum_address = datum_address
        self.raw = raw


class _Doc:
    def __init__(self, rows) -> None:
        self.rows = tuple(rows)


def _rudis(count: int = 11) -> list[_Row]:
    names = ["time-ordinal-position", "time-incramental-unit", "spacial-ordinal-position",
             "spacial-incramental-unit", "nominal-ordinal-position", "nominal-incramental-unit",
             "mass-ordinal-position", "mass-incramental-unit", "fiat-currency-unit",
             "photon-particle-unit", "json-file-unit"]
    return [_Row(f"0-0-{i}", [[f"0-0-{i}", "~", "0-0-0"], [names[i - 1]]])
            for i in range(1, count + 1)]


def _farmlike_anchor(extra: list[_Row] | None = None) -> _Doc:
    """An anchor shaped like a live farm's: rudis, a couple of layer-1 structures, babelettes."""
    rows = [
        *_rudis(),
        _Row("1-1-1", [["1-1-1", "0-0-5", "0101"], ["txa-SAMRAS"]]),
        _Row("1-1-2", [["1-1-2", "0-0-6", "256"], ["nominal-bacillete-256"]]),
        _Row("2-1-4", [["2-1-4", "1-1-2", "17"], ["nominal-256-17"]]),
        _Row("3-1-7", [["3-1-7", "2-1-4", "0"], ["nominal-babelette"]]),
    ]
    rows.extend(extra or [])
    return _Doc(rows)


def _provisioned() -> tuple[_Doc, FiatChain]:
    anchor = _farmlike_anchor()
    new_rows, chain = chain_rows_for_anchor(anchor)
    return _Doc([*anchor.rows, *(_Row(r[0][0], r) for r in new_rows)]), chain


class ParseCentsTests(unittest.TestCase):
    def test_the_forms_an_operator_actually_types(self) -> None:
        for text, expected in (
            ("$4.50", 450), ("4.50", 450), ("4.5", 450), ("4", 400), ("$0.01", 1),
            ("$1,250.00", 125000), (" $4.50 ", 450), ("0.99", 99), ("$12", 1200),
        ):
            with self.subTest(text=text):
                self.assertEqual(parse_cents(text), expected)

    def test_a_third_decimal_place_is_refused_not_rounded(self) -> None:
        # The whole reason money is an integer here. Rounding $4.505 picks a half-cent
        # nobody chose, in a direction nobody declared, and the row records the result as
        # though it were what the operator typed.
        for text in ("$4.505", "4.999", "$0.001"):
            with self.subTest(text=text):
                with self.assertRaises(FiatChainError):
                    parse_cents(text)

    def test_nonsense_and_emptiness_are_refused(self) -> None:
        for text in ("", "   ", "free", "$", "4.5.6", "abc", None):
            with self.subTest(text=text):
                with self.assertRaises(FiatChainError):
                    parse_cents(text)

    def test_a_float_never_appears_in_the_round_trip(self) -> None:
        # 4.10 is not exactly representable in binary. Going through cents, it is exact.
        self.assertEqual(parse_cents("$4.10"), 410)
        self.assertEqual(format_cents(410), "$4.10")
        for cents in (1, 9, 10, 99, 100, 101, 12345, 999999):
            with self.subTest(cents=cents):
                self.assertEqual(parse_cents(format_cents(cents)), cents)

    def test_format_refuses_a_magnitude_that_is_not_whole_cents(self) -> None:
        for value in ("4.5", "abc", "0b1010"):
            with self.subTest(value=value):
                with self.assertRaises(FiatChainError):
                    format_cents(value)
        self.assertEqual(format_cents(""), "")

    def test_negative_survives_the_round_trip(self) -> None:
        # Not a price, but the same datum backs a credit, and a sign that silently
        # disappears is a refund that becomes a charge.
        self.assertEqual(parse_cents("-$4.50"), -450)
        self.assertEqual(format_cents(-450), "-$4.50")


class ChainDiscoveryTests(unittest.TestCase):
    def test_an_unprovisioned_anchor_yields_nothing(self) -> None:
        self.assertIsNone(find_fiat_chain(_farmlike_anchor()))
        self.assertIsNone(find_fiat_chain(None))
        self.assertIsNone(find_fiat_chain(_Doc([])))

    def test_the_chain_is_found_by_its_shape(self) -> None:
        anchor, chain = _provisioned()
        found = find_fiat_chain(anchor)
        self.assertEqual(found, chain)
        self.assertEqual(found.marker, f"rf.{PREFERRED_FIAT_FIELD}")

    def test_the_same_chain_is_found_at_a_different_address(self) -> None:
        # The point of structural discovery: a sandbox that provisioned elsewhere, or a
        # still that arrived from a network that numbered its own anchor differently, reads
        # exactly the same. Nothing here depends on 3-1-21.
        anchor = _farmlike_anchor([
            _Row("1-1-9", [["1-1-9", MIU, str(GOLD_MASS_INCREMENTS)], ["miu-babel-4600"]]),
            _Row("2-2-3", [["2-2-3", "1-1-9", "1", GOLD, "1"], ["fiat-baciloid-gold-cent"]]),
            _Row("3-1-17", [["3-1-17", "2-2-3", "0"], [FIAT_BABELETTE_LABEL]]),
        ])
        found = find_fiat_chain(anchor)
        self.assertIsNotNone(found)
        self.assertEqual(found.babelette_address, "3-1-17")
        self.assertEqual(found.marker, "rf.3-1-17")

    def test_a_label_alone_does_not_make_a_chain(self) -> None:
        # A row that CALLS itself the fiat babelette but is built out of something else is
        # not one. The structure is the identity; the label is a convenience.
        anchor = _farmlike_anchor([
            _Row("3-1-21", [["3-1-21", "2-1-4", "0"], [FIAT_BABELETTE_LABEL]]),
        ])
        self.assertIsNone(find_fiat_chain(anchor))

    def test_a_different_mass_magnitude_is_a_different_unit(self) -> None:
        # 4600 is the declaration. A chain built on 4601 is a different cent and must not
        # be read as this one.
        anchor = _farmlike_anchor([
            _Row("1-1-9", [["1-1-9", MIU, "4601"], ["miu-babel-4601"]]),
            _Row("2-2-1", [["2-2-1", "1-1-9", "1", GOLD, "1"], ["other"]]),
            _Row("3-1-21", [["3-1-21", "2-2-1", "0"], [FIAT_BABELETTE_LABEL]]),
        ])
        self.assertIsNone(find_fiat_chain(anchor))

    def test_the_value_group_is_the_tuple_count(self) -> None:
        anchor, chain = _provisioned()
        by_address = {r.datum_address: r.raw[0] for r in anchor.rows}
        self.assertEqual(chain.mass_address.split("-")[:2], ["1", "1"])
        self.assertEqual(len(by_address[chain.mass_address]) - 1, 2)      # one pair
        self.assertEqual(chain.unit_address.split("-")[:2], ["2", "2"])
        self.assertEqual(len(by_address[chain.unit_address]) - 1, 4)      # two pairs
        self.assertEqual(chain.babelette_address.split("-")[:2], ["3", "1"])
        self.assertEqual(len(by_address[chain.babelette_address]) - 1, 2)

    def test_the_cent_is_a_mass_of_gold(self) -> None:
        anchor, chain = _provisioned()
        by_address = {r.datum_address: r.raw[0] for r in anchor.rows}
        self.assertEqual(by_address[chain.mass_address][1:], [MIU, str(GOLD_MASS_INCREMENTS)])
        self.assertEqual(
            by_address[chain.unit_address][1:], [chain.mass_address, "1", GOLD, "1"])
        self.assertEqual(by_address[chain.babelette_address][1:], [chain.unit_address, "0"])


class ProvisioningTests(unittest.TestCase):
    def test_provisioning_twice_is_provisioning_once(self) -> None:
        anchor, chain = _provisioned()
        rows, again = chain_rows_for_anchor(anchor)
        self.assertEqual(rows, [])
        self.assertEqual(again, chain)

    def test_a_taken_address_is_refused_not_relocated(self) -> None:
        anchor = _farmlike_anchor([
            _Row(PREFERRED_FIAT_FIELD, [[PREFERRED_FIAT_FIELD, "2-1-4", "0"], ["something-else"]]),
        ])
        with self.assertRaises(FiatChainError):
            chain_rows_for_anchor(anchor)

    def test_an_address_already_referenced_is_refused(self) -> None:
        # Not defined as a row, but pointed at — the FARM namespace's undeclared `view`
        # marker is exactly this shape. Writing the babelette there would redefine a field
        # already in use, and every row carrying it would change meaning.
        anchor = _farmlike_anchor([
            _Row("4-1-1", [["4-1-1", PREFERRED_FIAT_FIELD, "1"], ["a record row"]]),
        ])
        with self.assertRaises(FiatChainError):
            chain_rows_for_anchor(anchor)

    def test_the_babelette_must_be_layer_three_value_group_one(self) -> None:
        for bad in ("2-1-9", "3-2-1", "not-an-address", "4-1-1"):
            with self.subTest(bad=bad):
                with self.assertRaises(FiatChainError):
                    chain_rows_for_anchor(_farmlike_anchor(), babelette_address=bad)

    def test_iterations_are_allocated_after_what_the_anchor_holds(self) -> None:
        anchor = _farmlike_anchor([
            _Row("1-1-6", [["1-1-6", "0-0-1", "1010"], ["HOPS-chronological"]]),
        ])
        _rows, chain = chain_rows_for_anchor(anchor)
        self.assertEqual(chain.mass_address, "1-1-7")


class AbstractionClosureTests(unittest.TestCase):
    def test_the_closure_defines_the_price_reference_and_nothing_irrelevant(self) -> None:
        anchor, chain = _provisioned()
        closure = abstraction_closure(anchor, [chain.marker])
        addresses = {r.datum_address for r in closure}
        # everything that DEFINES the price
        self.assertLessEqual(
            {chain.babelette_address, chain.unit_address, chain.mass_address}, addresses)
        # the rudi prefix it stands on, whole, per the canonical-value rule
        self.assertLessEqual({f"0-0-{i}" for i in range(1, 10)}, addresses)
        # and not the farm's unrelated structures
        self.assertNotIn("1-1-1", addresses)
        self.assertNotIn("3-1-7", addresses)

    def test_a_marker_and_a_bare_address_name_the_same_target(self) -> None:
        anchor, chain = _provisioned()
        self.assertEqual(
            [r.datum_address for r in abstraction_closure(anchor, [chain.marker])],
            [r.datum_address for r in abstraction_closure(anchor, [chain.babelette_address])],
        )

    def test_referenced_addresses_strips_markers(self) -> None:
        doc = _Doc([
            _Row("4-9-1", [["4-9-1", "rf.3-1-5", "1-1-5-1", "rf.3-1-21", "450"], ["offer"]]),
        ])
        # The REFERENCES only. `1-1-5-1` is the magnitude of the lcl pair — an lcl node,
        # not an anchor row — and a closure that chased it would be chasing the farm's
        # whole node tree, which is the trade this exists to avoid.
        self.assertEqual(referenced_addresses(doc), {"3-1-5", "3-1-21"})

    def test_an_unknown_address_contributes_nothing(self) -> None:
        anchor, _chain = _provisioned()
        self.assertEqual(abstraction_closure(anchor, ["9-9-9"]), [])
        self.assertEqual(abstraction_closure(anchor, []), [])


class ChainValidationTests(unittest.TestCase):
    def test_a_chain_needs_real_addresses(self) -> None:
        with self.assertRaises(FiatChainError):
            FiatChain(mass_address="nope", unit_address="2-2-1", babelette_address="3-1-21")


if __name__ == "__main__":
    unittest.main()
