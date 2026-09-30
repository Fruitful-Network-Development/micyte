"""Phase 18c — analytics derivations tests.

Each derivation is a pure function: a list of event dicts in, a
JSON-serializable summary out. Tests assemble small synthetic
event lists + assert the expected output.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from micyte.core.analytics import derivations


def _event(**overrides):
    base = {
        "event_type": "page_view",
        "occurred_at_utc": "2026-05-01T00:00:00Z",
        "session_id": "sid-1",
        "page_path": "/",
        "visitor_cookie_id_hash": "visitor-a",
        "is_bot": False,
        "active_time_ms": 0,
        "scroll_depth_percent": 0,
        "referrer_domain": "",
    }
    base.update(overrides)
    return base


class ClassifyOriginTests(unittest.TestCase):
    def test_empty_referrer_is_direct(self) -> None:
        self.assertEqual(derivations.classify_origin("", ""), "direct")

    def test_google_is_search(self) -> None:
        self.assertEqual(derivations.classify_origin("www.google.com", ""), "search")

    def test_facebook_is_social(self) -> None:
        self.assertEqual(derivations.classify_origin("facebook.com", ""), "social")

    def test_utm_newsletter_is_email(self) -> None:
        self.assertEqual(derivations.classify_origin("", "newsletter"), "email")

    def test_paid_utm_is_paid(self) -> None:
        self.assertEqual(derivations.classify_origin("", "google"), "paid")

    def test_unknown_referrer_is_referral(self) -> None:
        self.assertEqual(
            derivations.classify_origin("medium.com", ""), "referral"
        )


class FilterBotsTests(unittest.TestCase):
    def test_splits_humans_and_bots(self) -> None:
        events = [
            _event(visitor_cookie_id_hash="a"),
            _event(visitor_cookie_id_hash="b", is_bot=True),
        ]
        humans, bots = derivations.filter_bots(events)
        self.assertEqual(len(humans), 1)
        self.assertEqual(len(bots), 1)


class ReconstructVisitorTimelineTests(unittest.TestCase):
    def test_returns_visitor_events_ordered(self) -> None:
        events = [
            _event(occurred_at_utc="2026-05-01T00:00:03Z", page_path="/c", visitor_cookie_id_hash="a"),
            _event(occurred_at_utc="2026-05-01T00:00:01Z", page_path="/a", visitor_cookie_id_hash="a"),
            _event(occurred_at_utc="2026-05-01T00:00:02Z", page_path="/b", visitor_cookie_id_hash="b"),
        ]
        timeline = derivations.reconstruct_visitor_timeline(
            events, visitor_cookie_id_hash="a"
        )
        self.assertEqual([e["page_path"] for e in timeline], ["/a", "/c"])


class SessionizeTests(unittest.TestCase):
    def test_groups_within_inactivity_gap(self) -> None:
        events = [
            _event(occurred_at_utc="2026-05-01T00:00:00Z", page_path="/"),
            _event(occurred_at_utc="2026-05-01T00:05:00Z", page_path="/about"),
            # 31 minutes later — new session.
            _event(occurred_at_utc="2026-05-01T00:36:00Z", page_path="/contact"),
        ]
        sessions = derivations.sessionize(events)
        self.assertEqual(len(sessions), 2)
        self.assertEqual(sessions[1]["page_view_count"], 2)
        self.assertEqual(sessions[0]["page_view_count"], 1)

    def test_session_id_change_starts_new_session(self) -> None:
        events = [
            _event(session_id="sid-1", page_path="/"),
            _event(session_id="sid-2", page_path="/about"),
        ]
        self.assertEqual(len(derivations.sessionize(events)), 2)

    def test_bot_flag_propagates(self) -> None:
        events = [_event(is_bot=True), _event(is_bot=True)]
        sessions = derivations.sessionize(events)
        self.assertTrue(sessions[0]["is_bot"])


class CountVisitorsTests(unittest.TestCase):
    def test_excludes_bots_by_default(self) -> None:
        events = [
            _event(visitor_cookie_id_hash="a"),
            _event(visitor_cookie_id_hash="b", is_bot=True),
            _event(visitor_cookie_id_hash="c"),
        ]
        self.assertEqual(derivations.count_visitors(events), 2)

    def test_includes_bots_when_requested(self) -> None:
        events = [
            _event(visitor_cookie_id_hash="a"),
            _event(visitor_cookie_id_hash="b", is_bot=True),
        ]
        self.assertEqual(derivations.count_visitors(events, include_bots=True), 2)


class CountRepeatVisitorsTests(unittest.TestCase):
    def test_counts_visitors_with_multiple_sessions(self) -> None:
        sessions = [
            {"visitor_cookie_id_hash": "a", "is_bot": False},
            {"visitor_cookie_id_hash": "a", "is_bot": False},
            {"visitor_cookie_id_hash": "b", "is_bot": False},
        ]
        self.assertEqual(derivations.count_repeat_visitors(sessions), 1)


class RankPagesByAttentionTests(unittest.TestCase):
    def test_orders_by_view_count(self) -> None:
        events = [
            _event(page_path="/", active_time_ms=1000, scroll_depth_percent=50),
            _event(page_path="/", visitor_cookie_id_hash="b"),
            _event(page_path="/about"),
        ]
        rows = derivations.rank_pages_by_attention(events)
        self.assertEqual(rows[0]["page_path"], "/")
        self.assertEqual(rows[0]["view_count"], 2)
        self.assertEqual(rows[0]["unique_visitors"], 2)
        self.assertEqual(rows[0]["scroll_depth_average"], 50)


class RankReferrersTests(unittest.TestCase):
    def test_counts_sessions_per_referrer(self) -> None:
        events = [
            _event(session_id="sid-1", referrer_domain="google.com"),
            _event(session_id="sid-1", referrer_domain="google.com", page_path="/a"),
            _event(session_id="sid-2", visitor_cookie_id_hash="b", referrer_domain="bing.com"),
        ]
        rows = derivations.rank_referrers(events)
        by_ref = {r["referrer_domain"]: r for r in rows}
        self.assertEqual(by_ref["google.com"]["sessions"], 1)
        self.assertEqual(by_ref["bing.com"]["sessions"], 1)


class FindCommonPathsTests(unittest.TestCase):
    def test_extracts_path_sequences(self) -> None:
        events = [
            _event(session_id="sid-1", page_path="/"),
            _event(session_id="sid-1", page_path="/services"),
            _event(session_id="sid-1", page_path="/contact"),
            _event(session_id="sid-2", visitor_cookie_id_hash="b", page_path="/"),
            _event(session_id="sid-2", visitor_cookie_id_hash="b", page_path="/services"),
        ]
        rows = derivations.find_common_paths(events, min_length=2, top_k=5)
        paths = {tuple(r["path"]): r["count"] for r in rows}
        self.assertEqual(paths[("/", "/services")], 2)
        self.assertEqual(paths[("/services", "/contact")], 1)


class HighIntentSessionsTests(unittest.TestCase):
    def test_filters_by_intent_page_and_active_time(self) -> None:
        sessions = [
            {
                "visitor_cookie_id_hash": "a",
                "is_bot": False,
                "active_time_ms": 90_000,
                "entry_page": "/",
                "exit_page": "/contact",
            },
            {
                "visitor_cookie_id_hash": "b",
                "is_bot": False,
                "active_time_ms": 10_000,  # too short
                "entry_page": "/",
                "exit_page": "/contact",
            },
            {
                "visitor_cookie_id_hash": "c",
                "is_bot": False,
                "active_time_ms": 90_000,
                "entry_page": "/",
                "exit_page": "/about",  # no intent page
            },
        ]
        out = derivations.high_intent_sessions(sessions)
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0]["visitor_cookie_id_hash"], "a")


class DetectVpnGeoJumpsTests(unittest.TestCase):
    def test_flags_visitor_with_multiple_ip_prefixes(self) -> None:
        events = [
            _event(visitor_cookie_id_hash="a"),
            _event(visitor_cookie_id_hash="a", page_path="/about"),
        ]
        # Patch in different ip_prefix on each event.
        events[0]["ip_prefix"] = "192.0.2.0/24"
        events[1]["ip_prefix"] = "203.0.113.0/24"
        flagged = derivations.detect_vpn_geo_jumps(events)
        self.assertEqual(len(flagged), 1)
        self.assertEqual(flagged[0]["visitor_cookie_id_hash"], "a")
        self.assertEqual(
            flagged[0]["ip_prefixes"], ["192.0.2.0/24", "203.0.113.0/24"]
        )

    def test_does_not_flag_single_prefix(self) -> None:
        events = [_event() for _ in range(5)]
        for e in events:
            e["ip_prefix"] = "192.0.2.0/24"
        self.assertEqual(derivations.detect_vpn_geo_jumps(events), [])


class TopEntryExitTests(unittest.TestCase):
    def test_top_entry_counts_session_entries(self) -> None:
        sessions = [
            {"entry_page": "/", "exit_page": "/a", "is_bot": False},
            {"entry_page": "/", "exit_page": "/b", "is_bot": False},
            {"entry_page": "/about", "exit_page": "/", "is_bot": False},
        ]
        rows = derivations.top_entry_pages(sessions)
        self.assertEqual(rows[0]["page_path"], "/")
        self.assertEqual(rows[0]["count"], 2)

    def test_top_exit_counts_session_exits(self) -> None:
        sessions = [
            {"entry_page": "/", "exit_page": "/contact", "is_bot": False},
            {"entry_page": "/about", "exit_page": "/contact", "is_bot": False},
        ]
        rows = derivations.top_exit_pages(sessions)
        self.assertEqual(rows[0]["page_path"], "/contact")
        self.assertEqual(rows[0]["count"], 2)


class VisitorSummaryTests(unittest.TestCase):
    def test_unknown_visitor_returns_zero_shape(self) -> None:
        result = derivations.visitor_summary([_event()], "ghost")
        self.assertEqual(result["visit_count"], 0)
        self.assertEqual(result["total_events"], 0)
        self.assertEqual(result["bot_status"], "unknown")

    def test_aggregates_full_visitor(self) -> None:
        events = [
            _event(
                session_id="s1",
                page_path="/",
                occurred_at_utc="2026-05-01T00:00:00Z",
                active_time_ms=2000,
                ip_prefix="192.0.2.0/24",
                device_type="desktop",
                referrer_domain="google.com",
            ),
            _event(
                session_id="s1",
                page_path="/pricing",
                occurred_at_utc="2026-05-01T00:01:00Z",
                active_time_ms=5000,
                ip_prefix="192.0.2.0/24",
                device_type="desktop",
            ),
            _event(
                event_type="form_submit",
                session_id="s2",
                page_path="/contact",
                occurred_at_utc="2026-05-02T00:00:00Z",
                active_time_ms=0,
                ip_prefix="198.51.100.0/24",
                device_type="mobile",
            ),
        ]
        result = derivations.visitor_summary(events, "visitor-a")
        self.assertEqual(result["session_count"], 2)
        self.assertEqual(result["total_events"], 3)
        self.assertEqual(result["total_active_time_ms"], 7000)
        self.assertEqual(result["first_landing_page"], "/")
        self.assertEqual(result["last_seen_page"], "/contact")
        self.assertEqual(result["conversion_count"], 1)
        self.assertEqual(result["bot_status"], "human")
        self.assertEqual(result["vpn_or_geo_jump_status"], "multi_prefix")


class VisitorInterestProfileTests(unittest.TestCase):
    def test_categorises_pages(self) -> None:
        events = [
            _event(page_path="/", visitor_cookie_id_hash="v"),
            _event(page_path="/services", visitor_cookie_id_hash="v"),
            _event(page_path="/pricing", visitor_cookie_id_hash="v"),
            _event(page_path="/contact", visitor_cookie_id_hash="v"),
        ]
        result = derivations.visitor_interest_profile(events, "v")
        self.assertEqual(result["total_page_views"], 4)
        self.assertIn("pricing", result["categories"])
        self.assertEqual(result["intent_tier"], "high")

    def test_browsing_tier_when_only_home(self) -> None:
        events = [
            _event(page_path="/", visitor_cookie_id_hash="v"),
            _event(page_path="/blog/x", visitor_cookie_id_hash="v"),
        ]
        result = derivations.visitor_interest_profile(events, "v")
        self.assertEqual(result["intent_tier"], "browsing")


class AbandonedIntentSessionsTests(unittest.TestCase):
    def test_flags_intent_without_conversion(self) -> None:
        sessions = [
            {
                "visitor_cookie_id_hash": "v",
                "session_id": "s1",
                "started_at_utc": "2026-05-01T00:00:00Z",
                "entry_page": "/",
                "exit_page": "/pricing",
                "active_time_ms": 30_000,
                "duration_ms": 60_000,
                "event_types": ["page_view"],
                "is_bot": False,
            },
        ]
        out = derivations.abandoned_intent_sessions(sessions)
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0]["exit_page"], "/pricing")
        self.assertIn("/pricing", out[0]["visited_intent_pages"])

    def test_skips_converted_session(self) -> None:
        sessions = [
            {
                "visitor_cookie_id_hash": "v",
                "session_id": "s1",
                "entry_page": "/",
                "exit_page": "/contact",
                "active_time_ms": 30_000,
                "event_types": ["page_view", "form_submit"],
                "is_bot": False,
            },
        ]
        self.assertEqual(derivations.abandoned_intent_sessions(sessions), [])


class DeadEndPagesTests(unittest.TestCase):
    def test_flags_high_single_page_session_rate(self) -> None:
        sessions = (
            [
                {
                    "entry_page": "/dead",
                    "exit_page": "/dead",
                    "active_time_ms": 1000,
                    "is_bot": False,
                }
            ]
            * 5
        )
        rows = derivations.dead_end_pages(sessions, min_entries=5, single_page_rate_threshold=0.6)
        self.assertEqual(rows[0]["page_path"], "/dead")
        self.assertEqual(rows[0]["single_page_session_rate"], 1.0)

    def test_ignores_low_volume_entries(self) -> None:
        sessions = [
            {
                "entry_page": "/rare",
                "exit_page": "/rare",
                "active_time_ms": 0,
                "is_bot": False,
            }
        ]
        self.assertEqual(derivations.dead_end_pages(sessions, min_entries=5), [])


class ConversionAssistingPagesTests(unittest.TestCase):
    def test_counts_pages_before_conversion(self) -> None:
        events = [
            _event(
                visitor_cookie_id_hash="v",
                session_id="s1",
                page_path="/",
                occurred_at_utc="2026-05-01T00:00:00Z",
            ),
            _event(
                visitor_cookie_id_hash="v",
                session_id="s1",
                page_path="/services",
                occurred_at_utc="2026-05-01T00:01:00Z",
            ),
            _event(
                visitor_cookie_id_hash="v",
                session_id="s1",
                page_path="/contact",
                occurred_at_utc="2026-05-01T00:02:00Z",
            ),
            _event(
                visitor_cookie_id_hash="v",
                session_id="s1",
                event_type="form_submit",
                page_path="/contact",
                occurred_at_utc="2026-05-01T00:03:00Z",
            ),
        ]
        rows = derivations.conversion_assisting_pages(events)
        paths = {r["page_path"] for r in rows}
        self.assertIn("/services", paths)
        self.assertIn("/", paths)
        self.assertIn("/contact", paths)


class TrafficOriginClassificationTests(unittest.TestCase):
    def test_buckets_by_origin(self) -> None:
        events = [
            _event(
                visitor_cookie_id_hash="v1",
                session_id="s1",
                referrer_domain="google.com",
                active_time_ms=3000,
            ),
            _event(
                visitor_cookie_id_hash="v2",
                session_id="s2",
                referrer_domain="",
                active_time_ms=1000,
            ),
            _event(
                visitor_cookie_id_hash="v3",
                session_id="s3",
                referrer_domain="facebook.com",
                active_time_ms=2000,
            ),
        ]
        result = derivations.traffic_origin_classification(events)
        self.assertEqual(result["search"]["sessions"], 1)
        self.assertEqual(result["direct"]["sessions"], 1)
        self.assertEqual(result["social"]["sessions"], 1)


if __name__ == "__main__":
    unittest.main()
