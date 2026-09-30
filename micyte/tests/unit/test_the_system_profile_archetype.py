"""`system_profile` must recognise a real instance's profile, and collide with nothing.

The archetype library's rule (mint_archetype_sandbox, check 3): a row matching two
archetypes has NO archetype, because the binding would resolve by iteration order and
that is not a denotation. So an archetype is only legal if its required slots pick out a
shape no other archetype claims.

`system_profile` required `msn_id, title, lcl_id, instance_endpoint` until 2026-08-27.
That made it legal and made it describe ONE instance: `/__instance/contract/request`
refuses any request whose `owner_msn` is not the PORTAL's own, so the seven hosted
instances cannot publish a working `instance_endpoint`, and a fresh instance's local
domain has no classification node for `lcl_id` to point at. Seven of eight real profiles
could not match their own archetype.

Simply relaxing both is what a reader naturally reaches for and it is REFUSED by the
library, in two places at once — this file pins both, because the trap is that neither is
obvious and the second one was not predicted even by the comment that predicted the first.

The fix is a different required field, not a looser archetype: `dns`. Every hosted
instance exists to run a website and all eight have one.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "scripts"))

import mint_archetype_sandbox as mint

from micyte.core.datum_ops import archetype_shape as ash

PROFILE = next(a for a in mint.ARCHETYPES if a.name == "system_profile")


def _shape(*fields: str) -> ash.RowShape:
    return ash.RowShape(layer="4", fields=fields)


def _claimants(shape: ash.RowShape) -> list[str]:
    return [a.name for a in mint.ARCHETYPES if a.covers(shape)]


class TheRequiredSlotsAreWhatAnInstanceCanActuallyFill(unittest.TestCase):
    def test_the_required_set(self) -> None:
        self.assertEqual(
            tuple(s.name for s in PROFILE.slots if s.required),
            ("msn_id", "title", "dns"))

    def test_the_two_an_instance_cannot_fill_are_OPTIONAL(self) -> None:
        optional = {s.name for s in PROFILE.slots if not s.required}
        self.assertIn("lcl_id", optional)
        self.assertIn("instance_endpoint", optional)

    def test_a_real_profile_row_DENOTES_it(self) -> None:
        """The eight live rows, in the order the writer writes them."""
        self.assertEqual(_claimants(_shape("msn_id", "title", "dns")), ["system_profile"])

    def test_the_optional_slots_still_match_when_present(self) -> None:
        """An instance that later publishes an endpoint must not stop matching."""
        for extra in (("lcl_id",), ("instance_endpoint",), ("dns", "coordinate")):
            fields = tuple(dict.fromkeys(("msn_id", "title", "dns", *extra)))
            ordered = tuple(s.name for s in PROFILE.slots if s.name in fields)
            with self.subTest(fields=ordered):
                self.assertEqual(_claimants(_shape(*ordered)), ["system_profile"])


class ItClaimsNoShAPEAnotherArchetypeOwNS(unittest.TestCase):
    def test_no_two_archetypes_claim_one_maximal_shape(self) -> None:
        """Check 3, over the whole library — the guard the minter refuses to write past."""
        collisions = {
            str(a.shape): [b.name for b in mint.ARCHETYPES if b.covers(a.shape)]
            for a in mint.ARCHETYPES
        }
        self.assertEqual(
            {shape: names for shape, names in collisions.items() if len(names) > 1}, {})

    def test_relaxing_BOTH_would_collide_with_record_AND_legal_entity_profile(self) -> None:
        """Why `dns` is required rather than the archetype simply being loosened.

        Two collisions, and only the second was predicted by the comment that used to
        justify requiring `instance_endpoint`:

        * `(msn_id, title)` is `record` — 44,689 live rows of it. An archetype requiring
          only those two claims the most generic shape in the corpus.
        * `(msn_id, title, lcl_id, dns)` is `legal_entity_profile` — 162 live rows.

        A row matching two archetypes denotes NEITHER, so this would have taken the eight
        real profiles from denoting `record` to denoting nothing at all.
        """
        import dataclasses

        # The ORIGINAL declaration with those two relaxed — which is the change as it
        # would naturally be asked for. Built from the original SLOT ORDER, not by
        # relaxing today's: today's already has them optional, so "relax them" applied to
        # it is a no-op and the test would prove nothing while passing.
        as_asked = dataclasses.replace(PROFILE, slots=(
            mint._s("msn_id"), mint._s("title"),
            mint._s("lcl_id", opt=True), mint._s("instance_endpoint", opt=True),
            mint._s("dns", opt=True), mint._s("coordinate", opt=True)))
        library = [as_asked if a.name == "system_profile" else a for a in mint.ARCHETYPES]

        def claimants(shape):
            return sorted(a.name for a in library if a.covers(shape))

        self.assertEqual(claimants(_shape("msn_id", "title")),
                         ["record", "system_profile"])
        self.assertEqual(claimants(_shape("msn_id", "title", "lcl_id", "dns")),
                         ["legal_entity_profile", "system_profile"])

    def test_requiring_dns_is_what_avoids_BOTH(self) -> None:
        """The guard above would also pass on a declaration that collided differently.

        Named as a rule rather than a result: `dns` is required, and neither the shape
        `record` owns nor the shape `legal_entity_profile` owns contains it in a position
        this archetype would accept.
        """
        self.assertNotIn("system_profile", _claimants(_shape("msn_id", "title")))
        self.assertNotIn("system_profile",
                         _claimants(_shape("msn_id", "title", "lcl_id", "dns")))
        self.assertEqual(_claimants(_shape("msn_id", "title")), ["record"])


class TheViewscopeStillDrawsEverySlot(unittest.TestCase):
    def test_every_drawn_field_is_a_slot(self) -> None:
        """Reordering the slots must not leave the drawing pointing at a field that left."""
        _container, specs = mint.VIEWSCOPES["system_profile"]
        names = {s.name for s in PROFILE.slots}
        for spec in specs:
            with self.subTest(field=spec[2]):
                self.assertIn(spec[2], names)


if __name__ == "__main__":
    unittest.main()
