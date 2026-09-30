"""Job Synopsis — what the whole log adds up to.

A derivation, so the guards are about arithmetic honesty: money stays an integer until it
is rendered, and a figure that cannot be read is COUNTED but never TOTALLED.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

REPO_ROOT = Path(__file__).resolve().parents[3]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from micyte.adapters.sql import SqliteSystemDatumStoreAdapter
from micyte.core import archetypes as arc
from micyte.core.datum_documents import AuthoritativeDatumDocument, AuthoritativeDatumDocumentRow
from micyte.core.datum_ops.labels import encode_label_bits
from micyte.core.mss.datum_identity import compute_mss_hash
from micyte.ports.datum_store import AuthoritativeDatumDocumentCatalogResult
from micyte.tools import _node_names as nn
from micyte.tools.job_synopsis import JobSynopsis, _cents, _month

TENANT, SANDBOX = "fnd", "registrar"
MSN, TITLE, LCL, SITE = "rf.3-1-2", "rf.3-1-3", "rf.3-1-13", "rf.3-1-36"
UTC, PRICE = "rf.3-1-6", "rf.3-1-21"
REQ, OPT = arc.REQUIRED_FILLER, arc.OPTIONAL_FILLER


def row(address, cells):
    return AuthoritativeDatumDocumentRow(datum_address=address, raw=[[address, *cells]])


def document(sandbox, name, rows, metadata=None):
    def build(version):
        return AuthoritativeDatumDocument(
            document_id=f"lv.3-2-3-17.{sandbox}.{name}.{version}",
            source_kind="sandbox_source", document_name=f"{name}.json",
            relative_path=f"{sandbox}/{name}.json", canonical_name=name,
            tool_id=sandbox, is_anchor=False, rows=rows, document_metadata=metadata or {})

    draft = build("0" * 64)
    return build(compute_mss_hash(draft)["version_hash"].removeprefix("sha256:"))


def job(index, *, trade, when, pay=""):
    cells = [MSN, "3-2-3-17-1", SITE, "3-2-3-17-2", LCL, trade, UTC, when]
    if pay:
        cells += [PRICE, pay]
    return row(f"4-1-{index}", cells)


class CentsTests(unittest.TestCase):
    def test_a_cell_that_is_not_whole_cents_is_UNREADABLE_not_rounded(self) -> None:
        """The field is declared as whole cents, so `185.00` is ambiguous between $1.85
        and $185.00. Guessing either is worse than saying the job is unpriced — which the
        count then reports, so a partial total is legible rather than merely wrong."""
        self.assertIsNone(_cents("185.00"))
        self.assertIsNone(_cents("abc"))
        self.assertIsNone(_cents(""))

    def test_the_ordinary_forms_read(self) -> None:
        self.assertEqual(_cents("18500"), 18500)
        self.assertEqual(_cents("$18,500"), 18500)
        self.assertEqual(_cents("-500"), -500)

    def test_a_period_key_says_what_the_token_IS(self) -> None:
        """A HOPS token decodes only against its sandbox's chronology authority, and a
        synopsis that fell back to string slicing when it was missing would report a
        different grouping than it claimed."""
        self.assertEqual(_month("3-16-0"), "3-16")
        self.assertEqual(_month(""), "(undated)")


class JobSynopsisTests(unittest.TestCase):
    def setUp(self) -> None:
        self._dir = TemporaryDirectory(prefix="job_syn_")
        self.db = Path(self._dir.name) / "authority.sqlite3"
        self.store = SqliteSystemDatumStoreAdapter(self.db)
        self.store.store_authoritative_catalog(
            AuthoritativeDatumDocumentCatalogResult(
                tenant_id=TENANT, documents=(), source_files={}, readiness_status={}))
        self.store.replace_documents_efficient(tenant_id=TENANT, replacements=[
            (None, document(SANDBOX, "lcl", (
                row("4-1-1", [LCL, "1-1-9", TITLE, encode_label_bits("pressure_washing")]),
                row("4-1-2", [LCL, "1-1-10", TITLE, encode_label_bits("gutter_cleaning")]),
            ))),
            (None, document(SANDBOX, "job_log", (
                job(1, trade="1-1-9", when="3-16-0", pay="18500"),
                job(2, trade="1-1-9", when="3-16-4", pay="9000"),
                job(3, trade="1-1-10", when="3-17-0", pay="12000"),
                # booked, not yet priced
                job(4, trade="1-1-10", when="3-17-2"),
            ))),
            (None, document("archetype", "job_event", (
                row("4-1-1", [MSN, REQ, SITE, REQ, LCL, REQ, UTC, REQ, UTC, OPT,
                              PRICE, OPT, TITLE, OPT]),), {arc.ROLE_KEY: arc.ROLE_VALUE})),
            (None, document("archetype", "class_record",
                            (row("4-1-1", [LCL, REQ, TITLE, REQ]),),
                            {arc.ROLE_KEY: arc.ROLE_VALUE})),
        ])
        nn._INDEX_CACHE.clear()

    def tearDown(self) -> None:
        self._dir.cleanup()
        nn._INDEX_CACHE.clear()

    def panel(self, **query):
        nn._INDEX_CACHE.clear()
        return JobSynopsis().build_panel_payload(
            authority_db_file=self.db, sandbox_id=SANDBOX, document_id="",
            datum_address="", extra_query=query)

    def test_by_trade_totals_the_pay_and_names_the_trade(self) -> None:
        panel = self.panel()
        self.assertEqual(panel["jobs"], 4)
        by_label = {i["label"]: i["figure"] for i in panel["items"]}
        self.assertIn("pressure_washing · 2 jobs", by_label)
        self.assertEqual(by_label["pressure_washing · 2 jobs"], "$275.00")
        self.assertIn("gutter_cleaning · 2 jobs", by_label)
        self.assertEqual(by_label["gutter_cleaning · 2 jobs"], "$120.00")

    def test_an_unpriced_job_is_COUNTED_but_not_TOTALLED_and_says_so(self) -> None:
        """Treating it as zero would make an honest total indistinguishable from a lossy
        one — and the count is what lets an operator reconcile the difference."""
        panel = self.panel()
        self.assertEqual(panel["unpriced"], 1)
        self.assertIn("1 unpriced", panel["count_label"])
        self.assertEqual(panel["total"], "$395.00")

    def test_the_ranking_is_on_the_INTEGER_not_the_rendered_string(self) -> None:
        """Sorting the rendered figure puts "$9.00" above "$120.00"."""
        panel = self.panel()
        self.assertEqual(panel["items"][0]["label"], "pressure_washing · 2 jobs")

    def test_grouping_by_period_regroups_the_same_jobs(self) -> None:
        panel = self.panel(job_group="month")
        self.assertEqual(panel["jobs"], 4)
        self.assertEqual({i["label"] for i in panel["items"]},
                         {"3-16 · 2 jobs", "3-17 · 2 jobs"})

    def test_an_unknown_grouping_is_refused_rather_than_silently_defaulted(self) -> None:
        panel = self.panel(job_group="by_customer")
        self.assertEqual(panel["items"], [])
        self.assertIn("by_customer", panel["empty_text"])

    def test_a_sandbox_with_no_job_log_says_so(self) -> None:
        panel = JobSynopsis().build_panel_payload(
            authority_db_file=self.db, sandbox_id="taxonomy", document_id="",
            datum_address="", extra_query={})
        self.assertIn("job log", panel["empty_text"])

    def test_rows_that_are_not_jobs_are_not_counted(self) -> None:
        """The log carries its own scaffolding; a synopsis that counted it would report
        more jobs than were booked."""
        self.assertEqual(self.panel()["jobs"], 4)


if __name__ == "__main__":
    unittest.main()
