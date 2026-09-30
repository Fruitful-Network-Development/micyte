"""The MSS engine's invariants are refused by the ENGINE — the codec on the wire, the
checker on the rows — and every refusal is reported at once.

Contract: ``docs/contracts/mss_engine_invariants.md``. Each invariant has a test here that
shows a violating document refused and, where the wire is involved, the repaired document
round-tripping the binary. The store-door half (``append_document_rows`` /
``create_document_rows`` refusing through the same checker) lives in
``test_the_store_door_refuses.py`` so this file needs no store.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from micyte.core.mss import invariants as inv
from micyte.core.mss.document_codec import (
    MssDatum,
    MssFormatError,
    MssTuple,
    decode_document,
    encode_document,
)


def T(ref: str, magnitude: int, kind: int = 0) -> MssTuple:
    return MssTuple(ref, kind, magnitude)


def _doc(rows):
    return [(address, raw) for address, raw in rows]


class TheWireRefusesWhatItCannotEncode(unittest.TestCase):
    """I1–I5. The codec's five refusals, now issued by ``check_datums`` and all at once."""

    def test_I1_a_duplicate_address_is_refused(self) -> None:
        refusals = inv.check_datums([MssDatum(0, 0, 1), MssDatum(0, 0, 1)])
        self.assertEqual([r.invariant for r in refusals], ["I1"])
        with self.assertRaises(MssFormatError) as caught:
            encode_document([MssDatum(0, 0, 1), MssDatum(0, 0, 1)])
        self.assertIn("duplicate datum address", str(caught.exception))

    def test_I4_a_reference_to_a_datum_not_in_the_set_is_refused(self) -> None:
        datums = [MssDatum(0, 0, 1), MssDatum(1, 1, 1, tuples=(T("0-0-2", 5),))]
        refusals = inv.check_datums(datums)
        self.assertEqual([(r.invariant, r.address) for r in refusals], [("I4", "1-1-1")])
        self.assertIn("references missing 0-0-2", refusals[0].sentence)

    def test_every_wire_refusal_is_reported_at_once(self) -> None:
        datums = [
            MssDatum(0, 0, 1),
            MssDatum(0, 0, 1),                                   # I1
            MssDatum(2, 1, 1, tuples=(T("0-0-1", 1),)),          # I2 (layer 1 missing)
            MssDatum(2, 1, 2, refs=("0-0-1",), tuples=(T("0-0-1", 1),)),  # I3
        ]
        ids = sorted({r.invariant for r in inv.check_datums(datums)})
        self.assertEqual(ids, ["I1", "I2", "I3"])
        with self.assertRaises(MssFormatError) as caught:
            encode_document(datums)
        for token in ("I1", "I2", "I3"):
            self.assertIn(token, str(caught.exception))

    def test_a_repaired_set_round_trips_the_binary(self) -> None:
        datums = [MssDatum(0, 0, 1), MssDatum(1, 1, 1, tuples=(T("0-0-1", 5),), title="a")]
        self.assertEqual(inv.check_datums(datums), ())
        encoded = encode_document(datums)
        self.assertEqual(decode_document(encoded.bitstream), datums)


class TheCheckerHoldsTheRows(unittest.TestCase):
    """I6–I10 over stored rows, pure."""

    def test_I6_a_head_that_names_another_address_is_refused(self) -> None:
        rows = _doc([("4-2-1", [["4-1-1", "rf.3-1-2", "1", "rf.3-1-3", "x"], ["t"]])])
        refusals = inv.check_rows(rows)
        self.assertEqual([(r.invariant, r.address) for r in refusals], [("I6", "4-2-1")])
        self.assertIn("names 4-1-1", refusals[0].sentence)

    def test_I6_does_not_apply_to_an_artifacts_rows(self) -> None:
        """``art.`` rows carry the chain reference first — ``datum_ops/artifact.py``."""
        rows = _doc([("2-1-1", [["1-1-7", "188419"], []]), ("5-1-1", [["4-1-1", 0, "12", 1], []])])
        self.assertEqual(inv.check_rows(rows, artifact=True), ())
        self.assertEqual({r.invariant for r in inv.check_rows(rows)}, {"I6"})

    def test_I7_an_instance_row_lives_in_the_family_its_arity_names(self) -> None:
        two_pairs_at_4_1 = _doc([("4-1-1", [["4-1-1"]]),
                                 ("4-1-2", [["4-1-2", "rf.3-1-2", "1", "rf.3-1-3", "x"], ["t"]])])
        refusals = inv.check_rows(two_pairs_at_4_1)
        self.assertEqual([(r.invariant, r.address) for r in refusals], [("I7", "4-1-2")])
        self.assertIn("family is 4-2, not 4-1", refusals[0].sentence)
        self.assertEqual(inv.check_rows(_doc([("4-2-1", [["4-2-1", "rf.3-1-2", "1", "rf.3-1-3", "x"], ["t"]])])), ())

    def test_I7_the_structural_blank_keeps_4_1(self) -> None:
        self.assertEqual(inv.check_rows(_doc([("4-1-1", [["4-1-1"]])])), ())
        blank_elsewhere = inv.check_rows(_doc([("4-3-1", [["4-3-1"]])]))
        self.assertEqual([r.invariant for r in blank_elsewhere], ["I7"])
        self.assertIn("blank", blank_elsewhere[0].sentence)

    def test_I7_a_refs_only_head_is_outside_the_rule(self) -> None:
        self.assertEqual(inv.check_rows(_doc([("4-0-1", [["4-0-1", "~", "1-1-1"], ["c"]])])), ())

    def test_I7_is_not_judged_below_the_row_layer(self) -> None:
        anchor_rows = _doc([("1-2-1", [["1-2-1", "0-0-1", "12345"], ["HOPS"]]),
                            ("3-1-21", [["3-1-21", "2-2-1", "0"], ["fiat-babelette"]])])
        self.assertEqual(inv.check_rows(anchor_rows), ())

    def test_I8_a_gap_in_a_layer_4_family_is_reported_once_with_the_first_hole(self) -> None:
        rows = _doc([("4-2-1", [["4-2-1", "rf.3-1-2", "1", "rf.3-1-3", "a"], ["t"]]),
                     ("4-2-3", [["4-2-3", "rf.3-1-2", "1", "rf.3-1-3", "b"], ["t"]])])
        refusals = inv.check_rows(rows)
        self.assertEqual([(r.invariant, r.address) for r in refusals], [("I8", "4-2-2")])

    def test_I8_is_not_judged_on_the_name_layers(self) -> None:
        """A babelette address is a field name; ``3-1-21`` beside ``3-1-1`` is not a gap."""
        rows = _doc([("3-1-1", [["3-1-1", "2-1-1", "0"], ["title-babelette"]]),
                     ("3-1-21", [["3-1-21", "2-2-1", "0"], ["fiat-babelette"]])])
        self.assertEqual(inv.check_rows(rows), ())

    def test_I9_is_the_doors_callback(self) -> None:
        rows = _doc([("4-2-1", [["4-2-1", "rf.3-1-2", "1", "rf.3-1-3", "a"], ["t"]])])
        self.assertEqual(inv.check_rows(rows, covers=lambda raw: True), ())
        refused = inv.check_rows(rows, covers=lambda raw: False, archetype="contact")
        self.assertEqual([(r.invariant, r.address) for r in refused], [("I9", "4-2-1")])
        self.assertIn("contact does not cover", refused[0].sentence)

    def test_I9_leaves_the_structural_rows_alone(self) -> None:
        """The blank and a `~` collection say nothing about a document's kind."""
        rows = _doc([("4-1-1", [["4-1-1"]]), ("5-0-1", [["5-0-1", "~", "4-1-1"], ["c"]])])
        self.assertEqual(inv.check_rows(rows, covers=lambda raw: False, archetype="contact"), ())

    def test_I10_a_title_longer_than_the_babelette_is_refused(self) -> None:
        rows = _doc([("4-1-1", [["4-1-1"], ["x" * 65]])])
        refusals = inv.check_rows(rows)
        self.assertEqual([(r.invariant, r.address) for r in refusals], [("I10", "4-1-1")])
        self.assertEqual(inv.check_rows(_doc([("4-1-1", [["4-1-1"], ["x" * 64]])])), ())

    def test_every_refusal_is_reported_not_the_first(self) -> None:
        rows = _doc([("4-1-1", [["4-1-1"]]),
                     ("4-1-2", [["4-1-9", "rf.3-1-2", "1", "rf.3-1-3", "x"], ["y" * 70]])])
        self.assertEqual(sorted(r.invariant for r in inv.check_rows(rows)), ["I10", "I6", "I7"])


class TheDoorJudgesOnlyWhatIsWritten(unittest.TestCase):
    """``check_new_rows``: the appended rows, against the document as it stands."""

    ARITY_DOC = _doc([("4-1-1", [["4-1-1"]]),
                      ("4-2-1", [["4-2-1", "rf.3-1-2", "1", "rf.3-1-3", "a"], ["t"]])])
    POSITIONAL_DOC = _doc([("4-1-1", [["4-1-1", "rf.3-1-6", "0-0-0", "rf.3-1-42", "59", "rf.3-1-43", "82"], ["t"]])])

    def test_a_row_one_past_the_highest_is_accepted(self) -> None:
        new = _doc([("4-2-2", [["4-2-2", "rf.3-1-2", "1", "rf.3-1-3", "b"], ["t"]])])
        self.assertEqual(inv.check_new_rows(self.ARITY_DOC, new), ())

    def test_I8_a_row_that_would_leave_a_gap_is_refused_with_the_next_address(self) -> None:
        new = _doc([("4-2-4", [["4-2-4", "rf.3-1-2", "1", "rf.3-1-3", "b"], ["t"]])])
        refusals = inv.check_new_rows(self.ARITY_DOC, new)
        self.assertEqual([(r.invariant, r.address) for r in refusals], [("I8", "4-2-4")])
        self.assertIn("the next row is 4-2-2", refusals[0].sentence)

    def test_an_existing_gap_is_not_the_next_writers_fault(self) -> None:
        gappy = _doc([("4-2-1", [["4-2-1", "rf.3-1-2", "1", "rf.3-1-3", "a"], ["t"]]),
                      ("4-2-3", [["4-2-3", "rf.3-1-2", "1", "rf.3-1-3", "c"], ["t"]])])
        new = _doc([("4-2-4", [["4-2-4", "rf.3-1-2", "1", "rf.3-1-3", "d"], ["t"]])])
        self.assertEqual(inv.check_new_rows(gappy, new), ())

    def test_I7_holds_a_document_that_keeps_the_arity_convention(self) -> None:
        new = _doc([("4-1-2", [["4-1-2", "rf.3-1-2", "1", "rf.3-1-3", "b"], ["t"]])])
        refusals = inv.check_new_rows(self.ARITY_DOC, new)
        self.assertEqual([r.invariant for r in refusals], ["I7"])

    def test_I7_leaves_a_positional_document_to_its_own_convention(self) -> None:
        """Measured 2026-09-17: 10,517 live rows use the value group positionally."""
        self.assertIs(inv.arity_convention_holds(self.POSITIONAL_DOC), False)
        new = _doc([("4-1-2", [["4-1-2", "rf.3-1-6", "0-0-1", "rf.3-1-42", "1", "rf.3-1-43", "2"], ["t"]])])
        self.assertEqual(inv.check_new_rows(self.POSITIONAL_DOC, new), ())

    def test_a_document_with_no_pair_rows_has_not_said_which_convention_it_keeps(self) -> None:
        blank_only = _doc([("4-1-1", [["4-1-1"]])])
        self.assertIsNone(inv.arity_convention_holds(blank_only))
        self.assertIs(inv.arity_convention_holds(self.ARITY_DOC), True)

    def test_I6_I9_I10_are_judged_on_the_new_rows(self) -> None:
        new = _doc([("4-2-2", [["4-2-9", "rf.3-1-2", "1", "rf.3-1-3", "b"], ["z" * 65]])])
        ids = sorted(r.invariant for r in inv.check_new_rows(self.ARITY_DOC, new, covers=lambda raw: False))
        self.assertEqual(ids, ["I10", "I6", "I9"])

    def test_the_refusal_carries_every_finding_as_data(self) -> None:
        err = inv.InvariantRefused([inv.Refusal("I6", "4-2-1", "a"), inv.Refusal("I8", "4-2-3", "b")])
        self.assertEqual([r.invariant for r in err.refusals], ["I6", "I8"])
        self.assertEqual(str(err), "I6 at 4-2-1: a; I8 at 4-2-3: b")


class TheReplaceDoorJudgesWhatChanged(unittest.TestCase):
    """``check_replaced_rows``: a whole document handed back, against the one it replaces."""

    ARITY_DOC = _doc([("4-1-1", [["4-1-1"]]),
                      ("4-2-1", [["4-2-1", "rf.3-1-2", "1", "rf.3-1-3", "a"], ["t"]]),
                      ("4-2-2", [["4-2-2", "rf.3-1-2", "2", "rf.3-1-3", "b"], ["t"]])])

    def test_an_appended_row_one_past_the_highest_is_accepted(self) -> None:
        new = _doc([("4-2-3", [["4-2-3", "rf.3-1-2", "3", "rf.3-1-3", "c"], ["t"]])])
        self.assertEqual(inv.check_replaced_rows(self.ARITY_DOC, [*self.ARITY_DOC, *new]), ())

    def test_I7_a_positional_row_in_an_arity_document_is_refused(self) -> None:
        """The live case: a four-pair row minted at 4-1-N by a writer with a literal family."""
        new = _doc([("4-1-2", [["4-1-2", "rf.3-1-2", "3", "rf.3-1-3", "c"], ["t"]])])
        found = inv.check_replaced_rows(self.ARITY_DOC, [*self.ARITY_DOC, *new])
        self.assertEqual([(r.invariant, r.address) for r in found], [("I7", "4-1-2")])

    def test_I7_leaves_a_positional_document_to_its_own_convention(self) -> None:
        positional = _doc([("4-1-1", [["4-1-1", "rf.3-1-6", "0-0-0", "rf.3-1-42", "59"], ["t"]])])
        new = _doc([("4-1-2", [["4-1-2", "rf.3-1-6", "0-0-0", "rf.3-1-42", "60"], ["t"]])])
        self.assertEqual(inv.check_replaced_rows(positional, [*positional, *new]), ())

    def test_I8_a_replacement_that_opens_a_gap_is_refused_at_the_first_hole(self) -> None:
        new = _doc([("4-2-5", [["4-2-5", "rf.3-1-2", "5", "rf.3-1-3", "e"], ["t"]])])
        found = inv.check_replaced_rows(self.ARITY_DOC, [*self.ARITY_DOC, *new])
        self.assertEqual([(r.invariant, r.address) for r in found], [("I8", "4-2-3")])

    def test_I8_a_compaction_that_closes_holes_is_accepted(self) -> None:
        gapped = _doc([("4-2-1", [["4-2-1", "rf.3-1-2", "1", "rf.3-1-3", "a"], ["t"]]),
                       ("4-2-4", [["4-2-4", "rf.3-1-2", "4", "rf.3-1-3", "d"], ["t"]])])
        compact = _doc([("4-2-1", [["4-2-1", "rf.3-1-2", "1", "rf.3-1-3", "a"], ["t"]]),
                        ("4-2-2", [["4-2-2", "rf.3-1-2", "4", "rf.3-1-3", "d"], ["t"]])])
        self.assertEqual(inv.check_replaced_rows(gapped, compact), ())

    def test_I8_a_hole_that_was_already_there_is_not_this_writers_fault(self) -> None:
        gapped = _doc([("4-2-1", [["4-2-1", "rf.3-1-2", "1", "rf.3-1-3", "a"], ["t"]]),
                       ("4-2-4", [["4-2-4", "rf.3-1-2", "4", "rf.3-1-3", "d"], ["t"]])])
        new = _doc([("4-2-5", [["4-2-5", "rf.3-1-2", "5", "rf.3-1-3", "e"], ["t"]])])
        self.assertEqual(inv.check_replaced_rows(gapped, [*gapped, *new]), ())

    def test_a_readdress_that_fills_a_family_from_one_is_accepted(self) -> None:
        """The I7 conversion: every row moves to the family its arity names."""
        positional = _doc([("4-1-1", [["4-1-1"]]),
                           ("4-1-2", [["4-1-2", "rf.3-1-2", "1", "rf.3-1-3", "a"], ["t"]]),
                           ("4-1-3", [["4-1-3", "rf.3-1-2", "2", "rf.3-1-3", "b"], ["t"]])])
        readdressed = _doc([("4-1-1", [["4-1-1"]]),
                            ("4-2-1", [["4-2-1", "rf.3-1-2", "1", "rf.3-1-3", "a"], ["t"]]),
                            ("4-2-2", [["4-2-2", "rf.3-1-2", "2", "rf.3-1-3", "b"], ["t"]])])
        self.assertEqual(inv.check_replaced_rows(positional, readdressed), ())

    def test_an_edited_row_is_judged_and_an_untouched_one_is_not(self) -> None:
        lying_prior = _doc([("4-2-1", [["4-2-9", "rf.3-1-2", "1", "rf.3-1-3", "a"], ["t"]])])
        # Handing the same lying row back unchanged: not this writer's doing.
        self.assertEqual(inv.check_replaced_rows(lying_prior, lying_prior), ())
        edited = _doc([("4-2-1", [["4-2-9", "rf.3-1-2", "1", "rf.3-1-3", "edited"], ["t"]])])
        found = inv.check_replaced_rows(lying_prior, edited)
        self.assertEqual([r.invariant for r in found], ["I6"])

    def test_a_delete_is_not_judged(self) -> None:
        self.assertEqual(inv.check_replaced_rows(self.ARITY_DOC, self.ARITY_DOC[:2]), ())

    def test_a_deletes_hole_is_admitted_but_a_skip_beside_it_is_not(self) -> None:
        """Dropping 4-2-1 leaves a hole where a row WAS: a delete's hole, admitted. Adding
        4-2-4 in the same replacement opens one where nothing ever was: refused there."""
        without_first = [self.ARITY_DOC[0], self.ARITY_DOC[2]]
        self.assertEqual(inv.check_replaced_rows(self.ARITY_DOC, without_first), ())
        skipped = [*without_first, ("4-2-4", [["4-2-4", "rf.3-1-2", "4", "rf.3-1-3", "d"], ["t"]])]
        found = inv.check_replaced_rows(self.ARITY_DOC, skipped)
        self.assertEqual([(r.invariant, r.address) for r in found], [("I8", "4-2-3")])


class ARawRowIsNotAPair(unittest.TestCase):
    """``_row`` reads ``[[address, …], [title]]`` as a row, not as an ``(address, raw)`` pair.

    Found 2026-09-29: ``arity_convention_holds`` over raw rows answered ``None`` for a
    document that plainly kept the convention, because each raw row is a two-element
    list and was read as a pair whose "address" was the head."""

    RAW = [["4-2-1", "rf.3-1-2", "1", "rf.3-1-3", "a"], ["t"]]

    def test_a_raw_row_parses_to_its_own_address(self) -> None:
        self.assertEqual(inv._row(self.RAW), ("4-2-1", self.RAW))

    def test_a_pair_still_parses_as_a_pair(self) -> None:
        self.assertEqual(inv._row(("4-2-1", self.RAW)), ("4-2-1", self.RAW))

    def test_the_convention_is_read_off_raw_rows(self) -> None:
        self.assertIs(inv.arity_convention_holds([self.RAW]), True)
        self.assertIs(inv.arity_convention_holds([[["4-1-1", "rf.3-1-2", "1", "rf.3-1-3", "a"], ["t"]]]), False)


if __name__ == "__main__":
    unittest.main()
