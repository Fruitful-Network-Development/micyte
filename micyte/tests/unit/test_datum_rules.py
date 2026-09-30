"""Unit tests for the datum_rules shape authority.

Exemplars are taken from the live FND catalog shape census (47,234 rows) so the
classifier is validated against real data, including the awkward cases:
value_group != pair_count, bare-scalar payloads, and variable-arity rudi rows.
"""

from __future__ import annotations

import unittest

from micyte.core.datum_rules import (
    SHAPE_PAIRS,
    SHAPE_RECORD,
    SHAPE_RUDI,
    SHAPE_SCALAR,
    SHAPE_UNKNOWN,
    classify_row,
    family_column_template,
    validate_row,
)


class ClassifyRowTests(unittest.TestCase):
    def test_pairs_well_formed_matches_value_group(self) -> None:
        shape = classify_row("4-2-1", [["4-2-1", "ref.2-1-10", "1", "ref.3-1-4", "0110"], ["contract_request"]])
        self.assertEqual(shape.shape, SHAPE_PAIRS)
        self.assertEqual(shape.pair_count, 2)
        self.assertTrue(shape.well_formed)
        self.assertEqual(shape.issues, ())

    def test_pairs_vg1_bare_reference(self) -> None:
        shape = classify_row("1-1-1", [["1-1-1", "0-0-1", "0001"], ["HOPS-chronology"]])
        self.assertEqual(shape.shape, SHAPE_PAIRS)
        self.assertEqual(shape.pair_count, 1)
        self.assertTrue(shape.well_formed)
        self.assertEqual(shape.issues, ())

    def test_pairs_value_group_pair_mismatch_is_advisory_not_malformed(self) -> None:
        # Real row: value_group=1 but 4 (reference, magnitude) pairs (head_len 9).
        head = ["4-1-1", "rf.3-1-3", "addr", "rf.3-1-4", "elizabeth", "rf.3-1-4", "blake", "rf.3-1-9", "0101"]
        shape = classify_row("4-1-1", [head, ["contact"]])
        self.assertEqual(shape.shape, SHAPE_PAIRS)
        self.assertEqual(shape.pair_count, 4)
        self.assertTrue(shape.well_formed)
        self.assertEqual(shape.issues, ("value_group_pair_mismatch",))

    def test_pairs_even_head_is_malformed(self) -> None:
        shape = classify_row("1-1-2", [["1-1-2", "0101"], ["x"]])
        self.assertEqual(shape.shape, SHAPE_PAIRS)
        self.assertFalse(shape.well_formed)
        self.assertEqual(shape.issues, ("pairs_arity_malformed",))

    def test_rudi_layer0(self) -> None:
        shape = classify_row("0-0-1", [["0-0-1", "~", "0-0-0"], ["time-ordinal-position"]])
        self.assertEqual(shape.shape, SHAPE_RUDI)
        self.assertEqual(shape.value_group, 0)
        self.assertTrue(shape.well_formed)

    def test_rudi_variable_arity_layer_gt0(self) -> None:
        head = ["5-0-1", "~", "4-2-1", "4-2-2", "4-2-3", "4-2-4"]
        shape = classify_row("5-0-1", [head, ["event_type_collection"]])
        self.assertEqual(shape.shape, SHAPE_RUDI)
        self.assertEqual(shape.head_len, 6)
        self.assertTrue(shape.well_formed)

    def test_record_dict_tail(self) -> None:
        shape = classify_row("1-0-1", [["1-0-1", "~", "0-0-11"], {"created_at": "2026", "email": "a@b.c"}])
        self.assertEqual(shape.shape, SHAPE_RECORD)
        self.assertEqual(shape.tail_kind, "dict")
        self.assertTrue(shape.well_formed)

    def test_scalar_string_payload(self) -> None:
        shape = classify_row("0-0-1", "mycite.v2.datum.fnd.newsletter.contact_log.v2")
        self.assertEqual(shape.shape, SHAPE_SCALAR)
        self.assertTrue(shape.well_formed)

    def test_scalar_int_payload(self) -> None:
        shape = classify_row("0-0-3", 3)
        self.assertEqual(shape.shape, SHAPE_SCALAR)
        self.assertTrue(shape.well_formed)

    def test_unknown_address(self) -> None:
        shape = classify_row("not-an-address", [["x"]])
        self.assertEqual(shape.shape, SHAPE_UNKNOWN)
        self.assertFalse(shape.well_formed)
        self.assertEqual(shape.issues, ("address_unparsable",))

    def test_classify_is_total_on_garbage(self) -> None:
        # Must never raise, whatever the input.
        for addr, raw in [
            (None, None),
            ("", []),
            ("1-1-1", []),
            ("1-1-1", [[]]),
            ("1-1-1", [["1-1-1"]]),
            ("0-0-1", {"not": "a list"}),
            ("3-2-3", [{"head": "is dict not list"}]),
            (123, 456),
        ]:
            shape = classify_row(addr, raw)
            self.assertIn(shape.shape, {SHAPE_PAIRS, SHAPE_RECORD, SHAPE_RUDI, SHAPE_SCALAR, SHAPE_UNKNOWN})

    def test_validate_row_returns_issue_list(self) -> None:
        self.assertEqual(validate_row("4-2-1", [["4-2-1", "a", "b", "c", "d"], ["x"]]), [])
        self.assertEqual(validate_row("1-1-2", [["1-1-2", "0101"], ["x"]]), ["pairs_arity_malformed"])


class FamilyColumnTemplateTests(unittest.TestCase):
    def test_pairs_width_from_widest_row(self) -> None:
        rows = [
            ("4-2-1", [["4-2-1", "r", "m", "r", "m"], ["x"]]),  # 2 pairs
            ("4-2-2", [["4-2-2", "r", "m", "r", "m", "r", "m"], ["x"]]),  # 3 pairs
        ]
        cols = family_column_template(rows)
        # Both rows carry a list tail, so the family also gets its `label` column.
        # Width is still taken from the widest ROW: three pairs, six head columns.
        self.assertEqual(
            [c.role for c in cols],
            ["address", "label", "reference", "magnitude", "reference", "magnitude", "reference", "magnitude"],
        )
        # `label` reads the tail and consumes no head slot, so the head-backed
        # sequence the grid walks positionally is unchanged.
        self.assertEqual(
            [c.role for c in cols if c.role != "label"],
            ["address", "reference", "magnitude", "reference", "magnitude", "reference", "magnitude"],
        )
        self.assertEqual(len(cols), 8)

    def test_rudi_family_is_variadic(self) -> None:
        cols = family_column_template([("5-0-1", [["5-0-1", "~", "4-2-1"], ["poly"]])])
        self.assertEqual([c.role for c in cols], ["address", "label", "relation", "references"])
        self.assertTrue(cols[-1].variadic)

    def test_a_family_whose_rows_have_no_tail_content_grows_no_label_column(self) -> None:
        """Otherwise every such family gains a column of blanks."""
        cols = family_column_template([("5-0-1", [["5-0-1", "~", "4-2-1"], []])])
        self.assertEqual([c.role for c in cols], ["address", "relation", "references"])

    def test_record_family_unions_dict_keys(self) -> None:
        rows = [
            ("1-0-1", [["1-0-1", "~", "0-0-11"], {"a": 1, "b": 2}]),
            ("1-0-2", [["1-0-2", "~", "0-0-12"], {"b": 3, "c": 4}]),
        ]
        cols = family_column_template(rows)
        record_keys = [c.key for c in cols if c.role == "record_key"]
        self.assertEqual(record_keys, ["a", "b", "c"])

    def test_scalar_family(self) -> None:
        cols = family_column_template([("0-0-1", "schema.string")])
        self.assertEqual([c.role for c in cols], ["address", "value"])

    def test_empty_family(self) -> None:
        self.assertEqual([c.role for c in family_column_template([])], ["address"])


if __name__ == "__main__":
    unittest.main()
