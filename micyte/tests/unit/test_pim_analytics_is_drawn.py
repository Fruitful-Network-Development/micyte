"""PIM's Analytics tab draws its figures, and the Authoring tab is two things.

The operator's assessment on 2026-08-29: the tabs are "very under developed as far as
frontend design", Analytics "does not show any pie charts or graphics", the tables lack
"the backfilled logs like the legacy dashboard", and Authoring "should only be the gallery
and the draft sub tabs".

All three were true. Analytics was three tables of figures against a legacy dashboard that
drew five charts, top pages, top referrers and a per-visitor log — and every one of those
numbers was already computed and simply unreachable from a tool.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from micyte.tools.pim_overview import (
    ANALYTICS_QUERY,
    PimOverview,
    _month_label,
    _pretty,
    _seconds,
)

MONTHS = [
    {"period": "2026-07", "visitors": "56", "sessions": "89", "views": "171", "bots": "8"},
    {"period": "2026-08", "visitors": "58", "sessions": "77", "views": "153", "bots": "7"},
]
LIVE = {
    "summary": {"unique_visitors": 72},
    "top_pages": [{"key": "/", "count": 135}, {"key": "/media.html", "count": 118}],
    "top_referrers": [{"key": "l.instagram.com", "count": 25}],
    "widgets": {
        "origin_distribution": [{"key": "direct", "count": 59}, {"key": "social", "count": 22}],
        "device_split": [{"key": "mobile", "count": 206}, {"key": "desktop", "count": 191}],
        "human_vs_bot": [{"key": "human", "count": 397}, {"key": "bot", "count": 7}],
    },
    "interest_profile_categories": [{"category": "home", "hits": 148}],
    "dead_end_pages": [{"page_path": "/index.html", "entry_count": 6,
                        "single_page_session_rate": 0.667,
                        "average_active_time_ms": 5775}],
}


def _context(**over):
    ctx = {"analytics": {"months": MONTHS}, "analytics_summary": lambda days=90: LIVE,
           "analytics_records": lambda period="": {}, "campaigns": {}}
    ctx.update(over)
    return ctx


def _analytics(context=None, query=None):
    return PimOverview()._analytics_pane(
        {"permitted": "yes"}, context or _context(), query=query)


def _panes(pane):
    """Every leaf payload under a pane, flattened — composites nest one level."""
    out = []
    for entry in pane.get("panes", []):
        payload = entry.get("panel_payload") or entry
        if payload.get("container") == "composite":
            out.extend(p.get("panel_payload") or p for p in payload.get("panes", []))
        else:
            out.append(payload)
    return out


class TheOverviewIsDrawnNotTabulated(unittest.TestCase):
    def setUp(self) -> None:
        self.tab = _analytics()
        self.overview = next(t["panel_payload"] for t in self.tab["tabs"]
                             if t["id"] == "overview")
        self.leaves = _panes(self.overview)
        self.charts = [p for p in self.leaves if p.get("container") == "chart"]

    def test_the_month_strip_leads(self) -> None:
        """THE SIGNATURE, and it is first for a reason: "how am I doing" is the question
        somebody opens an analytics tab holding, and a lone big number cannot answer it."""
        first = self.leaves[0]
        self.assertEqual(first["container"], "chart")
        self.assertEqual(first["mode"], "series")
        self.assertEqual([s["key"] for s in first["series"]], ["2026-07", "2026-08"])

    def test_the_strip_is_also_the_period_control(self) -> None:
        # A chart and a navigator as one object, rather than a chart plus a dropdown.
        strip = self.leaves[0]
        self.assertEqual(strip["active"], "2026-08")

    def test_the_strip_says_which_way_it_moved(self) -> None:
        self.assertIn("up 2", self.leaves[0]["count_label"])
        self.assertIn("Jul", self.leaves[0]["count_label"])

    def test_the_bot_share_rides_inside_the_column(self) -> None:
        """Not beside it. A second column would read as twice the month."""
        self.assertEqual([s["secondary"] for s in self.leaves[0]["series"]], [8, 7])

    def test_there_are_charts_of_more_than_one_kind(self) -> None:
        """The operator asked for graphics; a wall of one chart type is a different kind
        of monotony. Each mode answers a different shape of question."""
        modes = {c["mode"] for c in self.charts}
        self.assertIn("series", modes)   # change over time
        self.assertIn("split", modes)    # parts of one whole
        self.assertIn("rank", modes)     # an ordered list
        self.assertIn("donut", modes)    # the pie that was asked for

    def test_ranked_lists_are_bars_and_not_rings(self) -> None:
        """A ranked list read as a ring makes the reader compare arc lengths. Bars share
        a baseline and the eye does it for free."""
        by_title = {c["title"]: c for c in self.charts}
        self.assertEqual(by_title["What they read"]["mode"], "rank")
        self.assertEqual(by_title["Where they came from"]["mode"], "rank")

    def test_the_keys_are_said_the_way_a_person_says_them(self) -> None:
        arrived = next(c for c in self.charts if c["title"] == "How people arrived")
        self.assertEqual([s["key"] for s in arrived["series"]],
                         ["Typed or bookmarked", "Social"])

    def test_it_reports_what_it_can_act_on(self) -> None:
        titles = {p.get("title") for p in self.leaves}
        self.assertIn("What interests them", titles)
        self.assertIn("Pages people leave from", titles)


class TheBackfilledLogIsThere(unittest.TestCase):
    """The legacy dashboard's "Visitor records". PIM had no equivalent at all."""

    def test_visitors_is_a_subtab(self) -> None:
        tab = _analytics()
        self.assertEqual([t["id"] for t in tab["tabs"]],
                         ["overview", "months", "visitors", "campaigns"])

    def test_it_reads_one_row_per_person(self) -> None:
        records = {"period": "2026-08", "leaflet": {"visitors": [
            {"label": "Visitor 1", "first_seen_at": "2026-08-01T12:09:50Z",
             "last_seen_at": "2026-08-02T09:00:00Z", "returning_from_prior_month": True,
             "sessions": [{"arrival": {"kind": "direct", "label": "Direct"}}, {}]},
        ]}}
        tab = _analytics(_context(analytics_records=lambda period="": records))
        log = next(t["panel_payload"] for t in tab["tabs"] if t["id"] == "visitors")
        self.assertEqual(log["row_count"], 1)
        row = log["rows"][0]
        self.assertEqual(row["who"], "Visitor 1")
        self.assertEqual(row["visits"], "2")
        self.assertEqual(row["arrived by"], "Direct")
        self.assertEqual(row["first seen"], "2026-08-01")
        self.assertEqual(row["returning"], "yes")
        self.assertIn("1 people", log["count_label"])

    def test_an_absent_reader_leaves_the_tab_standing(self) -> None:
        """A month with no leaflet must not take the client's application down."""
        tab = _analytics(_context(analytics_records=None))
        log = next(t["panel_payload"] for t in tab["tabs"] if t["id"] == "visitors")
        self.assertEqual(log["rows"], [])
        self.assertTrue(log["empty_text"])

    def test_a_reader_that_throws_is_survived(self) -> None:
        def boom(period=""):
            raise RuntimeError("no leaflet")

        tab = _analytics(_context(analytics_records=boom))
        self.assertTrue(tab["tabs"])


class ItStillWorksWithoutTheLiveRollup(unittest.TestCase):
    """The months come from the datum; everything drawn from the rollup is additive.

    A summary reader that fails must cost the charts it feeds and NOT the tab — the same
    posture every other seam here takes.
    """

    def test_the_months_alone_still_render_a_tab(self) -> None:
        tab = _analytics(_context(analytics_summary=lambda days=90: {}))
        self.assertEqual(tab["container"], "tabbed")
        months = next(t["panel_payload"] for t in tab["tabs"] if t["id"] == "months")
        self.assertEqual(months["row_count"], 2)

    def test_a_throwing_reader_is_survived(self) -> None:
        def boom(days=90):
            raise RuntimeError("leaflets unreadable")

        tab = _analytics(_context(analytics_summary=boom))
        self.assertTrue(tab["tabs"])

    def test_no_months_and_no_rollup_reports_the_seam(self) -> None:
        tab = _analytics(_context(analytics=None, analytics_summary=lambda days=90: {}))
        self.assertEqual(tab["container"], "record_table")


class TheSubTabHasItsOwnParameter(unittest.TestCase):
    def test_it_selects_and_falls_back(self) -> None:
        self.assertEqual(_analytics(query={ANALYTICS_QUERY: "visitors"})["active_tab"],
                         "visitors")
        self.assertEqual(_analytics(query={ANALYTICS_QUERY: "nonsense"})["active_tab"],
                         "overview")

    def test_it_is_not_the_parents(self) -> None:
        from micyte.tools.pim_overview import TAB_QUERY
        self.assertNotEqual(ANALYTICS_QUERY, TAB_QUERY)


class FiguresAreSaidInWords(unittest.TestCase):
    def test_a_period_reads_as_a_month(self) -> None:
        """A chart axis reading "7/26" makes the reader do arithmetic to find last month."""
        self.assertEqual(_month_label("2026-07"), "Jul")
        self.assertEqual(_month_label("2026-07", long=True), "Jul 2026")
        self.assertEqual(_month_label("garbage"), "garbage")

    def test_a_duration_reads_as_a_duration(self) -> None:
        self.assertEqual(_seconds(5775), "6s")
        self.assertEqual(_seconds(125000), "2m 5s")
        self.assertEqual(_seconds(0), "—")

    def test_machine_keys_are_translated(self) -> None:
        self.assertEqual(_pretty("human"), "People")
        self.assertEqual(_pretty("bot"), "Machines")
        self.assertEqual(_pretty("direct"), "Typed or bookmarked")


if __name__ == "__main__":
    unittest.main()
