"""Canonical raw-event contract for the analytics log.

A row in the NDJSON log is one observed event. The schema is split
into two layers:

  * **Client-stamped** fields (occurred_at_utc, event_type, page_path,
    session_id, etc.) — supplied by the browser via
    ``POST /__fnd/analytics/event``.
  * **Server-stamped** fields (received_at_utc,
    visitor_cookie_id_hash, ip_hash, ip_prefix, is_bot, bot_class,
    bot_evidence, schema_version, collector_version, domain,
    event_id) — derived inside the route from the request +
    cookies + IP + UA.

No "insights" are persisted here — bot_class is *evidence* (UA
regex match), not a *conclusion* about whether the visitor is real.
"""

from __future__ import annotations

import hashlib
import secrets
import time
from dataclasses import dataclass, field
from typing import Any

EVENT_SCHEMA = "mycite.v2.analytics.event.v3"
COLLECTOR_VERSION = "fnd-analytics/3.0"

CLOCK_SKEW_TOLERANCE_MS = 60_000

KNOWN_EVENT_TYPES = frozenset(
    {
        "page_view",
        "click",
        "scroll",
        "heartbeat",
        "form_submit",
        "outbound_click",
        "download",
        "error",
        "ops_probe",
    }
)

# Standardized interaction *action* vocabulary. event_type stays coarse
# (click / form_submit / …); ``action`` names the semantic interaction so the
# same token means the same thing across every site regardless of how a button
# or link is styled. The collector (analytics.js) auto-detects most of these
# (mailto:→email_click, tel:→phone_click, file ext→download_file, outbound
# link→outbound_click, newsletter vs contact form by id) and honors an explicit
# ``data-fnd-action="…"`` attribute for the rest. An unknown value is dropped to
# "" at write time so the field is always trustworthy.
STANDARD_ACTIONS = frozenset(
    {
        "contact_form_submit",
        "email_click",
        "phone_click",
        "booking_click",
        "checkout_start",
        "checkout_complete",
        "download_file",
        "outbound_click",
        "newsletter_signup",
    }
)

# The smallest fact-set that makes an event row meaningful. Everything
# else is optional and falls back to empty strings / zero / None.
REQUIRED_EVENT_FIELDS = ("event_type", "occurred_at_utc", "session_id", "page_path")

# Bound the free-form ``properties`` JSON to defeat abuse / accidental
# unbounded blobs. Anything beyond this is dropped at write time.
MAX_PROPERTIES_BYTES = 4 * 1024
# Bound user-agent / referrer text the same way.
MAX_TEXT_FIELD_BYTES = 2 * 1024


def _as_text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _as_int(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _as_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return _as_text(value).lower() in {"true", "1", "yes"}


def _bounded(text: str, *, limit: int = MAX_TEXT_FIELD_BYTES) -> str:
    return text[:limit] if len(text) > limit else text


def salted_hash(value: str, *, salt: str) -> str:
    """Stable salted hash for visitor / IP identifiers.

    The salt is a per-instance secret held under
    ``<private>/utilities/tools/analytics/secret.txt`` so production
    hashes never collide with test fixtures and the raw cookie /
    IP values are never persistable from the digest.
    """
    if not _as_text(value):
        return ""
    digest = hashlib.sha256()
    digest.update((salt or "").encode("utf-8"))
    digest.update(b"::")
    digest.update(_as_text(value).encode("utf-8"))
    return digest.hexdigest()


def coarse_ip_prefix(ip: str) -> str:
    """Return a coarse IP-prefix token suitable for VPN / geo-jump
    heuristics. IPv4 → ``a.b.c.0/24``; IPv6 → first 3 hextets +
    ``::/48``. Empty / unrecognised input returns the empty string.
    """
    token = _as_text(ip)
    if not token:
        return ""
    if ":" in token:
        # IPv6 — keep the first 3 hextets, anonymise the rest.
        parts = token.split(":")
        head = ":".join(parts[:3])
        return f"{head}::/48"
    parts = token.split(".")
    if len(parts) != 4:
        return ""
    return f"{parts[0]}.{parts[1]}.{parts[2]}.0/24"


def _iso_to_epoch_ms(iso_string: str) -> int | None:
    """Best-effort ISO-8601 → epoch ms.

    Returns ``None`` when the input is empty or fails to parse — that
    way callers can distinguish a *genuine* epoch-zero timestamp
    (1970-01-01T00:00:00Z, which legitimately maps to 0 ms) from a
    parse failure. The two used to collapse onto 0, which silently
    broke the clock_skew quality flag.
    """
    token = _as_text(iso_string)
    if not token:
        return None
    try:
        from datetime import datetime as _dt

        token_normalised = token.replace("Z", "+00:00")
        return int(_dt.fromisoformat(token_normalised).timestamp() * 1000)
    except (ValueError, TypeError):
        return None


def compute_quality_flags(
    body: dict[str, Any],
    *,
    received_at_utc: str,
    visitor_cookie_id_hash: str,
) -> tuple[str, ...]:
    """Server-stamped evidence tokens describing the event row's
    quality. Each token names a *signal*, not a conclusion. See
    ``docs/contracts/analytics_event_schema.md`` for the full token
    glossary.
    """
    flags: list[str] = []

    occurred_ms = _iso_to_epoch_ms(_as_text(body.get("occurred_at_utc")))
    received_ms = _iso_to_epoch_ms(received_at_utc)
    if occurred_ms is not None and received_ms is not None:
        if abs(received_ms - occurred_ms) > CLOCK_SKEW_TOLERANCE_MS:
            flags.append("clock_skew")

    referrer_url = _as_text(body.get("referrer_url"))
    referrer_domain = _as_text(body.get("referrer_domain"))
    if referrer_url and not referrer_domain:
        flags.append("no_referrer_parse")

    page_url = _as_text(body.get("page_url"))
    if page_url:
        try:
            from urllib.parse import urlparse as _urlparse

            parsed = _urlparse(page_url)
            if not parsed.scheme or not parsed.netloc:
                flags.append("malformed_url")
        except Exception:
            flags.append("malformed_url")

    event_type = _as_text(body.get("event_type"))
    active = _as_int(body.get("active_time_ms"))
    previous_path = _as_text(body.get("previous_page_path"))
    page_path = _as_text(body.get("page_path"))
    if (
        event_type in {"heartbeat", "page_view"}
        and active == 0
        and previous_path
        and page_path
        and previous_path != page_path
    ):
        flags.append("zero_active_time_with_navigation")

    if not visitor_cookie_id_hash:
        flags.append("missing_identifier")

    return tuple(flags)


def _new_event_id() -> str:
    """ULID-shaped 26-char identifier. k-sortable by timestamp
    prefix so the NDJSON files stay roughly chronological even if a
    delayed event slips in.
    """
    millis = int(time.time() * 1000)
    rand = secrets.token_bytes(10)
    return f"{millis:012x}-{rand.hex()}"


@dataclass(frozen=True)
class RawEvent:
    """Raw event row. Field set is the entire factual schema; the
    derivation layer reads these without ever re-writing the row.
    """

    # Server-stamped
    event_id: str
    received_at_utc: str
    schema_version: str
    collector_version: str
    site_id: str
    domain: str
    environment: str
    visitor_cookie_id_hash: str
    ip_hash: str
    ip_prefix: str
    is_bot: bool
    bot_class: str
    bot_evidence: tuple[str, ...]

    # Client-stamped (required subset)
    event_type: str
    occurred_at_utc: str
    session_id: str
    page_path: str

    # Client-stamped (optional)
    event_name: str = ""
    event_index_in_session: int = 0
    page_query_hash: str = ""
    page_title: str = ""
    referrer_url: str = ""
    referrer_domain: str = ""
    origin_type: str = ""
    utm_source: str = ""
    utm_medium: str = ""
    utm_campaign: str = ""
    utm_content: str = ""
    utm_term: str = ""
    previous_page_path: str = ""
    time_since_previous_ms: int = 0
    active_time_ms: int = 0
    visible_time_ms: int = 0
    scroll_depth_percent: int = 0
    user_agent_raw: str = ""
    device_type: str = ""
    browser_name: str = ""
    viewport_width: int = 0
    viewport_height: int = 0
    language: str = ""
    do_not_track: bool = False
    properties: dict[str, Any] = field(default_factory=dict)

    # v3 additions
    page_url: str = ""
    os_name: str = ""
    quality_flags: tuple[str, ...] = ()

    # Standardized interaction action (one of STANDARD_ACTIONS, or "").
    action: str = ""

    # Campaign attribution: the ?fnd_c=<token> a pre-tracked link / QR carries.
    # Rides on the session's routed_from so every visit through that link is
    # attributed to the campaign (the visitor cookie still distinguishes people
    # who scanned the same QR). Resolved token→label at render time.
    campaign_token: str = ""

    # Per-visitor referral chain (A→B link sharing). ``share_id`` is the
    # visitor's own JS-readable fnd_sid; ``referred_by`` is the fnd_ref the
    # inbound link carried (the SHARER's share_id). Lets the dashboard trace
    # "B's visit came via A" even though A and B have different visitor cookies.
    share_id: str = ""
    referred_by: str = ""

    @classmethod
    def from_request(
        cls,
        body: dict[str, Any],
        *,
        domain: str,
        site_id: str,
        environment: str,
        visitor_cookie: str,
        remote_addr: str,
        user_agent: str,
        salt: str,
        received_at_utc: str,
    ) -> RawEvent:
        """Build a RawEvent from a request body + server context.

        Raises ``ValueError`` if any required field is missing or
        the event_type isn't in ``KNOWN_EVENT_TYPES``.
        """
        if not isinstance(body, dict):
            raise ValueError("analytics event body must be a JSON object")
        for key in REQUIRED_EVENT_FIELDS:
            if not _as_text(body.get(key)):
                raise ValueError(f"missing required field: {key}")
        event_type = _as_text(body.get("event_type"))
        if event_type not in KNOWN_EVENT_TYPES:
            raise ValueError(f"unknown event_type: {event_type!r}")

        # Lazy import: bot_detection lives next door but importing
        # at module top would create a cycle once derivations.py
        # consumes both.
        from .bot_detection import classify_user_agent

        is_bot, bot_class, bot_evidence = classify_user_agent(user_agent)

        action = _as_text(body.get("action"))
        if action not in STANDARD_ACTIONS:
            action = ""
        campaign_token = _bounded(_as_text(body.get("campaign_token")), limit=64)
        share_id = _bounded(_as_text(body.get("share_id")), limit=64)
        referred_by = _bounded(_as_text(body.get("referred_by")), limit=64)

        visitor_cookie_id_hash = salted_hash(visitor_cookie, salt=salt)
        quality_flags = compute_quality_flags(
            body,
            received_at_utc=received_at_utc,
            visitor_cookie_id_hash=visitor_cookie_id_hash,
        )

        properties_raw = body.get("properties")
        properties: dict[str, Any] = {}
        if isinstance(properties_raw, dict):
            # Cheap bound: serialised size <= MAX_PROPERTIES_BYTES.
            import json as _json

            raw = _json.dumps(properties_raw, separators=(",", ":"))
            if len(raw) <= MAX_PROPERTIES_BYTES:
                properties = dict(properties_raw)

        return cls(
            event_id=_new_event_id(),
            received_at_utc=received_at_utc,
            schema_version=EVENT_SCHEMA,
            collector_version=COLLECTOR_VERSION,
            site_id=_as_text(site_id) or _as_text(domain),
            domain=_as_text(domain).lower(),
            environment=_as_text(environment) or "prod",
            visitor_cookie_id_hash=visitor_cookie_id_hash,
            ip_hash=salted_hash(remote_addr, salt=salt),
            ip_prefix=coarse_ip_prefix(remote_addr),
            is_bot=is_bot,
            bot_class=bot_class,
            bot_evidence=tuple(bot_evidence),
            event_type=event_type,
            occurred_at_utc=_as_text(body.get("occurred_at_utc")),
            session_id=_bounded(_as_text(body.get("session_id"))),
            page_path=_bounded(_as_text(body.get("page_path"))),
            event_name=_bounded(_as_text(body.get("event_name"))),
            event_index_in_session=_as_int(body.get("event_index_in_session")),
            page_query_hash=_bounded(_as_text(body.get("page_query_hash"))),
            page_title=_bounded(_as_text(body.get("page_title"))),
            referrer_url=_bounded(_as_text(body.get("referrer_url"))),
            referrer_domain=_bounded(_as_text(body.get("referrer_domain"))),
            origin_type=_bounded(_as_text(body.get("origin_type"))),
            utm_source=_bounded(_as_text(body.get("utm_source"))),
            utm_medium=_bounded(_as_text(body.get("utm_medium"))),
            utm_campaign=_bounded(_as_text(body.get("utm_campaign"))),
            utm_content=_bounded(_as_text(body.get("utm_content"))),
            utm_term=_bounded(_as_text(body.get("utm_term"))),
            previous_page_path=_bounded(_as_text(body.get("previous_page_path"))),
            time_since_previous_ms=_as_int(body.get("time_since_previous_ms")),
            active_time_ms=_as_int(body.get("active_time_ms")),
            visible_time_ms=_as_int(body.get("visible_time_ms")),
            scroll_depth_percent=_as_int(body.get("scroll_depth_percent")),
            user_agent_raw=_bounded(_as_text(user_agent)),
            device_type=_bounded(_as_text(body.get("device_type"))),
            browser_name=_bounded(_as_text(body.get("browser_name"))),
            viewport_width=_as_int(body.get("viewport_width")),
            viewport_height=_as_int(body.get("viewport_height")),
            language=_bounded(_as_text(body.get("language"))),
            do_not_track=_as_bool(body.get("do_not_track")),
            properties=properties,
            page_url=_bounded(_as_text(body.get("page_url"))),
            os_name=_bounded(_as_text(body.get("os_name"))),
            quality_flags=quality_flags,
            action=action,
            campaign_token=campaign_token,
            share_id=share_id,
            referred_by=referred_by,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema_version,
            "collector_version": self.collector_version,
            "event_id": self.event_id,
            "received_at_utc": self.received_at_utc,
            "site_id": self.site_id,
            "domain": self.domain,
            "environment": self.environment,
            "visitor_cookie_id_hash": self.visitor_cookie_id_hash,
            "ip_hash": self.ip_hash,
            "ip_prefix": self.ip_prefix,
            "is_bot": self.is_bot,
            "bot_class": self.bot_class,
            "bot_evidence": list(self.bot_evidence),
            "event_type": self.event_type,
            "occurred_at_utc": self.occurred_at_utc,
            "session_id": self.session_id,
            "page_path": self.page_path,
            "event_name": self.event_name,
            "event_index_in_session": self.event_index_in_session,
            "page_query_hash": self.page_query_hash,
            "page_title": self.page_title,
            "referrer_url": self.referrer_url,
            "referrer_domain": self.referrer_domain,
            "origin_type": self.origin_type,
            "utm_source": self.utm_source,
            "utm_medium": self.utm_medium,
            "utm_campaign": self.utm_campaign,
            "utm_content": self.utm_content,
            "utm_term": self.utm_term,
            "previous_page_path": self.previous_page_path,
            "time_since_previous_ms": self.time_since_previous_ms,
            "active_time_ms": self.active_time_ms,
            "visible_time_ms": self.visible_time_ms,
            "scroll_depth_percent": self.scroll_depth_percent,
            "user_agent_raw": self.user_agent_raw,
            "device_type": self.device_type,
            "browser_name": self.browser_name,
            "viewport_width": self.viewport_width,
            "viewport_height": self.viewport_height,
            "language": self.language,
            "do_not_track": self.do_not_track,
            "properties": dict(self.properties),
            "page_url": self.page_url,
            "os_name": self.os_name,
            "quality_flags": list(self.quality_flags),
            "action": self.action,
            "campaign_token": self.campaign_token,
            "share_id": self.share_id,
            "referred_by": self.referred_by,
        }


__all__ = [
    "CLOCK_SKEW_TOLERANCE_MS",
    "COLLECTOR_VERSION",
    "EVENT_SCHEMA",
    "KNOWN_EVENT_TYPES",
    "MAX_PROPERTIES_BYTES",
    "MAX_TEXT_FIELD_BYTES",
    "REQUIRED_EVENT_FIELDS",
    "STANDARD_ACTIONS",
    "RawEvent",
    "coarse_ip_prefix",
    "compute_quality_flags",
    "salted_hash",
]
