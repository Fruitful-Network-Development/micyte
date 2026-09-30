"""Direct tests for compute_quality_flags + _iso_to_epoch_ms.

The flag computation is exercised indirectly via RawEvent.from_request
in test_analytics_event_schema.py, but each evidence-token branch
deserves a focused test so future refactors can't silently break one
path while the others keep passing.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from micyte.core.analytics.event_schema import (
    _iso_to_epoch_ms,
    compute_quality_flags,
)


class IsoToEpochMsTests(unittest.TestCase):
    def test_empty_string_returns_none(self) -> None:
        self.assertIsNone(_iso_to_epoch_ms(""))

    def test_unparseable_returns_none(self) -> None:
        self.assertIsNone(_iso_to_epoch_ms("not-a-date"))

    def test_genuine_epoch_zero_returns_zero(self) -> None:
        self.assertEqual(_iso_to_epoch_ms("1970-01-01T00:00:00Z"), 0)

    def test_z_suffix_normalised(self) -> None:
        self.assertEqual(
            _iso_to_epoch_ms("2026-05-22T12:00:00Z"),
            _iso_to_epoch_ms("2026-05-22T12:00:00+00:00"),
        )


def _body(**overrides):
    base = {
        "event_type": "page_view",
        "occurred_at_utc": "2026-05-22T12:00:00Z",
        "session_id": "sid-1",
        "page_path": "/",
    }
    base.update(overrides)
    return base


class ComputeQualityFlagsTests(unittest.TestCase):
    def test_clean_event_yields_no_flags(self) -> None:
        flags = compute_quality_flags(
            _body(),
            received_at_utc="2026-05-22T12:00:00Z",
            visitor_cookie_id_hash="hashA",
        )
        self.assertEqual(flags, ())

    def test_clock_skew_fires_when_offset_exceeds_60s(self) -> None:
        flags = compute_quality_flags(
            _body(occurred_at_utc="2026-05-22T11:00:00Z"),
            received_at_utc="2026-05-22T12:00:00Z",
            visitor_cookie_id_hash="hashA",
        )
        self.assertIn("clock_skew", flags)

    def test_clock_skew_silent_when_parse_failure(self) -> None:
        # _iso_to_epoch_ms returns None for "garbage" — the new guard
        # treats that as "no evidence", not as 0-epoch.
        flags = compute_quality_flags(
            _body(occurred_at_utc="garbage"),
            received_at_utc="2026-05-22T12:00:00Z",
            visitor_cookie_id_hash="hashA",
        )
        self.assertNotIn("clock_skew", flags)

    def test_clock_skew_silent_for_genuine_epoch_zero(self) -> None:
        # Distinct from the parse-failure case: both timestamps parse,
        # but received_at is also a sentinel (e.g. recovery scenario).
        # The guard still skips since the diff is below threshold for
        # like-timestamps; in any case it doesn't crash.
        flags = compute_quality_flags(
            _body(occurred_at_utc="1970-01-01T00:00:00Z"),
            received_at_utc="1970-01-01T00:00:00Z",
            visitor_cookie_id_hash="hashA",
        )
        self.assertNotIn("clock_skew", flags)

    def test_no_referrer_parse_fires(self) -> None:
        flags = compute_quality_flags(
            _body(referrer_url="https://google.com/q?x=1", referrer_domain=""),
            received_at_utc="2026-05-22T12:00:00Z",
            visitor_cookie_id_hash="hashA",
        )
        self.assertIn("no_referrer_parse", flags)

    def test_malformed_url_fires(self) -> None:
        flags = compute_quality_flags(
            _body(page_url="not a url"),
            received_at_utc="2026-05-22T12:00:00Z",
            visitor_cookie_id_hash="hashA",
        )
        self.assertIn("malformed_url", flags)

    def test_well_formed_url_does_not_fire(self) -> None:
        flags = compute_quality_flags(
            _body(page_url="https://example.com/path"),
            received_at_utc="2026-05-22T12:00:00Z",
            visitor_cookie_id_hash="hashA",
        )
        self.assertNotIn("malformed_url", flags)

    def test_zero_active_time_on_heartbeat_navigation(self) -> None:
        flags = compute_quality_flags(
            _body(
                event_type="heartbeat",
                active_time_ms=0,
                previous_page_path="/",
                page_path="/about",
            ),
            received_at_utc="2026-05-22T12:00:00Z",
            visitor_cookie_id_hash="hashA",
        )
        self.assertIn("zero_active_time_with_navigation", flags)

    def test_zero_active_time_on_page_view_navigation(self) -> None:
        # Widening per the 2026-05 review: page_view events with the
        # same pathology should also fire the flag.
        flags = compute_quality_flags(
            _body(
                event_type="page_view",
                active_time_ms=0,
                previous_page_path="/",
                page_path="/about",
            ),
            received_at_utc="2026-05-22T12:00:00Z",
            visitor_cookie_id_hash="hashA",
        )
        self.assertIn("zero_active_time_with_navigation", flags)

    def test_missing_identifier_fires_when_hash_empty(self) -> None:
        flags = compute_quality_flags(
            _body(),
            received_at_utc="2026-05-22T12:00:00Z",
            visitor_cookie_id_hash="",
        )
        self.assertIn("missing_identifier", flags)


if __name__ == "__main__":
    unittest.main()
