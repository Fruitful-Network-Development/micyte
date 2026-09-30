"""Phase 18a — RawEvent contract tests.

Pins the schema's invariants: required-field validation, the
client-stamped vs server-stamped split, salted-hash determinism +
salt-sensitivity, and the coarse IPv4/IPv6 prefix derivation.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from micyte.core.analytics import (
    EVENT_SCHEMA,
    RawEvent,
    coarse_ip_prefix,
    salted_hash,
)


def _minimal_body(**overrides):
    body = {
        "event_type": "page_view",
        "occurred_at_utc": "2026-05-16T00:00:00Z",
        "session_id": "sid-abc",
        "page_path": "/",
    }
    body.update(overrides)
    return body


def _build(**kwargs):
    base = dict(
        body=_minimal_body(),
        domain="example.test",
        site_id="fnd",
        environment="prod",
        visitor_cookie="cookie-xyz",
        remote_addr="192.0.2.10",
        user_agent="Mozilla/5.0",
        salt="salt-A",
        received_at_utc="2026-05-16T00:00:01Z",
    )
    base.update(kwargs)
    return RawEvent.from_request(**base)


class RequiredFieldValidationTests(unittest.TestCase):
    def test_missing_event_type_raises(self) -> None:
        with self.assertRaises(ValueError):
            _build(body={
                "occurred_at_utc": "2026-05-16T00:00:00Z",
                "session_id": "sid-abc",
                "page_path": "/",
            })

    def test_missing_session_id_raises(self) -> None:
        body = _minimal_body()
        body.pop("session_id")
        with self.assertRaises(ValueError):
            _build(body=body)

    def test_missing_page_path_raises(self) -> None:
        body = _minimal_body()
        body.pop("page_path")
        with self.assertRaises(ValueError):
            _build(body=body)

    def test_unknown_event_type_raises(self) -> None:
        with self.assertRaises(ValueError):
            _build(body=_minimal_body(event_type="nope"))


class ServerStampedFieldShapeTests(unittest.TestCase):
    def test_received_at_and_schema_pinned(self) -> None:
        event = _build()
        self.assertEqual(event.received_at_utc, "2026-05-16T00:00:01Z")
        d = event.to_dict()
        self.assertEqual(d["schema"], EVENT_SCHEMA)
        self.assertTrue(d["event_id"])
        self.assertEqual(d["domain"], "example.test")

    def test_client_stamped_fields_preserved(self) -> None:
        event = _build(body=_minimal_body(
            event_type="form_submit",
            page_title="Contact",
            referrer_url="https://google.com/?q=fnd",
            referrer_domain="google.com",
            scroll_depth_percent=75,
            properties={"form_id": "contact-form"},
        ))
        d = event.to_dict()
        self.assertEqual(d["event_type"], "form_submit")
        self.assertEqual(d["page_title"], "Contact")
        self.assertEqual(d["referrer_domain"], "google.com")
        self.assertEqual(d["scroll_depth_percent"], 75)
        self.assertEqual(d["properties"], {"form_id": "contact-form"})


class SaltedHashTests(unittest.TestCase):
    def test_deterministic_per_salt(self) -> None:
        a = salted_hash("cookie-xyz", salt="salt-A")
        b = salted_hash("cookie-xyz", salt="salt-A")
        self.assertEqual(a, b)
        self.assertEqual(len(a), 64)

    def test_different_salts_diverge(self) -> None:
        a = salted_hash("cookie-xyz", salt="salt-A")
        b = salted_hash("cookie-xyz", salt="salt-B")
        self.assertNotEqual(a, b)

    def test_empty_input_returns_empty(self) -> None:
        self.assertEqual(salted_hash("", salt="anything"), "")

    def test_event_visitor_hash_is_deterministic(self) -> None:
        e1 = _build()
        e2 = _build()
        self.assertEqual(e1.visitor_cookie_id_hash, e2.visitor_cookie_id_hash)


class IpPrefixTests(unittest.TestCase):
    def test_ipv4_prefix_is_slash_24(self) -> None:
        self.assertEqual(coarse_ip_prefix("192.0.2.10"), "192.0.2.0/24")
        self.assertEqual(coarse_ip_prefix("203.0.113.255"), "203.0.113.0/24")

    def test_ipv6_prefix_is_slash_48(self) -> None:
        self.assertEqual(
            coarse_ip_prefix("2001:db8:abcd:0012::1"),
            "2001:db8:abcd::/48",
        )

    def test_unrecognised_input_empty(self) -> None:
        self.assertEqual(coarse_ip_prefix(""), "")
        self.assertEqual(coarse_ip_prefix("not-an-ip"), "")


class PropertiesBoundTests(unittest.TestCase):
    def test_oversized_properties_dropped(self) -> None:
        # 4KB cap — try 8KB of payload.
        huge = {"blob": "x" * 8192}
        event = _build(body=_minimal_body(properties=huge))
        self.assertEqual(event.properties, {})

    def test_nondict_properties_dropped(self) -> None:
        event = _build(body=_minimal_body(properties="not-a-dict"))
        self.assertEqual(event.properties, {})


if __name__ == "__main__":
    unittest.main()
