"""The next row address is the row's own arity, not the document's dominant family."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from micyte.core.datum_ops.row_address import (
    family_of,
    highest_iteration,
    next_row_address,
    readdressed,
    value_group_of,
)

BLANK = ["4-1-1"]
TWO = ["", "rf.3-1-4", "3-2-3-17", "rf.3-1-6", "tok"]
SIX = ["", "m", "a", "m", "b", "m", "c", "m", "d", "m", "e", "m", "f"]


class TheFamilyIsTheTupleCount(unittest.TestCase):
    def test_pairs_after_the_address(self) -> None:
        self.assertEqual(value_group_of(TWO), 2)
        self.assertEqual(value_group_of(SIX), 6)
        self.assertEqual(family_of(TWO), "4-2")
        self.assertEqual(family_of(SIX), "4-6")

    def test_the_blank_keeps_the_first_family(self) -> None:
        self.assertEqual(value_group_of(BLANK), 0)
        self.assertEqual(family_of(BLANK), "4-1")

    def test_the_iteration_is_per_family_one_past_the_highest(self) -> None:
        taken = ["4-1-1", "4-2-1", "4-2-7", "4-6-3", "not-an-address", "4-2-x"]
        self.assertEqual(highest_iteration(taken, "4-2"), 7)
        self.assertEqual(highest_iteration(taken, "4-9"), 0)
        self.assertEqual(next_row_address(taken, head=TWO), "4-2-8")
        self.assertEqual(next_row_address(taken, head=SIX), "4-6-4")
        self.assertEqual(next_row_address(["4-1-1"], head=SIX), "4-6-1")

    def test_a_dominant_family_does_not_pull_a_row_in(self) -> None:
        """The defect this module replaces: 44 rows at 4-1 and the 45th followed them."""
        taken = ["4-1-1", *[f"4-1-{i}" for i in range(2, 46)]]
        self.assertEqual(next_row_address(taken, head=SIX), "4-6-1")


class ReaddressingADocument(unittest.TestCase):
    def test_brocks_shape(self) -> None:
        """A blank at 4-1-1, 41 six-pair rows and 2 five-pair rows all at 4-1: the blank
        stays, the rest move to their own families numbered from 1, in address order."""
        rows = [("4-1-1", BLANK)]
        rows += [(f"4-1-{i}", SIX) for i in range(2, 43)]
        rows += [(f"4-1-{i}", SIX[:-2]) for i in (43, 44)]
        moves = readdressed(rows)
        self.assertNotIn("4-1-1", moves)
        self.assertEqual(moves["4-1-2"], "4-6-1")
        self.assertEqual(moves["4-1-42"], "4-6-41")
        self.assertEqual((moves["4-1-43"], moves["4-1-44"]), ("4-5-1", "4-5-2"))
        self.assertEqual(len(moves), 43)
        self.assertEqual(len(set(moves.values())), 43, "no two rows land on one address")

    def test_rows_already_home_keep_their_address_and_are_counted(self) -> None:
        rows = [("4-1-1", BLANK), ("4-6-1", SIX), ("4-1-2", SIX)]
        self.assertEqual(readdressed(rows), {"4-1-2": "4-6-2"})

    def test_a_document_that_obeys_the_rule_moves_nothing(self) -> None:
        self.assertEqual(readdressed([("4-1-1", BLANK), ("4-2-1", TWO), ("4-6-1", SIX)]), {})


if __name__ == "__main__":
    unittest.main()
