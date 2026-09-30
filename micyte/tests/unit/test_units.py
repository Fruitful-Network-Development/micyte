"""units.py — quantity parsing + unit-count derivation for agro_erp nominals."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from micyte.core.datum_ops.units import (
    derive_unit_count,
    is_count_unit,
    parse_quantity,
    to_grams,
)


class TestUnits(unittest.TestCase):
    def test_parse_quantity(self) -> None:
        self.assertEqual(parse_quantity("25 lbs"), (25.0, "lbs"))
        self.assertEqual(parse_quantity("0.5 oz"), (0.5, "oz"))
        self.assertEqual(parse_quantity("500 slips"), (500.0, "slips"))
        self.assertEqual(parse_quantity("$95.00"), (95.0, ""))
        self.assertEqual(parse_quantity(""), (0.0, ""))

    def test_is_count_unit(self) -> None:
        for u in ("slips", "roots", "bulbs", "count", "each"):
            self.assertTrue(is_count_unit(u), u)
        for u in ("lbs", "oz", "g", ""):
            self.assertFalse(is_count_unit(u), u)

    def test_to_grams(self) -> None:
        self.assertAlmostEqual(to_grams(1, "lb"), 453.59237, places=3)
        self.assertAlmostEqual(to_grams(1, "oz"), 28.349523, places=3)
        self.assertEqual(to_grams(5, "g"), 5.0)
        self.assertIsNone(to_grams(5, "slips"))

    def test_derive_unit_count(self) -> None:
        # count unit → the number is the count directly.
        self.assertEqual(derive_unit_count("500 slips", "5 g"), 500)
        # mass unit → grams(qty) / grams(unit weight), floored.
        self.assertEqual(derive_unit_count("1 lb", "1 g"), 453)
        # exact division that float represents as X.9999996 must not undercount (epsilon floor).
        self.assertEqual(derive_unit_count("3 g", "0.1 g"), 30)
        self.assertEqual(derive_unit_count("10 g", "0.1 g"), 100)
        # genuine fractional remainder still floors down.
        self.assertEqual(derive_unit_count("1 lb", "0.1 g"), 4535)
        # missing/zero unit weight for a mass purchase → None.
        self.assertIsNone(derive_unit_count("25 lbs", ""))
        self.assertIsNone(derive_unit_count("25 lbs", "0 g"))


if __name__ == "__main__":
    unittest.main()
