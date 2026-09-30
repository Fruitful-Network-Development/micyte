"""The TOLLING tab, and why the residue is the headline.

R8: *"a datum doc that backs the TOLLING tab which will collect the overall aws cost
incurred, **especially those items that arn't attributable to a client**, like processing
etc."*

The emphasis is the requirement. Measured across four periods on the live store:
**$317.66 total, $313.53 of it (98.7%) borne by FND, $4.13 attributable to a client.** The
per-grantee invoice this replaces was AWS cost x margin, and on those numbers the entire
client base billed $0.032 a month — because the cost that attributes to nobody was simply
not in the picture.

So a tolling tab that led with the attributable slice would reproduce that mistake in a
nicer table. Residue sorts first here, and the notice states the split before any row.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from micyte.tools.grantor_tolling import GrantorTolling, attribution_of


class TheAttributionIsREADNotDerived(unittest.TestCase):
    """The projection writes it into the note. Re-deriving it from the bearer msn would be
    a second definition of the split, free to disagree with the one that wrote the row."""

    def test_the_three_the_projection_writes(self) -> None:
        self.assertEqual(attribution_of("residue compute"), "residue")
        self.assertEqual(attribution_of("shared_pool compute"), "shared_pool")
        self.assertEqual(attribution_of("direct data_transfer"), "direct")

    def test_anything_else_is_unknown_not_guessed(self) -> None:
        for note in ("", "compute", "something else entirely", None):
            with self.subTest(note=note):
                self.assertEqual(attribution_of(note), "unknown")


class TheResidueLeads(unittest.TestCase):
    def _payload(self, rows):
        tool = GrantorTolling()
        tool._lines = lambda db, sandbox: list(rows)  # type: ignore[assignment]
        import micyte.tools.grantor_tolling as module

        real = module.cost_summary
        module.cost_summary = lambda db, sandbox=None: {
            "projected": True, "entries": len(rows), "total_cents": 1000,
            "total": "$10.00", "borne_by_fnd_cents": 900, "borne_by_fnd": "$9.00",
            "billable_cents": 100, "billable": "$1.00", "borne_by_fnd_pct": 90.0,
        }
        try:
            return tool.cost_pane(authority_db_file=Path("/x"), sandbox_id="grantor")
        finally:
            module.cost_summary = real

    @staticmethod
    def _line(attribution, cents):
        return {"attribution": attribution, "category": "compute",
                "amount": f"${cents/100:.2f}", "amount_cents": cents,
                "quantity": "—", "bearer": "someone"}

    def test_residue_sorts_above_a_LARGER_direct_line(self) -> None:
        """Amount alone would bury the unattributable lines among the attributable ones,
        which is exactly how a $0.032 invoice gets written."""
        payload = self._payload([self._line("direct", 90_000),
                                 self._line("residue", 1)])
        self.assertEqual([r["attribution"] for r in payload["rows"]],
                         ["residue", "direct"])

    def test_then_shared_pool_then_direct(self) -> None:
        payload = self._payload([self._line("direct", 10), self._line("shared_pool", 10),
                                 self._line("residue", 10)])
        self.assertEqual([r["attribution"] for r in payload["rows"]],
                         ["residue", "shared_pool", "direct"])

    def test_within_one_attribution_the_largest_leads(self) -> None:
        payload = self._payload([self._line("residue", 5), self._line("residue", 500)])
        self.assertEqual([r["amount_cents"] for r in payload["rows"]], [500, 5])

    def test_the_notice_states_the_split_before_any_row(self) -> None:
        payload = self._payload([self._line("residue", 10)])
        self.assertIn("borne by FND", payload["notice"])
        self.assertIn("90.0%", payload["notice"])
        self.assertIn("attributable to a client", payload["notice"])


class NoCostIsEverTyped(unittest.TestCase):
    """A cost row is a PROJECTION. A hand-entered one is a number that disagrees with the
    bill it claims to mirror, and nothing downstream could say which was right.

    The tab gained two writes on 2026-08-30 when the operator's legacy cost tabs came home
    to it, and NEITHER of them is a cost: billing rules are a rate card (a decision), and a
    recompute re-derives the ledger from AWS. The invariant this class defends is not "the
    tool never writes" — it is that no amount reaches the cost record except through a
    derivation, which is why the cost pane still has no editor.
    """

    def test_it_declares_no_datum_writes(self) -> None:
        self.assertEqual(getattr(GrantorTolling, "writes", ()), ())

    def test_the_cost_pane_is_a_record_table_not_an_editable_one(self) -> None:
        tool = GrantorTolling()
        payload = tool.cost_pane(authority_db_file=None)
        self.assertEqual(payload["container"], "record_table")
        self.assertNotIn("save_route", payload)
        self.assertNotIn("add_label", payload)
        self.assertNotIn("submit_action", payload)


class AnUnprojectedBookSaysSo(unittest.TestCase):
    def test_it_does_not_render_zero_as_a_cost(self) -> None:
        """An empty cost column reading '$0.00 of overhead' is the most flattering
        possible lie on the one page whose job is to prevent it."""
        import micyte.tools.grantor_tolling as module

        real = module.cost_summary
        module.cost_summary = lambda db, sandbox=None: {
            "projected": False, "note": "the cost book is empty", "entries": 0}
        try:
            payload = GrantorTolling().cost_pane(
                authority_db_file=Path("/x"), sandbox_id="grantor")
        finally:
            module.cost_summary = real
        self.assertEqual(payload["rows"], [])
        self.assertNotIn("$0.00", payload["notice"])
        self.assertIn("project_tolling_to_datum", payload["empty_text"])


if __name__ == "__main__":
    unittest.main()
