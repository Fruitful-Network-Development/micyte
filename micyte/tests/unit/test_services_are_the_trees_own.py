"""The services a customer can ask for are the tree's `services` branch — one reading.

Two surfaces offered "trades" before 2026-09-17 and neither read the tree the operator
grew: the jobs table offered every operator node (28 on one client's, `no_answer` among them)
and the several-services form asked for typed lines. `_services` is the one reading both
now declare. Pinned here against a tree shaped like a client's live one.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from micyte.core.datum_documents import AuthoritativeDatumDocumentRow as Row
from micyte.core.datum_ops import local_domain as ld
from micyte.core.datum_ops.labels import encode_label_bits
from micyte.tools._services import (
    labels_for,
    no_services_branch,
    service_options,
    services_from_selection,
    services_root,
)


def _definition(address: str, node: str, label: str) -> Row:
    return Row(datum_address=address, raw=[
        [address, "rf.3-1-1", node, "rf.3-1-2", encode_label_bits(label)], [label]])


#: A client's live objects subtree on 2026-09-17, in miniature, beside the branches a
#: reading must NOT mistake for services.
BROCKS = (
    ("1", "local_domain"), ("1-1", "meta"), ("1-2", "classes"), ("1-3", "objects"),
    ("1-3-1", "domain"), ("1-3-1-1", "kind"), ("1-3-1-1-1", "legal"),
    ("1-3-2", "services"), ("1-3-2-1", "trade"),
    ("1-3-2-1-1", "pressure_washing"),
    ("1-3-2-1-1-1", "house_wash"), ("1-3-2-1-1-1-1", "house_wash_2_story"),
    ("1-3-2-1-1-2", "driveway"),
    ("1-3-2-1-2", "gutter_cleaning"),
    ("1-3-2-1-3", "general_handyman"), ("1-3-2-1-3-1", "vehicle_service"),
    ("1-3-3", "outcomes"), ("1-3-3-1", "no_answer"),
)


def _log(pairs=BROCKS):
    rows = tuple(_definition(f"4-2-{i}", node, label) for i, (node, label) in enumerate(pairs, 1))
    return ld.read_log(type("Doc", (), {"rows": rows})())


class TheReading(unittest.TestCase):
    def test_only_the_services_branch_is_offered_and_in_tree_order(self) -> None:
        options = service_options(_log())
        self.assertEqual([o["value"] for o in options],
                         ["1-3-2-1-1", "1-3-2-1-1-1", "1-3-2-1-1-1-1", "1-3-2-1-1-2",
                          "1-3-2-1-2", "1-3-2-1-3", "1-3-2-1-3-1"])
        values = {o["value"] for o in options}
        # Not an outcome, not a kind, not the `trade` layer, not the branch itself.
        for wrong in ("1-3-3-1", "1-3-1-1-1", "1-3-2-1", "1-3-2", "1-3"):
            self.assertNotIn(wrong, values)

    def test_each_option_knows_its_trade_and_its_depth(self) -> None:
        by = {o["value"]: o for o in service_options(_log())}
        self.assertEqual(by["1-3-2-1-1"], {"value": "1-3-2-1-1", "label": "Pressure Washing",
                                            "group": "Pressure Washing", "depth": 0,
                                            "path": "Pressure Washing"})
        self.assertEqual(by["1-3-2-1-1-1-1"]["group"], "Pressure Washing")
        self.assertEqual(by["1-3-2-1-1-1-1"]["depth"], 2)
        self.assertEqual(by["1-3-2-1-1-1-1"]["path"],
                         "Pressure Washing > House Wash > House Wash 2 Story")
        self.assertEqual(by["1-3-2-1-2"]["depth"], 0)

    def test_a_tree_without_the_branch_offers_nothing_and_says_where(self) -> None:
        bare = _log(tuple(p for p in BROCKS if not p[0].startswith("1-3-2")))
        self.assertEqual(services_root(bare), "")
        self.assertEqual(service_options(bare), [])
        self.assertIn("Domain editor", no_services_branch("system"))


class TheSelection(unittest.TestCase):
    def setUp(self) -> None:
        self.options = service_options(_log())

    def test_a_posted_list_comes_back_as_services_in_tree_order(self) -> None:
        services, why = services_from_selection(["1-3-2-1-2", "1-3-2-1-1-2"], self.options)
        self.assertEqual(why, "")
        self.assertEqual(services, [{"lcl_id": "1-3-2-1-1-2"}, {"lcl_id": "1-3-2-1-2"}])
        self.assertEqual(labels_for(services, self.options), ["Driveway", "Gutter Cleaning"])

    def test_a_string_is_read_too_and_a_repeat_is_one_service(self) -> None:
        services, _ = services_from_selection("1-3-2-1-2, 1-3-2-1-2\n1-3-2-1-1", self.options)
        self.assertEqual([s["lcl_id"] for s in services], ["1-3-2-1-1", "1-3-2-1-2"])

    def test_nothing_selected_is_no_services_and_no_refusal(self) -> None:
        self.assertEqual(services_from_selection([], self.options), ([], ""))
        self.assertEqual(services_from_selection("", self.options), ([], ""))

    def test_a_node_the_branch_does_not_offer_is_refused_by_name(self) -> None:
        services, why = services_from_selection(["1-3-3-1"], self.options)
        self.assertEqual(services, [])
        self.assertIn("1-3-3-1", why)
        self.assertIn("services", why)


if __name__ == "__main__":
    unittest.main()
