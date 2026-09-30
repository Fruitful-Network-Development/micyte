"""Pure leaflet-model merge semantics."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from micyte.core.analytics import leaflet_model as lm


def _raw(occurred, **kw):
    base = {
        "event_id": "evt-" + occurred,
        "received_at_utc": occurred,
        "visitor_cookie_id_hash": "cookieA",
        "session_id": "s1",
        "event_type": "page_view",
        "occurred_at_utc": occurred,
        "page_path": "/",
        "referrer_domain": "",
        "active_time_ms": 0,
        "visible_time_ms": 0,
        "scroll_depth_percent": 0,
        "is_bot": False,
        "bot_class": "",
        "bot_evidence": [],
        "ip_prefix": "10.0.0.0/24",
    }
    base.update(kw)
    return base


def _month():
    return lm.empty_month(entity="e", domain="d.test", period="2026-06", generated_at="")


class LeafletModelTests(unittest.TestCase):
    def test_two_page_views_one_session(self):
        m = _month()
        lm.merge_event(m, _raw("2026-06-01T09:00:00+00:00", page_path="/"))
        lm.merge_event(m, _raw("2026-06-01T09:01:00+00:00", page_path="/services",
                               event_id="evt-2"))
        self.assertEqual(len(m["visitors"]), 1)
        s = m["visitors"][0]["sessions"][0]
        self.assertEqual(len(s["events"]), 2)
        self.assertEqual(s["session_summary"]["page_view_count"], 2)
        self.assertEqual(s["session_summary"]["entry_page"], "/")
        self.assertEqual(s["session_summary"]["exit_page"], "/services")
        self.assertFalse(s["session_summary"]["is_bounce"])

    def test_heartbeat_folds_into_page_view(self):
        m = _month()
        lm.merge_event(m, _raw("2026-06-01T09:00:00+00:00", page_path="/"))
        lm.merge_event(m, _raw("2026-06-01T09:00:15+00:00", page_path="/",
                               event_type="heartbeat", active_time_ms=15000,
                               scroll_depth_percent=70, event_id="hb1"))
        s = m["visitors"][0]["sessions"][0]
        self.assertEqual(len(s["events"]), 1)  # heartbeat folded, not stored
        self.assertEqual(s["events"][0]["active_time_ms"], 15000)
        self.assertEqual(s["events"][0]["scroll_depth_percent"], 70)
        self.assertEqual(s["session_summary"]["active_time_ms"], 15000)

    def test_heartbeats_use_max_not_sum(self):
        # The collector posts CUMULATIVE active time each heartbeat; folding must
        # keep the max, not sum the snapshots (which would 3x a 45s visit).
        m = _month()
        lm.merge_event(m, _raw("2026-06-01T09:00:00+00:00", page_path="/"))
        for i, ms in enumerate((15000, 30000, 45000), start=1):
            lm.merge_event(m, _raw("2026-06-01T09:00:00+00:00", page_path="/",
                                   event_type="heartbeat", active_time_ms=ms,
                                   event_id=f"hb{i}"))
        ev = m["visitors"][0]["sessions"][0]["events"][0]
        self.assertEqual(ev["active_time_ms"], 45000)
        self.assertEqual(m["visitors"][0]["sessions"][0]["session_summary"]["active_time_ms"], 45000)

    def test_ops_probe_is_stored(self):
        m = _month()
        lm.merge_event(m, _raw("2026-06-01T09:00:00+00:00", event_type="ops_probe"))
        self.assertEqual(len(m["visitors"][0]["sessions"][0]["events"]), 1)
        self.assertEqual(m["visitors"][0]["sessions"][0]["events"][0]["event_type"], "ops_probe")

    def test_form_submit_is_conversion(self):
        m = _month()
        lm.merge_event(m, _raw("2026-06-01T09:00:00+00:00", page_path="/contact",
                               event_type="form_submit", action="contact_form_submit"))
        s = m["visitors"][0]["sessions"][0]
        self.assertTrue(s["session_summary"]["converted"])
        self.assertIn("contact_form_submit", s["session_summary"]["actions"])

    def test_abandoned_intent(self):
        m = _month()
        lm.merge_event(m, _raw("2026-06-01T09:00:00+00:00", page_path="/pricing",
                               active_time_ms=70000))
        s = m["visitors"][0]["sessions"][0]
        self.assertTrue(s["session_summary"]["high_intent"])
        self.assertTrue(s["session_summary"]["abandoned_intent"])
        self.assertFalse(s["session_summary"]["converted"])

    def test_bot_assessment(self):
        m = _month()
        lm.merge_event(m, _raw("2026-06-01T09:00:00+00:00", is_bot=True,
                               bot_class="scraper", bot_evidence=["ua_scrapy"]))
        ctx = m["visitors"][0]["visitor_context"]
        self.assertTrue(ctx["bot_assessment"]["is_bot"])
        self.assertEqual(ctx["bot_assessment"]["bot_class"], "scraper")
        self.assertIn("ua_flagged_bot", ctx["flags"])

    def test_multi_prefix_flag(self):
        m = _month()
        lm.merge_event(m, _raw("2026-06-01T09:00:00+00:00", ip_prefix="10.0.0.0/24"))
        lm.merge_event(m, _raw("2026-06-01T09:05:00+00:00", ip_prefix="172.16.0.0/24",
                               event_id="evt-2"))
        self.assertIn("multi_prefix", m["visitors"][0]["visitor_context"]["flags"])

    def test_finalize_sorts_and_renumbers(self):
        m = _month()
        lm.merge_event(m, _raw("2026-06-02T09:00:00+00:00", visitor_cookie_id_hash="late"))
        lm.merge_event(m, _raw("2026-06-01T09:00:00+00:00", visitor_cookie_id_hash="early",
                               event_id="evt-2"))
        lm.finalize_month(m, generated_at="2026-07-01T00:00:00+00:00")
        self.assertEqual(m["visitors"][0]["visitor_cookie_id_hash"], "early")
        self.assertEqual(m["visitors"][0]["visitor_record_id"], "visitor_0001")
        self.assertEqual(m["visitors"][1]["visitor_record_id"], "visitor_0002")
        self.assertEqual(m["generated_at"], "2026-07-01T00:00:00+00:00")

    def test_link_prior_month(self):
        prior = _month()
        prior["period"] = "2026-05"
        lm.merge_event(prior, _raw("2026-05-20T09:00:00+00:00", visitor_cookie_id_hash="cookieA"))
        cur = _month()
        lm.merge_event(cur, _raw("2026-06-01T09:00:00+00:00", visitor_cookie_id_hash="cookieA"))
        lm.merge_event(cur, _raw("2026-06-01T09:00:00+00:00", visitor_cookie_id_hash="fresh",
                                 event_id="evt-2"))
        lm.link_prior_month(cur, prior)
        by_cookie = {v["visitor_cookie_id_hash"]: v for v in cur["visitors"]}
        self.assertTrue(by_cookie["cookieA"]["returning_from_prior_month"])
        self.assertEqual(by_cookie["cookieA"]["prior_period"], "2026-05")
        self.assertFalse(by_cookie["fresh"]["returning_from_prior_month"])

    def test_flatten_round_trip(self):
        m = _month()
        lm.merge_event(m, _raw("2026-06-01T09:00:00+00:00", page_path="/"))
        lm.merge_event(m, _raw("2026-06-01T09:01:00+00:00", page_path="/x", event_id="evt-2"))
        flat = lm.flatten_events(m)
        self.assertEqual(len(flat), 2)
        self.assertEqual(flat[0]["visitor_cookie_id_hash"], "cookieA")
        self.assertIn("occurred_at_utc", flat[0])

    def test_referral_fields_flow_through(self):
        # B arrives via A's shared link: ?fnd_ref=A. B's own share id is recorded;
        # B's session is attributed to A via routed_from.referred_by.
        m = _month()
        lm.merge_event(m, _raw("2026-06-01T09:00:00+00:00", visitor_cookie_id_hash="B",
                               share_id="sid_B", referred_by="sid_A"))
        v = m["visitors"][0]
        self.assertEqual(v["visitor_context"]["share_id"], "sid_B")
        self.assertEqual(v["sessions"][0]["routed_from"]["referred_by"], "sid_A")
        flat = lm.flatten_events(m)
        self.assertEqual(flat[0]["referred_by"], "sid_A")
        self.assertEqual(flat[0]["share_id"], "sid_B")

    def test_intent_match_is_segment_bounded(self):
        # /contact-list must NOT count as the /contact intent page (substring trap).
        m = _month()
        lm.merge_event(m, _raw("2026-06-01T09:00:00+00:00", page_path="/contact-list",
                               active_time_ms=70000))
        self.assertFalse(m["visitors"][0]["sessions"][0]["session_summary"]["abandoned_intent"])
        # /contact itself DOES count.
        m2 = _month()
        lm.merge_event(m2, _raw("2026-06-01T09:00:00+00:00", page_path="/contact",
                                active_time_ms=70000))
        self.assertTrue(m2["visitors"][0]["sessions"][0]["session_summary"]["abandoned_intent"])

    def test_stored_event_dedup(self):
        # A duplicate stored event (same event_id, or same occurred_at+type+path)
        # is not double-appended (retry / cross-worker double-POST).
        m = _month()
        e = _raw("2026-06-01T09:00:00+00:00", event_type="form_submit",
                 action="contact_form_submit", event_id="evt-dup")
        lm.merge_event(m, e)
        lm.merge_event(m, dict(e))  # exact replay
        lm.merge_event(m, _raw("2026-06-01T09:00:00+00:00", event_type="form_submit",
                               action="contact_form_submit", event_id="other-id"))  # same occ+type+path
        events = m["visitors"][0]["sessions"][0]["events"]
        self.assertEqual(len(events), 1)

    def test_missing_cookie_dropped(self):
        m = _month()
        lm.merge_event(m, _raw("2026-06-01T09:00:00+00:00", visitor_cookie_id_hash=""))
        self.assertEqual(len(m["visitors"]), 0)


if __name__ == "__main__":
    unittest.main()
