"""The three manipulation primitives (TASK-2026-09-16-002 P2) as SET operations, refused
whole by the invariants, with every referrer following the move.

The operator's worked example is the second class: a document holding 60+ value-group-3
rows (``lcl_id`` + ``title`` + a weight) that all gain a fiat value — note the digest,
copy ``4-3-n..m``, delete them, create the 60 in ``4-4`` after its last row with the
addresses shifted by ``m-n``.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from micyte.core.datum_ops import row_address
from micyte.core.mss import transform as tf
from micyte.core.mss.invariants import InvariantRefused, check_rows

LCL, TITLE, WEIGHT, PRICE = "rf.3-1-5", "rf.3-1-2", "rf.3-1-9", "rf.3-1-21"


def product(n: int, *, grams: int) -> tuple[str, list]:
    a = f"4-3-{n}"
    return a, [[a, LCL, f"1-3-2-{n}", TITLE, f"product_{n}", WEIGHT, str(grams)], [f"product_{n}"]]


def sixty_products() -> list[tuple[str, list]]:
    rows = [("4-1-1", [["4-1-1"]])]
    rows += [product(n, grams=100 + n) for n in range(1, 61)]
    # Two strangers in the same family: a different material (no weight; a note instead).
    rows.append(("4-3-61", [["4-3-61", LCL, "1-3-9", TITLE, "a note", "rf.3-1-7", "hello"], ["a note"]]))
    rows.append(("4-3-62", [["4-3-62", LCL, "1-3-9", TITLE, "b note", "rf.3-1-7", "there"], ["b note"]]))
    # A collection that references the products by address — the referrer that must follow.
    rows.append(("5-0-1", [["5-0-1", "~", "4-3-1", "4-3-2", "4-3-60", "4-3-61"], ["all"]]))
    return rows


class SiblingDetection(unittest.TestCase):
    def test_the_run_is_the_rows_of_one_material_under_one_parent(self) -> None:
        siblings = tf.sibling_set(sixty_products(), layer=4, value_group=3, parent=WEIGHT)
        self.assertEqual(len(siblings), 60)
        self.assertEqual((siblings.first, siblings.last), ("4-3-1", "4-3-60"))
        self.assertEqual(siblings.markers, (LCL, TITLE, WEIGHT))

    def test_a_parent_nobody_references_is_refused(self) -> None:
        with self.assertRaises(tf.TransformRefused):
            tf.sibling_set(sixty_products(), layer=4, value_group=3, parent="rf.3-1-99")

    def test_start_picks_the_run_that_holds_it(self) -> None:
        notes = tf.sibling_set(sixty_products(), layer=4, value_group=3, parent="rf.3-1-7", start="4-3-62")
        self.assertEqual(notes.addresses, ("4-3-61", "4-3-62"))


class TheSetTransform(unittest.TestCase):
    def test_sixty_products_gain_a_price_and_land_in_4_4_after_its_last_row(self) -> None:
        rows = sixty_products()
        siblings = tf.sibling_set(rows, layer=4, value_group=3, parent=WEIGHT)
        out = tf.transform_set(rows, siblings, add=[(PRICE, "250")])
        addresses = [a for a, _ in out.rows]
        self.assertEqual([a for a in addresses if a.startswith("4-4-")], [f"4-4-{n}" for n in range(1, 61)])
        # the strangers closed the gap the sixty left
        self.assertEqual([a for a in addresses if a.startswith("4-3-")], ["4-3-1", "4-3-2"])
        self.assertEqual(out.remap["4-3-1"], "4-4-1")
        self.assertEqual(out.remap["4-3-60"], "4-4-60")
        self.assertEqual(out.remap["4-3-61"], "4-3-1")
        self.assertNotEqual(out.digest_before, out.digest_after)
        by = dict(out.rows)
        self.assertEqual(by["4-4-7"][0][-2:], [PRICE, "250"])
        self.assertEqual(by["4-4-7"][0][0], "4-4-7")

    def test_every_referrer_follows(self) -> None:
        rows = sixty_products()
        out = tf.transform_set(rows, tf.sibling_set(rows, layer=4, value_group=3, parent=WEIGHT), add=[(PRICE, "1")])
        collection = dict(out.rows)["5-0-1"][0]
        self.assertEqual(collection, ["5-0-1", "~", "4-4-1", "4-4-2", "4-4-60", "4-3-1"])

    def test_the_result_keeps_every_invariant(self) -> None:
        rows = sixty_products()
        out = tf.transform_set(rows, tf.sibling_set(rows, layer=4, value_group=3, parent=WEIGHT), add=[(PRICE, "1")])
        self.assertEqual(check_rows(out.rows), ())

    def test_a_transform_that_would_break_an_invariant_is_refused_whole(self) -> None:
        rows = sixty_products()
        siblings = tf.sibling_set(rows, layer=4, value_group=3, parent=WEIGHT)
        with self.assertRaises(InvariantRefused) as caught:
            # a fourth pair forced into family 4-3: the arity says 4-4
            tf.transform_set(rows, siblings, add=[(PRICE, "1")], value_group=3)
        self.assertIn("I7", [r.invariant for r in caught.exception.refusals])

    def test_a_set_the_document_no_longer_holds_is_refused(self) -> None:
        rows = sixty_products()
        siblings = tf.sibling_set(rows, layer=4, value_group=3, parent=WEIGHT)
        fewer = [r for r in rows if r[0] != "4-3-30"]
        with self.assertRaises(tf.TransformRefused):
            tf.transform_set(fewer, siblings, add=[(PRICE, "1")])

    def test_the_input_is_never_edited(self) -> None:
        rows = sixty_products()
        before = tf.digest(rows)
        tf.transform_set(rows, tf.sibling_set(rows, layer=4, value_group=3, parent=WEIGHT), add=[(PRICE, "1")])
        self.assertEqual(tf.digest(rows), before)


class Redenote(unittest.TestCase):
    def test_one_row_moves_to_the_family_its_new_pair_names(self) -> None:
        rows = sixty_products()
        out = tf.redenote(rows, "4-3-30", value_group=4, add=[(PRICE, "999")])
        self.assertEqual(out.remap["4-3-30"], "4-4-1")
        # the family it left closed the gap: 4-3-31..62 became 4-3-30..61
        self.assertEqual(out.remap["4-3-31"], "4-3-30")
        self.assertEqual(out.remap["4-3-62"], "4-3-61")
        self.assertEqual(dict(out.rows)["5-0-1"][0], ["5-0-1", "~", "4-3-1", "4-3-2", "4-3-59", "4-3-60"])

    def test_re_denoting_without_the_pair_the_family_names_is_refused(self) -> None:
        with self.assertRaises(InvariantRefused):
            tf.redenote(sixty_products(), "4-3-30", value_group=4)

    def test_an_address_the_document_lacks_is_refused(self) -> None:
        with self.assertRaises(tf.TransformRefused):
            tf.redenote(sixty_products(), "4-3-99", value_group=4, add=[(PRICE, "1")])


class TheRepairs(unittest.TestCase):
    def test_reindex_heads_points_every_head_at_its_key(self) -> None:
        rows = [("4-1-1", [["4-1-1"]]), ("4-2-1", [["4-1-1", LCL, "1", TITLE, "x"], ["x"]]), ("4-2-2", [["4-1-2", LCL, "2", TITLE, "y"], ["y"]])]
        self.assertEqual({r.invariant for r in check_rows(rows)}, {"I6"})
        out = tf.reindex_heads(rows)
        self.assertEqual(out.remap, {})
        self.assertEqual(check_rows(out.rows), ())
        self.assertIn("2 heads", out.note)

    def test_compact_closes_the_gaps_and_referrers_follow(self) -> None:
        rows = [("4-1-1", [["4-1-1"]]), ("4-3-1", [["4-3-1", LCL, "1", TITLE, "a", WEIGHT, "1"], ["a"]]),
                ("4-3-4", [["4-3-4", LCL, "4", TITLE, "d", WEIGHT, "4"], ["d"]]),
                ("5-0-1", [["5-0-1", "~", "4-3-4"], ["c"]])]
        out = tf.compact(rows)
        self.assertEqual(out.remap, {"4-3-4": "4-3-2"})
        self.assertEqual(dict(out.rows)["5-0-1"][0], ["5-0-1", "~", "4-3-2"])
        self.assertEqual(dict(out.rows)["4-3-2"][0][0], "4-3-2")

    def test_two_movers_into_a_family_that_already_has_rows_land_consecutively(self) -> None:
        """Family 4-1 holds one row; four one-pair rows sit at 4-2 (I7). They move to
        4-1-2, 4-1-3, 4-1-4, 4-1-5 — not 2, 4, 6, 8: adding the family's highest to the
        highest already placed gave the second mover the address TWO past the first, a
        gap the transform then refused as its own I8; four live documents were refused so."""
        rows = [("4-1-1", [["4-1-1", "rf.3-1-7", "a"], ["one"]])] + [
            (f"4-2-{n}", [[f"4-2-{n}", "rf.3-1-7", f"v{n}"], [f"t{n}"]]) for n in range(1, 5)
        ]
        out = tf.readdress(rows)
        self.assertEqual(sorted(r[0] for r in out.rows), ["4-1-1", "4-1-2", "4-1-3", "4-1-4", "4-1-5"])
        self.assertEqual(out.remap, {"4-2-1": "4-1-2", "4-2-2": "4-1-3", "4-2-3": "4-1-4", "4-2-4": "4-1-5"})
        self.assertEqual(check_rows(out.rows), ())

    def test_readdress_is_the_09_11_repair_as_a_move(self) -> None:
        """BPW's 44 six-pair rows at 4-1-N; `row_address.readdressed` computes, this performs."""
        six = [LCL, "1", TITLE, "t", WEIGHT, "2", PRICE, "3", "rf.3-1-7", "n", "rf.3-1-8", "m"]
        rows = [("4-1-1", [["4-1-1"]])] + [(f"4-1-{n}", [[f"4-1-{n}", *six], ["job"]]) for n in range(2, 6)]
        mapping = row_address.readdressed(((a, r[0]) for a, r in rows))
        out = tf.readdress(rows)
        self.assertEqual(out.remap, mapping)
        self.assertEqual(sorted(a for a, _ in out.rows), ["4-1-1", "4-6-1", "4-6-2", "4-6-3", "4-6-4"])
        self.assertEqual(check_rows(out.rows), ())


if __name__ == "__main__":
    unittest.main()
