"""The restricted-grammar glyph codec, round-tripped before anything is designed on it.

A picture that decodes to rows and back to the SAME rows is a picture the store can hold.
One that nearly does is a picture that will render differently after its first re-save, and
nothing will raise — so the round trip is the first test in this file and every other test
here exists to pin one bound it depends on.
"""
from __future__ import annotations

import unittest

from micyte.core.datum_ops.glyph import (
    GRID_BITS,
    GRID_EXTENT,
    LENGTH_BITS,
    Glyph,
    GlyphError,
    decode_length,
    decode_point,
    encode_length,
    encode_point,
    glyph_from_path_data,
    glyph_of,
    parse_path_data,
    rows_of,
)

#: The operator's rectangle, inside the canvas. Their own writing puts the far edge at 512;
#: 512 x 512 POSITIONS are 0..511, and 512 is the fencepost.
RECTANGLE = ("M0 0 A512 1 0 1 1 511 0 A1 512 0 1 1 511 511 "
             "A512 1 0 1 1 0 511 A1 512 0 1 1 0 0")
#: One arc out and one back — the smallest closed-looking shape the grammar can draw.
CIRCLE = "M0 256 A256 256 0 1 1 511 256 A256 256 0 1 1 0 256"


class TheRoundTripTests(unittest.TestCase):
    """rows -> glyph -> rows, byte-identical. The claim the rest of the file supports."""

    def _round_trip(self, glyph: Glyph) -> None:
        rows = rows_of(glyph)
        self.assertEqual(rows_of(glyph_of(rows)), rows)
        self.assertEqual(glyph_of(rows).to_path_data(), glyph.to_path_data())

    def test_the_rectangle(self) -> None:
        self._round_trip(glyph_from_path_data([RECTANGLE], fills=[True]))

    def test_a_circle(self) -> None:
        self._round_trip(glyph_from_path_data([CIRCLE], fills=[True]))

    def test_two_paths_keep_their_order_and_their_own_fills(self) -> None:
        glyph = glyph_from_path_data([RECTANGLE, CIRCLE], fills=[False, True])
        self._round_trip(glyph)
        back = glyph_of(rows_of(glyph))
        self.assertEqual([p.fill for p in back.paths], [False, True])
        self.assertEqual(back.to_path_data(), (RECTANGLE, CIRCLE))

    def test_the_path_data_comes_back_verbatim(self) -> None:
        back = glyph_of(rows_of(glyph_from_path_data([RECTANGLE])))
        self.assertEqual(back.to_path_data()[0], RECTANGLE)


class WhatARowLooksLikeTests(unittest.TestCase):
    """The address IS the arity, so each shape is asserted at the address it requires."""

    def setUp(self) -> None:
        self.rows = rows_of(glyph_from_path_data([RECTANGLE], fills=[True]))
        self.head = {r[0][0]: r[0][1:] for r in self.rows}

    def test_the_move_is_one_tuple_at_5_1(self) -> None:
        self.assertEqual(len(self.head["5-1-1"]), 2)

    def test_an_arc_is_FIVE_tuples_at_5_5(self) -> None:
        """rx, ry, large-arc, sweep, endpoint — which is why it is not 5-4 or 5-6."""
        self.assertEqual(len(self.head["5-5-1"]), 10)

    def test_a_path_is_references_only_at_6_0(self) -> None:
        self.assertEqual(self.head["6-0-1"][0], "~")
        self.assertEqual(self.head["6-0-1"][1:], ["5-1-1", "5-5-1", "5-5-2", "5-5-3", "5-5-4"])

    def test_the_top_row_declares_the_path_count(self) -> None:
        self.assertEqual(self.head["9-1-1"], ["8-0-1", "1"])

    def test_a_declared_count_that_disagrees_is_REFUSED(self) -> None:
        rows = [list(r) for r in self.rows]
        rows[-1] = [["9-1-1", "8-0-1", "4"], ["glyph"]]
        with self.assertRaises(GlyphError) as caught:
            glyph_of(rows)
        self.assertIn("declares 4", str(caught.exception))


class TheLengthOffsetTests(unittest.TestCase):
    """Nine bits address 1..512, not 0..511.

    The operator's own first arc is the evidence: the row carries ``rx = 111111111`` and the
    path it is said to equal begins ``A512 1``. Drop the offset and that arc has a radius of
    zero — which SVG draws as a STRAIGHT LINE, so the rectangle renders as a diagonal and
    nothing raises.
    """

    def test_the_top_of_the_range_is_all_ones(self) -> None:
        self.assertEqual(encode_length(GRID_EXTENT), "1" * LENGTH_BITS)

    def test_the_bottom_of_the_range_is_all_zeros(self) -> None:
        self.assertEqual(encode_length(1), "0" * LENGTH_BITS)

    def test_the_operators_own_first_arc_decodes_to_A512_1(self) -> None:
        self.assertEqual(decode_length("111111111"), 512)
        self.assertEqual(decode_length("000000000"), 1)

    def test_a_radius_of_zero_is_refused_and_says_why(self) -> None:
        with self.assertRaises(GlyphError) as caught:
            encode_length(0)
        self.assertIn("straight line", str(caught.exception))

    def test_a_radius_past_the_canvas_is_refused(self) -> None:
        with self.assertRaises(GlyphError):
            encode_length(GRID_EXTENT + 1)


class ThePointTests(unittest.TestCase):
    """A point is NOT offset: 262,144 positions are 0..511 and the far edge is 511."""

    def test_eighteen_bits_not_nineteen(self) -> None:
        self.assertEqual(GRID_BITS, 18)
        self.assertEqual(GRID_EXTENT * GRID_EXTENT, 262144)
        self.assertEqual(len(encode_point(0, 0)), 18)

    def test_x_is_the_high_half(self) -> None:
        self.assertEqual(encode_point(GRID_EXTENT - 1, 0), "1" * 9 + "0" * 9)
        self.assertEqual(encode_point(0, GRID_EXTENT - 1), "0" * 9 + "1" * 9)

    def test_every_corner_round_trips(self) -> None:
        far = GRID_EXTENT - 1
        for x, y in ((0, 0), (far, 0), (0, far), (far, far), (far, 1), (1, far)):
            self.assertEqual(decode_point(encode_point(x, y)), (x, y))

    def test_the_fencepost_is_refused_by_name(self) -> None:
        """512 is what the operator wrote; 511 is what 512 positions reach."""
        with self.assertRaises(GlyphError) as caught:
            encode_point(GRID_EXTENT, 0)
        self.assertIn("far edge is 511", str(caught.exception))


class WhatTheGrammarRefusesTests(unittest.TestCase):
    """One M, only A. A grammar that accepts what it cannot re-emit is a lossy parser."""

    def test_a_second_M_is_a_second_PATH(self) -> None:
        with self.assertRaises(GlyphError) as caught:
            parse_path_data("M0 0 A1 1 0 0 0 1 1 M5 5 A1 1 0 0 0 6 6")
        self.assertIn("ONE M per path", str(caught.exception))

    def test_a_curve_is_refused_and_NAMED(self) -> None:
        with self.assertRaises(GlyphError) as caught:
            parse_path_data("M0 0 C1 1 2 2 3 3")
        self.assertIn("C", str(caught.exception))

    def test_a_close_is_refused_and_NAMED(self) -> None:
        with self.assertRaises(GlyphError) as caught:
            parse_path_data("M0 0 A1 1 0 0 0 1 1 Z")
        self.assertIn("Z", str(caught.exception))

    def test_a_path_that_does_not_open_with_M(self) -> None:
        with self.assertRaises(GlyphError) as caught:
            parse_path_data("A1 1 0 0 0 1 1")
        self.assertIn("opens with M", str(caught.exception))

    def test_a_rotated_arc_is_refused_because_the_grammar_FIXES_it(self) -> None:
        with self.assertRaises(GlyphError) as caught:
            parse_path_data("M0 0 A1 1 45 0 0 1 1")
        self.assertIn("rotation", str(caught.exception))

    def test_a_fractional_coordinate_is_refused(self) -> None:
        with self.assertRaises(GlyphError) as caught:
            parse_path_data("M0.5 0 A1 1 0 0 0 1 1")
        self.assertIn("smallest step", str(caught.exception))

    def test_an_arc_with_the_wrong_number_of_numbers(self) -> None:
        with self.assertRaises(GlyphError) as caught:
            parse_path_data("M0 0 A1 1 0 0 1 1")
        self.assertIn("takes 7 numbers", str(caught.exception))

    def test_the_operators_own_stated_path_is_REFUSED_at_the_fencepost(self) -> None:
        """Their rectangle runs to 512. It is one unit outside a 512-position canvas."""
        stated = ("M0 0 A512 1 0 1 1 512 0 A1 512 0 1 1 512 512 "
                  "A512 1 0 1 1 0 512 A1 512 0 1 1 0 0")
        with self.assertRaises(GlyphError) as caught:
            parse_path_data(stated)
        self.assertIn("far edge is 511", str(caught.exception))


class WhatARowSETRefusesTests(unittest.TestCase):
    """Reading is as strict as writing, or a hand-edited document renders as something else."""

    def test_rows_with_no_top_datum(self) -> None:
        rows = rows_of(glyph_from_path_data([RECTANGLE]))[:-1]
        with self.assertRaises(GlyphError) as caught:
            glyph_of(rows)
        self.assertIn("9-1", str(caught.exception))

    def test_an_arc_row_whose_markers_are_not_an_arcs(self) -> None:
        rows = [list(r) for r in rows_of(glyph_from_path_data([RECTANGLE]))]
        rows[1] = [["5-5-1", "rf.3-1-3", "111111111", "rf.3-1-2", "000000000",
                    "rf.3-1-5", "1", "rf.3-1-5", "1", "rf.4-1-1", "1" * 18], ["x"]]
        with self.assertRaises(GlyphError) as caught:
            glyph_of(rows)
        self.assertIn("markers", str(caught.exception))

    def test_a_path_with_no_move(self) -> None:
        rows = [list(r) for r in rows_of(glyph_from_path_data([RECTANGLE]))]
        rows[5] = [["6-0-1", "~"], ["path-1"]]
        with self.assertRaises(GlyphError) as caught:
            glyph_of(rows)
        self.assertIn("opens with no M", str(caught.exception))


if __name__ == "__main__":
    unittest.main()


class TheGlyphCanvasContainerTests(unittest.TestCase):
    """The viewscope side: a container that draws a DOCUMENT rather than its fields."""

    def test_glyph_canvas_is_a_declared_container(self) -> None:
        from micyte.core.datum_ops import viewscope as vs

        self.assertIn("glyph_canvas", vs.CONTAINERS)

    def test_a_viewscope_may_declare_it_with_NO_SLOTS(self) -> None:
        """A glyph has no fields. A viewscope declaring slots here would be a form over
        a picture, and `load_viewscope` must not treat "no slots" as "no viewscope"."""
        from micyte.core.datum_documents import (
            AuthoritativeDatumDocument,
            AuthoritativeDatumDocumentRow,
        )
        from micyte.core.datum_ops import viewscope as vs

        scope = vs.Viewscope(archetype="svg_glyph", container="glyph_canvas", slots=())
        rows = tuple(
            AuthoritativeDatumDocumentRow(datum_address=r["datum_address"], raw=r["raw"])
            for r in vs.build_viewscope_rows(scope)
        )
        document = AuthoritativeDatumDocument(
            document_id="lv.0.archetype.viewscope_svg_glyph." + "0" * 64,
            source_kind="sandbox_source", document_name="viewscope_svg_glyph.json",
            relative_path="archetype/viewscope_svg_glyph.json",
            canonical_name="viewscope_svg_glyph", tool_id="archetype", is_anchor=False,
            rows=rows, document_metadata={"role": "viewscope"},
        )
        read, problems = vs.load_viewscope(document)
        self.assertEqual(problems, [])
        self.assertIsNotNone(read)
        self.assertEqual(read.container, "glyph_canvas")
        self.assertEqual(read.slots, ())


class TheArchetypeFoldReachesLayerFourTests(unittest.TestCase):
    """A babelette's LAYER is its chain's depth, and the corpus grew one at layer 4.

    `archetype_shape._classify` encodes the corpus as it was — every chain three deep, so
    every field marker at `3-1-N`. The glyph anchor's grid point is four deep. Folded as a
    POSITION it reads `<4-1>`, which merges "a point on the canvas" with "a reference to
    layer 4" and makes the arc archetype unrecognisable.
    """

    def test_a_declared_field_outside_3_1_resolves_by_NAME(self) -> None:
        from micyte.core.datum_ops.archetype_shape import row_shape

        head = ["5-1-1", "rf.4-1-1", "0" * 18]
        self.assertEqual(str(row_shape([head, ["m"]], sandbox="glyph")),
                         "L5:grid_point")

    def test_an_arc_folds_to_the_shape_the_archetype_declares(self) -> None:
        from micyte.core.datum_ops.archetype_shape import row_shape

        rows = rows_of(glyph_from_path_data([RECTANGLE]))
        self.assertEqual(str(row_shape(rows[1], sandbox="glyph")),
                         "L5:length+,nominal+,grid_point")

    def test_only_the_glyph_namespace_declares_a_field_outside_3_1(self) -> None:
        """What makes the rule above ADDITIVE, held as a fact rather than an argument.

        It can only turn an unresolved ``<a-b>`` into a name, never rename anything —
        but only while no other namespace declares an address the old fold called a
        position. The day one does, its documents' signatures move and every archetype
        binding for that sandbox has to be re-derived.
        """
        from micyte.core.datum_ops import field_registry as fr

        outside = {
            (field, address)
            for table in (fr.FIELD_ADDRESS, fr.EXTRA_FIELDS, fr.RESERVED_NEW_FIELDS)
            for fields in table.values()
            for field, address in fields.items()
            if not address.startswith("3-1-")
        }
        self.assertEqual(outside, {("grid_point", "4-1-1")})
