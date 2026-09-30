"""A crop photograph resolves to ONE taxon, once, and says why when it cannot.

TASK-2026-09-12-001 A2. Until 2026-08-03 this was a slug walk re-made in the browser on
every page load; these pin the ladder that replaced it, including the two shapes of
non-answer, because those are what an operator acts on.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from micyte.core.datum_ops.plantae_binding import bind, slug

#: A tree shaped like the live one: a genus, its species, and a cultivar group beneath.
TITLES = {
    "1-1-1": "Solanum",
    "1-1-1-1": "Solanum lycopersicum",
    "1-1-2": "Cucurbita",
    "1-1-2-1": "Cucurbita pepo",
    "1-1-2-1-1": "summer_squash",
    "1-1-2-2": "winter_squash",
    "1-1-3": "Triticum",
    "1-1-4": "Capsicum",
    "1-1-4-1": "Capsicum annuum",
    "1-1-5": "Brassica rapa",
    "1-1-5-1": "narinosa",
    "1-1-6": "sage",
    "1-1-7": "sage",
}


class TheLadderResolvesInOrder(unittest.TestCase):
    def test_a_species_is_its_own_title(self) -> None:
        (b,) = bind(["solanum_lycopersicum"], TITLES).bindings
        self.assertEqual((b.node, b.step), ("1-1-1-1", "whole stem"))

    def test_a_qualifier_resolves_UNDER_its_base(self) -> None:
        """`cucurbita_pepo.summer_squash` must land on the cultivar group beneath that
        species, not on a same-named node elsewhere."""
        (b,) = bind(["cucurbita_pepo.summer_squash"], TITLES).bindings
        self.assertEqual((b.node, b.step), ("1-1-2-1-1", "qualifier under its base"))

    def test_a_rank_abbreviation_comes_off_the_base(self) -> None:
        (b,) = bind(["triticum_spp"], TITLES).bindings
        self.assertEqual((b.node, b.step), ("1-1-3", "base without its rank abbreviation"))

    def test_the_last_token_is_the_final_step(self) -> None:
        (b,) = bind(["brassica_rapa.subsp_narinosa"], TITLES).bindings
        self.assertEqual((b.node, b.step), ("1-1-5-1", "last token"))

    def test_the_hybrid_mark_comes_off_too(self) -> None:
        titles = {**TITLES, "1-1-8": "Triticosecale"}
        (b,) = bind(["x_triticosecale_sp"], titles).bindings
        self.assertEqual(b.node, "1-1-8")


class WhatItRefusesToGuess(unittest.TestCase):
    def test_two_taxa_of_one_title_STOP_the_ladder(self) -> None:
        """Falling through to a broader step would answer a looser question than the one
        already answered badly."""
        (b,) = bind(["sage"], TITLES).bindings
        self.assertFalse(b.resolved)
        self.assertTrue(b.ambiguous)
        self.assertEqual(sorted(b.candidates), ["1-1-6", "1-1-7"])
        self.assertIn("say which", b.why)

    def test_a_plant_the_tree_lacks_entirely_says_so(self) -> None:
        (b,) = bind(["achillea_millefolium"], TITLES).bindings
        self.assertFalse(b.resolved or b.ambiguous)
        self.assertEqual(b.nearest, "")
        self.assertIn("would have to be minted", b.why)

    def test_a_photograph_MORE_SPECIFIC_than_the_tree_names_the_nearest(self) -> None:
        """`capsicum_annuum.sweet` is a picture of sweet peppers. Binding it to the species
        would call it a picture of Capsicum annuum, so it is reported with what the tree
        does carry — a different problem from a missing genus, and a different fix."""
        (b,) = bind(["capsicum_annuum.sweet"], TITLES).bindings
        self.assertFalse(b.resolved)
        self.assertEqual((b.nearest, b.nearest_slug), ("1-1-4-1", "capsicum_annuum"))
        self.assertIn("mint the node or accept the broader one", b.why)

    def test_two_photographs_of_one_taxon_are_reported_not_merged(self) -> None:
        report = bind(["solanum_lycopersicum", "solanum_lycopersicum"], TITLES)
        self.assertEqual(report.collisions(), {"1-1-1-1": ("solanum_lycopersicum",) * 2})


class TheReportIsTheDeliverable(unittest.TestCase):
    def test_the_three_outcomes_are_counted_and_kept_apart(self) -> None:
        report = bind(["solanum_lycopersicum", "sage", "achillea_millefolium"], TITLES)
        self.assertEqual(report.to_dict()["counts"],
                         {"stems": 3, "resolved": 1, "unmatched": 1, "ambiguous": 1})
        self.assertEqual(report.by_stem, {"solanum_lycopersicum": "1-1-1-1"})
        self.assertIn("achillea_millefolium", report.to_dict()["unmatched"])

    def test_slug_is_the_one_comparable_form(self) -> None:
        self.assertEqual(slug("Brassica rapa subsp. narinosa"), "brassica_rapa_subsp_narinosa")
        self.assertEqual(slug("  Solanum   lycopersicum  "), "solanum_lycopersicum")


if __name__ == "__main__":
    unittest.main()
