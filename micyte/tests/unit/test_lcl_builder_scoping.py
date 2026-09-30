"""`LclBuilder` reuse semantics — what "already exists" means when minting an lcl node.

Both defects here matter because Phase 3 puts a GENERIC create path on top of this builder. A
bespoke caller can get away with a quirk it knows about; a generic one that mints whatever the
tree asks for cannot.

* :meth:`LclBuilder.mint_child` reused by title GLOBALLY, so ``mint_child("1-1", "notes")`` and
  ``mint_child("1-2", "notes")`` returned the SAME node — the second call silently handed back
  the first parent's child instead of minting under the parent asked for. Two records with the
  same name under different parents are two records; anything else loses one of them.
* :meth:`LclBuilder.ensure` reused by title only, never checking whether the NODE it was asked
  for already exists. Live, ``1-1-6-1`` in trapp is titled ``invoice_instance``, and
  ``save_invoice`` calls ``ensure("1-1-6-1", "invoice", …)`` — the title does not match, so it
  appended a SECOND definition row for a node that was already defined.

Reuse stays global for `ensure` on purpose: it is asked for a concept at a fixed address, so if
that concept already lives at a different address it must hand back the real one. Only the
question "is this node already defined" is answered before the title lookup.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from micyte.agro.doc_lib import LclBuilder, _row
from micyte.core.datum_ops.labels import RF_LCL_ID, RF_NODE_ID, RF_TITLE


def _rows(*specs: tuple[str, str, str]):
    return [
        _row(f"4-2-{i}", [[f"4-2-{i}", marker, node, RF_TITLE, "0" * 8], [label]])
        for i, (node, label, marker) in enumerate(specs, start=1)
    ]


def _defined(builder: LclBuilder) -> list[tuple[str, str]]:
    """(node, label) for every row the builder would ADD."""
    return [(r.raw[0][2], r.raw[1][0]) for r in builder.overlay.values()]


class MintChildScopingTests(unittest.TestCase):
    def test_the_same_label_under_two_parents_mints_two_nodes(self) -> None:
        builder = LclBuilder(_rows(("1-1", "entity", RF_NODE_ID), ("1-2", "land", RF_NODE_ID)))
        first = builder.mint_child("1-1", "notes", RF_LCL_ID)
        second = builder.mint_child("1-2", "notes", RF_LCL_ID)
        self.assertEqual(first, "1-1-1")
        self.assertEqual(second, "1-2-1")
        self.assertNotEqual(first, second)

    def test_the_same_label_under_one_parent_is_still_reused(self) -> None:
        # Idempotency is the point of reuse — re-minting must not grow the tree.
        builder = LclBuilder(_rows(("1-1", "entity", RF_NODE_ID)))
        first = builder.mint_child("1-1", "notes", RF_LCL_ID)
        self.assertEqual(builder.mint_child("1-1", "notes", RF_LCL_ID), first)
        self.assertEqual(len(builder.overlay), 1)

    def test_reuse_finds_a_child_that_was_already_in_the_document(self) -> None:
        builder = LclBuilder(_rows(("1-1", "entity", RF_NODE_ID),
                                   ("1-1-1", "notes", RF_LCL_ID)))
        self.assertEqual(builder.mint_child("1-1", "notes", RF_LCL_ID), "1-1-1")
        self.assertEqual(builder.overlay, {})

    def test_a_retired_sibling_label_is_still_reused_under_its_own_parent(self) -> None:
        # The effective-dating invariant (test_agro_write_effective_dating) depends on this:
        # a retired label persists, and re-minting it under the SAME parent must hand back the
        # retired node rather than mint a duplicate. Per-parent scoping keeps that true.
        builder = LclBuilder(_rows(("1-2-2", "field", RF_NODE_ID),
                                   ("1-2-2-1", "cluster_1", RF_LCL_ID)))
        self.assertEqual(builder.mint_child("1-2-2", "cluster_1", RF_LCL_ID), "1-2-2-1")

    def test_ordinals_stay_contiguous_under_each_parent(self) -> None:
        # A SAMRAS structure refuses a gap, so the anchor recompile would fail on one.
        builder = LclBuilder(_rows(("1-1", "entity", RF_NODE_ID)))
        minted = [builder.mint_child("1-1", f"n{i}", RF_LCL_ID) for i in range(1, 4)]
        self.assertEqual(minted, ["1-1-1", "1-1-2", "1-1-3"])


class EnsureIdempotencyTests(unittest.TestCase):
    def test_an_already_defined_node_is_not_defined_a_second_time(self) -> None:
        # The live case: trapp's 1-1-6-1 is titled `invoice_instance`, and save_invoice asks for
        # ensure("1-1-6-1", "invoice"). Appending a second definition row for one node makes its
        # label resolution order-dependent and its kind ambiguous.
        builder = LclBuilder(_rows(("1-1-6-1", "invoice_instance", RF_NODE_ID)))
        self.assertEqual(builder.ensure("1-1-6-1", "invoice", RF_NODE_ID), "1-1-6-1")
        self.assertEqual(_defined(builder), [])

    def test_a_concept_that_lives_at_another_address_is_still_handed_back(self) -> None:
        # `ensure` is asked for a concept at a fixed address; when the concept already exists
        # elsewhere the caller must get the real node, not a duplicate at the requested one.
        builder = LclBuilder(_rows(("1-1-7", "invoice", RF_NODE_ID)))
        self.assertEqual(builder.ensure("1-1-6-1", "invoice", RF_NODE_ID), "1-1-7")
        self.assertEqual(_defined(builder), [])

    def test_an_absent_node_and_absent_label_is_minted_at_the_address_asked_for(self) -> None:
        builder = LclBuilder(_rows(("1-1-6", "records", RF_NODE_ID)))
        self.assertEqual(builder.ensure("1-1-6-1", "invoice", RF_NODE_ID), "1-1-6-1")
        self.assertEqual(_defined(builder), [("1-1-6-1", "invoice")])


if __name__ == "__main__":
    unittest.main()


class ADefinitionRowLivesInTheFamilyItsArityNames(unittest.TestCase):
    """The address is the arity (I7). Found 2026-09-29 when the store's replace door
    started judging what a writer hands back: a source pinned beside its glyph — id,
    title, pin, icon — was minted at `4-3` because the family counted the trailing
    references alone; and the extra pair was written BEFORE the references, where
    `local_domain.trailing_refs` stops reading, so the glyph behind it was invisible."""

    def _builder(self) -> LclBuilder:
        return LclBuilder(_rows(("1-1", "entity", RF_NODE_ID), ("1-2", "land", RF_NODE_ID)))

    def test_a_node_with_an_extra_pair_and_a_glyph_lives_at_4_4(self) -> None:
        builder = self._builder()
        node = builder.mint_new_child("1-1", "pinned", RF_LCL_ID,
                                      extra=(("rf.3-1-19", "deadbeef"),), icon="1-2")
        key = builder.row_by_node[node]
        head = builder.overlay[key].raw[0]
        self.assertEqual(key.split("-")[1], "4", key)
        self.assertEqual((len(head) - 1) // 2, 4)

    def test_the_references_come_before_the_extras(self) -> None:
        from micyte.core.datum_ops.local_domain import trailing_refs

        builder = self._builder()
        node = builder.mint_new_child("1-1", "pinned", RF_LCL_ID,
                                      extra=(("rf.3-1-19", "deadbeef"),), icon="1-2")
        head = builder.overlay[builder.row_by_node[node]].raw[0]
        self.assertEqual(trailing_refs(head), ("1-2",), head)
        self.assertEqual(head[-2:], ["rf.3-1-19", "deadbeef"])

    def test_a_row_the_tree_holds_past_4_4_is_still_a_definition(self) -> None:
        rows = _rows(("1-1", "entity", RF_NODE_ID))
        rows.append(_row("4-5-1", [["4-5-1", RF_LCL_ID, "1-1-1", RF_TITLE, "0" * 8,
                                    RF_LCL_ID, "1-2", RF_LCL_ID, "1-3", "rf.3-1-8", "0" * 8], ["wide"]]))
        builder = LclBuilder(rows)
        self.assertIn("1-1-1", builder.node_set)
        self.assertEqual(builder.next_address("4-5"), "4-5-2")

    def test_a_node_on_a_marker_nobody_classified_is_still_seen(self) -> None:
        rows = _rows(("1-1", "entity", RF_NODE_ID))
        rows.append(_row("4-2-2", [["4-2-2", "rf.9-9-9", "1-1-1", RF_TITLE, "0" * 8], ["mystery"]]))
        self.assertIn("1-1-1", LclBuilder(rows).node_set)
