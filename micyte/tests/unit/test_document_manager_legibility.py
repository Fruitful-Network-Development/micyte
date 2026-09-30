"""The document manager's four claims, each checked against the shape that broke it.

Every test here replays a defect that shipped, because a guard written only against
the fixed code passes for the same reason the bug was invisible.
"""

from __future__ import annotations

import unittest

from micyte.core.datum_rules import family_column_template
from micyte.core.publication import (
    HELD_PRIVATE,
    PUBLISHED_CURRENT,
    PUBLISHED_STALE,
    UNPUBLISHED,
    build_publication_index,
)
from micyte.tools.workbench_ui.service import _sandbox_groups


class _Doc:
    """The three attributes the publication index reads off a document."""

    def __init__(self, document_id: str, canonical_name: str = "", version_hash: str = ""):
        self.document_id = document_id
        self.canonical_name = canonical_name
        self.document_name = canonical_name
        self.version_hash = version_hash


class _Still:
    def __init__(self, documents):
        self.documents = tuple(documents)


def _doc_id(sandbox: str, name: str, digest: str) -> str:
    return f"lv.3-2-3.{sandbox}.{name}.{digest * 64}"[: len(f"lv.3-2-3.{sandbox}.{name}.") + 64]


class LabelColumnTests(unittest.TestCase):
    """The row's own name must reach the grid."""

    def test_rudi_family_gets_a_label_column_for_its_list_tail(self) -> None:
        # The live shape: the tail is the only legible token on the row.
        rows = [("0-0-1", [["0-0-1", "~", "0-0-0"], ["time-ordinal-position"]])]
        roles = [c.role for c in family_column_template(rows)]
        self.assertEqual(roles, ["address", "label", "relation", "references"])

    def test_pairs_family_gets_a_label_column(self) -> None:
        rows = [("1-1-2", [["1-1-2", "0-0-6", "256"], ["nominal-bacillete-256"]])]
        roles = [c.role for c in family_column_template(rows)]
        self.assertEqual(roles, ["address", "label", "reference", "magnitude"])

    def test_a_family_with_no_tail_content_grows_no_label_column(self) -> None:
        # Otherwise every such family gains a column of blanks.
        rows = [("1-1-2", [["1-1-2", "0-0-6", "256"], []])]
        self.assertNotIn("label", [c.role for c in family_column_template(rows)])

    def test_record_family_keeps_its_dict_tail_for_record_keys(self) -> None:
        rows = [("3-0-1", [["3-0-1", "~", "0-0-9"], {"alpha": "A"}])]
        roles = [c.role for c in family_column_template(rows)]
        self.assertNotIn("label", roles)
        self.assertEqual(roles[:3], ["address", "relation", "reference"])

    def test_the_label_column_never_consumes_a_head_slot(self) -> None:
        """The grid walks head-backed roles POSITIONALLY, so their order is a contract."""
        rows = [("1-2-1", [["1-2-1", "0-0-5", "A", "0-0-6", "B"], ["two-pair-row"]])]
        roles = [c.role for c in family_column_template(rows)]
        self.assertEqual(
            [r for r in roles if r != "label"],
            ["address", "reference", "magnitude", "reference", "magnitude"],
        )


class SandboxGroupTests(unittest.TestCase):
    def test_the_group_holding_the_selection_sorts_first_and_is_the_only_one_open(self) -> None:
        """Sorting by size alone put registrar (484 of 510 documents) on top and
        buried the six other sandboxes under a scroll nobody would finish."""
        rows = [{"document_id": f"r{i}", "sandbox": "registrar"} for i in range(484)]
        rows.append({"document_id": "t1", "sandbox": "trapp", "selected": True})
        rows.append({"document_id": "s1", "sandbox": "system"})
        groups = _sandbox_groups(rows, active_sandbox="")
        self.assertEqual(groups[0]["sandbox"], "trapp")
        self.assertEqual([g["sandbox"] for g in groups if g["open"]], ["trapp"])

    def test_every_document_lands_in_exactly_one_group(self) -> None:
        rows = [
            {"document_id": "a", "sandbox": "x"},
            {"document_id": "b", "sandbox": "y"},
            {"document_id": "c", "sandbox": ""},
        ]
        groups = _sandbox_groups(rows)
        self.assertEqual(sum(g["count"] for g in groups), 3)
        self.assertIn("unfiled", [g["sandbox"] for g in groups])

    def test_some_group_is_always_open(self) -> None:
        groups = _sandbox_groups([{"document_id": "a", "sandbox": "x"}], active_sandbox="absent")
        self.assertTrue(any(g["open"] for g in groups))


class PublicationIndexTests(unittest.TestCase):
    def test_a_bare_name_never_matches_across_sandboxes(self) -> None:
        """THE bug: six sandboxes hold a document called `anchor`. Matching on the
        name alone reported all six as carried by a still holding only agnet's,
        producing ten confident and entirely false "published, stale" verdicts."""
        agnet_anchor = _Doc("lv.3-2-3.agnet.anchor." + "a" * 64, "anchor")
        trapp_anchor = _Doc("lv.3-2-3.trapp.anchor." + "b" * 64, "anchor")
        still = _Still([_Doc("lv.3-2-3.agnet.anchor." + "a" * 64, "anchor", "a" * 64)])
        index = build_publication_index(
            [agnet_anchor, trapp_anchor], stills={"agnet": still}, public_names=["agnet"]
        )
        self.assertEqual(index[agnet_anchor.document_id].verdict, PUBLISHED_CURRENT)
        self.assertEqual(index[trapp_anchor.document_id].verdict, UNPUBLISHED)

    def test_a_still_carrying_an_older_version_reads_as_stale(self) -> None:
        """The one state no timestamp finds and the only one an operator can act on."""
        live = _Doc("lv.3-2-3.agnet.lcl." + "c" * 64, "lcl")
        carried = _Doc("lv.3-2-3.agnet.lcl." + "d" * 64, "lcl", "d" * 64)
        index = build_publication_index(
            [live], stills={"agnet": _Still([carried])}, public_names=["agnet"]
        )
        self.assertEqual(index[live.document_id].verdict, PUBLISHED_STALE)
        self.assertEqual(index[live.document_id].still_version_hash, "d" * 64)

    def test_a_held_but_unlisted_still_is_private_not_a_fault(self) -> None:
        live = _Doc("lv.3-2-3.agnet.lcl." + "c" * 64, "lcl")
        index = build_publication_index(
            [live],
            stills={"draft": _Still([_Doc(live.document_id, "lcl", "c" * 64)])},
            public_names=[],  # the card lists nothing
        )
        self.assertEqual(index[live.document_id].verdict, HELD_PRIVATE)
        self.assertFalse(index[live.document_id].is_public)

    def test_the_sha256_marker_is_normalized_on_both_sides(self) -> None:
        """The store spells it `sha256:<hex>` and the MSS identity returns bare hex;
        comparing them unnormalized reports every document as stale."""
        live = _Doc("lv.3-2-3.agnet.lcl." + "c" * 64, "lcl")
        carried = _Doc(live.document_id, "lcl", "sha256:" + "c" * 64)
        index = build_publication_index(
            [live], stills={"agnet": _Still([carried])}, public_names=["agnet"]
        )
        self.assertEqual(index[live.document_id].verdict, PUBLISHED_CURRENT)

    def test_no_stills_means_no_entries_rather_than_confident_unpublished(self) -> None:
        """"Not published" and "not computed" are different facts. With no stills the
        index still answers for every document — the CALLER decides not to compute
        one at all, and then the payload carries no publication key."""
        live = _Doc("lv.3-2-3.agnet.lcl." + "c" * 64, "lcl")
        index = build_publication_index([live], stills={}, public_names=[])
        self.assertEqual(index[live.document_id].verdict, UNPUBLISHED)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
