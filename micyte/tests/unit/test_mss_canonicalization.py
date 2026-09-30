from __future__ import annotations

import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from micyte.core.mss.canonicalization import (
    canonicalize_iteration_addresses,
    canonicalize_value_group_ordering,
)


def _row(addr: str, label: str = "x") -> dict:
    return {"datum_address": addr, "raw": [[addr, "~", "0-0-0"], [label]]}


class TestCanonicalizeIterationAddresses(unittest.TestCase):
    def test_no_op_when_already_contiguous(self) -> None:
        rows = [_row("0-0-1"), _row("0-0-2"), _row("0-0-3")]
        out, remap = canonicalize_iteration_addresses(rows)
        self.assertEqual([r["datum_address"] for r in out], ["0-0-1", "0-0-2", "0-0-3"])
        self.assertEqual(remap, {})

    def test_repairs_skipped_iteration(self) -> None:
        rows = [_row("0-0-1"), _row("0-0-3"), _row("0-0-7")]
        out, remap = canonicalize_iteration_addresses(rows)
        self.assertEqual([r["datum_address"] for r in out], ["0-0-1", "0-0-2", "0-0-3"])
        self.assertEqual(remap, {"0-0-3": "0-0-2", "0-0-7": "0-0-3"})

    def test_per_family_independent(self) -> None:
        rows = [_row("0-0-1"), _row("0-0-3"), _row("1-1-2"), _row("1-1-5")]
        out, remap = canonicalize_iteration_addresses(rows)
        addresses = [r["datum_address"] for r in out]
        self.assertEqual(addresses, ["0-0-1", "0-0-2", "1-1-1", "1-1-2"])
        self.assertEqual(remap, {"0-0-3": "0-0-2", "1-1-2": "1-1-1", "1-1-5": "1-1-2"})

    def test_input_not_mutated(self) -> None:
        rows = [_row("0-0-1"), _row("0-0-3")]
        snap = [r["datum_address"] for r in rows]
        canonicalize_iteration_addresses(rows)
        self.assertEqual([r["datum_address"] for r in rows], snap)


class TestCanonicalizeValueGroupOrdering(unittest.TestCase):
    def test_no_magnitude_callback_falls_back_to_iteration(self) -> None:
        rows = [_row("0-0-3"), _row("0-0-1"), _row("0-0-2")]
        out = canonicalize_value_group_ordering(rows)
        self.assertEqual([r["datum_address"] for r in out], ["0-0-1", "0-0-2", "0-0-3"])

    def test_magnitude_callback_orders_within_family(self) -> None:
        rows = [
            {"datum_address": "1-1-1", "magnitude": 30},
            {"datum_address": "1-1-2", "magnitude": 10},
            {"datum_address": "1-1-3", "magnitude": 20},
        ]
        out = canonicalize_value_group_ordering(rows, magnitude_of=lambda r: r.get("magnitude"))
        self.assertEqual([r["datum_address"] for r in out], ["1-1-2", "1-1-3", "1-1-1"])

    def test_magnitude_returning_none_falls_back_to_iteration(self) -> None:
        rows = [
            {"datum_address": "0-0-3", "magnitude": None},
            {"datum_address": "0-0-1", "magnitude": None},
            {"datum_address": "0-0-2", "magnitude": None},
        ]
        out = canonicalize_value_group_ordering(rows, magnitude_of=lambda r: r.get("magnitude"))
        self.assertEqual([r["datum_address"] for r in out], ["0-0-1", "0-0-2", "0-0-3"])

    def test_iteration_not_renumbered(self) -> None:
        rows = [
            {"datum_address": "1-1-1", "magnitude": 30},
            {"datum_address": "1-1-3", "magnitude": 10},
        ]
        out = canonicalize_value_group_ordering(rows, magnitude_of=lambda r: r.get("magnitude"))
        self.assertEqual([r["datum_address"] for r in out], ["1-1-3", "1-1-1"])


if __name__ == "__main__":
    unittest.main()
