"""Pure hierarchical model for the monthly analytics *leaflet*.

The leaflet is the canonical per-site, per-month analytics store — one YAML
file shaped ``visitors → sessions → events`` (see the demo in the operator
brief and ``docs/analytics_convention.md`` in the webapps repo). It replaces
the per-domain raw NDJSON log: there is no second store behind it.

Everything in this module is a **pure transform** over plain dicts — no I/O,
no clock, no randomness. The filesystem adapter
(:mod:`MyCiteV2.packages.adapters.filesystem.analytics_leaflet`) owns locking,
atomic writes, and buffering; the route owns request parsing. That split keeps
the merge logic exhaustively unit-testable.

Design notes that matter:

* **Heartbeats + scrolls fold into their page_view.** The browser emits a
  ``heartbeat`` every ~15s to accumulate active/visible time and scroll depth.
  Storing each one would bloat the leaflet 5-10x and doesn't match the demo
  YAML's event granularity, so a heartbeat/scroll is *merged into* the owning
  ``page_view`` event (active/visible summed, scroll kept as the max) rather
  than appended. Only "real" events (page_view, click, form_submit,
  outbound_click, download, error) become stored event rows.

* **Per-event PII is minimized.** Stored events carry no IP hash/prefix; the
  coarse /24 prefixes a visitor was seen from live as a small set on the
  visitor (``visitor_context.ip_prefixes``) purely to support the
  ``multi_prefix`` geo-jump *evidence* flag.

* **session_summary is recomputed from the session's events** on every merge
  (sessions are small; this is robust against incremental-update drift).
  visitor_context aggregates that depend on raw per-event server signals
  (is_bot, ip_prefix, device/os) are updated incrementally from the incoming
  raw event, since those signals aren't all persisted per row.

* **Idempotency is the caller's job.** ``merge_event`` assumes each
  ``event_id`` is merged at most once (the live buffer dedups; the migration
  rebuilds a month from scratch). It does not keep a persisted seen-set.
"""

from __future__ import annotations

import logging
from itertools import pairwise
from typing import Any

from .derivations import (
    CONVERSION_ACTIONS,
    CONVERSION_EVENT_TYPES,
    HIGH_INTENT_ACTIONS,
    classify_origin,
    path_touches_intent,
)
from .event_schema import _iso_to_epoch_ms

# The intent/conversion/action sets + path_touches_intent are the SINGLE SOURCE
# in derivations (the lower module) and reused here so the session_summary and
# the dashboard widgets classify intent/conversions identically. Imported, not
# redefined.

_log = logging.getLogger("mycite.portal_host")

ANALYTICS_RECORD_SCHEMA = "mycite.site_core.analytics_record.v1"
ANALYTICS_RECORD_KIND = "record-analytics"

# Event types that become a stored event row. Everything else
# (heartbeat, scroll) folds into the owning page_view.
STORED_EVENT_TYPES = frozenset(
    {"page_view", "click", "form_submit", "outbound_click", "download", "error", "ops_probe"}
)
FOLD_EVENT_TYPES = frozenset({"heartbeat", "scroll"})

# rapid_navigation evidence: ≥ this many page_views whose median inter-view gap
# is under the threshold looks automated.
RAPID_NAV_MIN_VIEWS = 4
RAPID_NAV_MEDIAN_MS = 1500
HIGH_INTENT_MIN_ACTIVE_MS = 60_000


def _txt(value: Any) -> str:
    return "" if value is None else str(value).strip()


def _int(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def empty_month(*, entity: str, domain: str, period: str, generated_at: str) -> dict[str, Any]:
    """A fresh month skeleton. ``period`` is ``YYYY-MM``."""
    return {
        "schema": ANALYTICS_RECORD_SCHEMA,
        "kind": ANALYTICS_RECORD_KIND,
        "entity": _txt(entity),
        "domain": _txt(domain),
        "period": _txt(period),
        "period_label": _period_label(period),
        "generated_at": _txt(generated_at),
        "visitors": [],
    }


_MONTH_NAMES = (
    "", "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December",
)


def _period_label(period: str) -> str:
    token = _txt(period)
    parts = token.split("-")
    if len(parts) == 2 and parts[0].isdigit() and parts[1].isdigit():
        m = int(parts[1])
        if 1 <= m <= 12:
            return f"{_MONTH_NAMES[m]} {parts[0]}"
    return token


# ---------------------------------------------------------------------------
# Merge — fold one raw event dict into the month structure.
# ---------------------------------------------------------------------------


def merge_event(month: dict[str, Any], raw: dict[str, Any]) -> dict[str, Any]:
    """Merge one RawEvent dict (``RawEvent.to_dict()`` shape) into ``month``.

    Mutates and returns ``month``. The caller guarantees each event_id is
    merged at most once. Unknown / empty event_types are ignored.
    """
    event_type = _txt(raw.get("event_type"))
    cookie = _txt(raw.get("visitor_cookie_id_hash"))
    occurred = _txt(raw.get("occurred_at_utc") or raw.get("occurred_at"))
    if not cookie:
        # A server-minted visitor hash should always be present; an empty one
        # means the cookie/salt pipeline is broken. Surface it rather than
        # silently dropping traffic (the failure mode would be invisible).
        if event_type:
            _log.warning(
                "analytics_event_dropped_no_cookie_hash event_type=%s page=%s",
                event_type, _txt(raw.get("page_path")),
            )
        return month
    if not event_type:
        return month
    if event_type not in STORED_EVENT_TYPES and event_type not in FOLD_EVENT_TYPES:
        return month

    visitor = _find_or_create_visitor(month, cookie, occurred)
    _touch_visitor_context(visitor, raw, occurred)

    session = _find_or_create_session(visitor, raw, occurred)

    if event_type in FOLD_EVENT_TYPES:
        _fold_into_page_view(session, raw)
    else:
        # Idempotency guard: skip a stored event already merged into this
        # session — exact event_id, or a client retry carrying the same
        # occurred_at + type + path — so a >250ms retry or a cross-worker
        # double-POST can't double-count a page_view / form_submit.
        event_id = _txt(raw.get("event_id"))
        page_path = _txt(raw.get("page_path"))
        already = any(
            (event_id and e.get("event_id") == event_id)
            or (
                e.get("occurred_at") == occurred
                and e.get("event_type") == event_type
                and e.get("page_path") == page_path
            )
            for e in session["events"]
        )
        if already:
            return month
        session["events"].append(_stored_event(raw, event_type, occurred))

    _recompute_session_summary(session)
    _recompute_visitor_flags(visitor)
    visitor["last_seen_at"] = _max_iso(visitor.get("last_seen_at"), occurred)
    return month


def _find_or_create_visitor(month: dict[str, Any], cookie: str, occurred: str) -> dict[str, Any]:
    for v in month["visitors"]:
        if v.get("visitor_cookie_id_hash") == cookie:
            return v
    n = len(month["visitors"]) + 1
    visitor = {
        "visitor_record_id": f"visitor_{n:04d}",
        "visitor_cookie_id_hash": cookie,
        "first_seen_at": occurred,
        "last_seen_at": occurred,
        "returning_from_prior_month": False,
        "prior_period": None,
        "visitor_context": {
            "first_origin_type": "",
            "first_referrer_domain": "",
            "primary_device_type": "",
            "primary_browser": "",
            "primary_os": "",
            "bot_assessment": {"is_bot": False, "bot_class": "", "bot_evidence": []},
            "flags": [],
            "ip_prefixes": [],
            "share_id": "",   # this visitor's JS-readable fnd_sid (for A→B referral chains)
            "network": None,  # enrichment hook (no GeoIP this pass)
            "region": None,   # enrichment hook
        },
        "sessions": [],
    }
    month["visitors"].append(visitor)
    return visitor


def _touch_visitor_context(visitor: dict[str, Any], raw: dict[str, Any], occurred: str) -> None:
    ctx = visitor["visitor_context"]
    # first_* set once, from the chronologically-first event we see.
    if not ctx["first_origin_type"]:
        ctx["first_origin_type"] = _origin_of(raw)
    if not ctx["first_referrer_domain"]:
        ctx["first_referrer_domain"] = _txt(raw.get("referrer_domain"))
    if not ctx["primary_device_type"]:
        ctx["primary_device_type"] = _device_of(raw)
    if not ctx["primary_browser"]:
        ctx["primary_browser"] = _txt(raw.get("browser_name"))
    if not ctx["primary_os"]:
        ctx["primary_os"] = _txt(raw.get("os_name"))
    # bot_assessment — OR-in evidence; first non-empty class wins.
    if raw.get("is_bot"):
        ba = ctx["bot_assessment"]
        ba["is_bot"] = True
        if not ba["bot_class"]:
            ba["bot_class"] = _txt(raw.get("bot_class")) or "likely_bot"
        for ev in raw.get("bot_evidence") or []:
            ev = _txt(ev)
            if ev and ev not in ba["bot_evidence"]:
                ba["bot_evidence"].append(ev)
    # coarse prefix set (for multi_prefix evidence only).
    prefix = _txt(raw.get("ip_prefix"))
    if prefix and prefix not in ctx["ip_prefixes"]:
        ctx["ip_prefixes"].append(prefix)
    # this visitor's own share id (set once) — maps referred_by back to them.
    if not ctx.get("share_id"):
        ctx["share_id"] = _txt(raw.get("share_id"))
    visitor["first_seen_at"] = _min_iso(visitor.get("first_seen_at"), occurred)


def _find_or_create_session(visitor: dict[str, Any], raw: dict[str, Any], occurred: str) -> dict[str, Any]:
    sid = _txt(raw.get("session_id"))
    for s in visitor["sessions"]:
        if s.get("session_id") == sid:
            s["ended_at"] = _max_iso(s.get("ended_at"), occurred)
            return s
    session = {
        "session_id": sid,
        "started_at": occurred,
        "ended_at": occurred,
        "routed_from": {
            "origin_type": _origin_of(raw),
            "referrer_url": _txt(raw.get("referrer_url")),
            "referrer_domain": _txt(raw.get("referrer_domain")),
            "utm_source": _txt(raw.get("utm_source")),
            "utm_medium": _txt(raw.get("utm_medium")),
            "utm_campaign": _txt(raw.get("utm_campaign")),
            "campaign_token": _txt(raw.get("campaign_token")),
            "referred_by": _txt(raw.get("referred_by")),  # sharer's fnd_sid (A→B chain)
        },
        "session_summary": {},
        "events": [],
    }
    visitor["sessions"].append(session)
    return session


def _stored_event(raw: dict[str, Any], event_type: str, occurred: str) -> dict[str, Any]:
    props = raw.get("properties") if isinstance(raw.get("properties"), dict) else {}
    interaction = _txt(raw.get("interaction_target") or props.get("interaction_target") or raw.get("event_name"))
    value = _txt(raw.get("event_value") or props.get("event_value"))
    return {
        "event_id": _txt(raw.get("event_id")),
        "occurred_at": occurred,
        "received_at": _txt(raw.get("received_at_utc") or raw.get("received_at")),
        "event_type": event_type,
        "action": _txt(raw.get("action")),
        "page_path": _txt(raw.get("page_path")),
        "previous_page_path": _txt(raw.get("previous_page_path")),
        "referrer_domain": _txt(raw.get("referrer_domain")),
        "origin_type": _origin_of(raw),
        "active_time_ms": _int(raw.get("active_time_ms")),
        "visible_time_ms": _int(raw.get("visible_time_ms")),
        "scroll_depth_percent": _int(raw.get("scroll_depth_percent")),
        "interaction_target": interaction,
        "event_value": value,
        "quality_flags": list(raw.get("quality_flags") or []),
    }


def _fold_into_page_view(session: dict[str, Any], raw: dict[str, Any]) -> None:
    """Accumulate a heartbeat/scroll into the page_view it belongs to."""
    path = _txt(raw.get("page_path"))
    target = None
    for ev in reversed(session["events"]):
        if ev["event_type"] != "page_view":
            continue
        if not path or ev["page_path"] == path:
            target = ev
            break
    if target is None:
        # No page_view yet (e.g. a heartbeat arrived first) — nothing to fold
        # into; the active time still lands on the session via recompute.
        # Stash a synthetic page_view so the time isn't lost.
        target = _stored_event(raw, "page_view", _txt(raw.get("occurred_at_utc") or raw.get("occurred_at")))
        target["active_time_ms"] = 0
        target["visible_time_ms"] = 0
        target["scroll_depth_percent"] = 0
        session["events"].append(target)
    # Heartbeats carry the CUMULATIVE active/visible time for the page (a
    # running total since page load), so keep the MAX, not the sum — summing the
    # successive snapshots would multiply the real time by the heartbeat count.
    target["active_time_ms"] = max(target["active_time_ms"], _int(raw.get("active_time_ms")))
    target["visible_time_ms"] = max(target["visible_time_ms"], _int(raw.get("visible_time_ms")))
    target["scroll_depth_percent"] = max(
        target["scroll_depth_percent"], _int(raw.get("scroll_depth_percent"))
    )


# ---------------------------------------------------------------------------
# Recompute — derive summaries from the (small) session/visitor structures.
# ---------------------------------------------------------------------------


def _recompute_session_summary(session: dict[str, Any]) -> None:
    events = session["events"]
    page_views = [e for e in events if e["event_type"] == "page_view"]
    active = sum(_int(e.get("active_time_ms")) for e in events)
    actions = sorted({_txt(e.get("action")) for e in events if _txt(e.get("action"))})
    entry = page_views[0]["page_path"] if page_views else (events[0]["page_path"] if events else "")
    exit_p = page_views[-1]["page_path"] if page_views else (events[-1]["page_path"] if events else "")

    converted = any(
        e["event_type"] in CONVERSION_EVENT_TYPES or _txt(e.get("action")) in CONVERSION_ACTIONS
        for e in events
    )
    touched_intent = any(path_touches_intent(e.get("page_path")) for e in events)
    high_intent = bool(
        (touched_intent and active >= HIGH_INTENT_MIN_ACTIVE_MS)
        or any(_txt(e.get("action")) in HIGH_INTENT_ACTIONS for e in events)
    )
    session["session_summary"] = {
        "entry_page": entry,
        "exit_page": exit_p,
        "page_view_count": len(page_views),
        "active_time_ms": active,
        "converted": converted,
        "is_bounce": len(page_views) <= 1 and len(events) <= 1,
        "high_intent": high_intent,
        "abandoned_intent": bool(touched_intent and not converted),
        "actions": actions,
    }


def _recompute_visitor_flags(visitor: dict[str, Any]) -> None:
    ctx = visitor["visitor_context"]
    flags: list[str] = []
    if len(ctx["ip_prefixes"]) > 1:
        flags.append("multi_prefix")
    # rapid_navigation across all of the visitor's page_views.
    occured: list[int] = []
    for s in visitor["sessions"]:
        for e in s["events"]:
            if e["event_type"] == "page_view":
                ms = _iso_to_epoch_ms(e.get("occurred_at"))
                if ms is not None:
                    occured.append(ms)
    occured.sort()
    if len(occured) >= RAPID_NAV_MIN_VIEWS:
        gaps = [b - a for a, b in pairwise(occured) if b >= a]
        if gaps:
            gaps.sort()
            median = gaps[len(gaps) // 2]
            if median < RAPID_NAV_MEDIAN_MS:
                flags.append("rapid_navigation")
    if ctx["bot_assessment"]["is_bot"]:
        flags.append("ua_flagged_bot")
    ctx["flags"] = flags


# ---------------------------------------------------------------------------
# Cross-month lineage + finalization.
# ---------------------------------------------------------------------------


def link_prior_month(month: dict[str, Any], prior_month: dict[str, Any] | None) -> dict[str, Any]:
    """Mark visitors whose cookie also appears in ``prior_month`` as returning."""
    if not prior_month:
        return month
    prior_cookies = {
        v.get("visitor_cookie_id_hash")
        for v in prior_month.get("visitors", [])
        if v.get("visitor_cookie_id_hash")
    }
    prior_period = _txt(prior_month.get("period")) or None
    for v in month["visitors"]:
        if v.get("visitor_cookie_id_hash") in prior_cookies:
            v["returning_from_prior_month"] = True
            v["prior_period"] = prior_period
    return month


def finalize_month(month: dict[str, Any], *, generated_at: str) -> dict[str, Any]:
    """Sort visitors by first appearance + sessions chronologically; stamp time."""
    month["generated_at"] = _txt(generated_at)
    month["visitors"].sort(key=lambda v: _txt(v.get("first_seen_at")))
    for i, v in enumerate(month["visitors"], start=1):
        v["visitor_record_id"] = f"visitor_{i:04d}"
        v["sessions"].sort(key=lambda s: _txt(s.get("started_at")))
    return month


def flatten_events(month: dict[str, Any]) -> list[dict[str, Any]]:
    """Yield flat event dicts in the shape :mod:`derivations` consumes.

    Lets the summary endpoint reuse the existing widget derivations
    (rank_referrers, traffic_origin_classification, dead_end_pages, …) over a
    leaflet without a second implementation. Per-event ``is_bot`` /
    ``visitor_cookie_id_hash`` / ``ip_prefix`` are re-projected from the
    owning visitor/session so the derivations behave exactly as on NDJSON.
    """
    out: list[dict[str, Any]] = []
    for v in month.get("visitors", []):
        ctx = v.get("visitor_context") or {}
        is_bot = bool((ctx.get("bot_assessment") or {}).get("is_bot"))
        bot_class = (ctx.get("bot_assessment") or {}).get("bot_class") or ""
        cookie = v.get("visitor_cookie_id_hash") or ""
        prefixes = ctx.get("ip_prefixes") or []
        prefix = prefixes[0] if prefixes else ""
        device = ctx.get("primary_device_type") or ""
        share_id = ctx.get("share_id") or ""
        for s in v.get("sessions", []):
            routed = s.get("routed_from") or {}
            sid = s.get("session_id") or ""
            referred_by = routed.get("referred_by") or ""
            for e in s.get("events", []):
                out.append(
                    {
                        "visitor_cookie_id_hash": cookie,
                        "session_id": sid,
                        "is_bot": is_bot,
                        "bot_class": bot_class,
                        "ip_prefix": prefix,
                        "device_type": device,
                        "share_id": share_id,
                        "referred_by": referred_by,
                        "event_type": e.get("event_type") or "",
                        "action": e.get("action") or "",
                        "occurred_at_utc": e.get("occurred_at") or "",
                        "page_path": e.get("page_path") or "",
                        "previous_page_path": e.get("previous_page_path") or "",
                        "referrer_domain": e.get("referrer_domain") or routed.get("referrer_domain") or "",
                        "origin_type": e.get("origin_type") or routed.get("origin_type") or "",
                        "utm_source": routed.get("utm_source") or "",
                        "active_time_ms": _int(e.get("active_time_ms")),
                        "visible_time_ms": _int(e.get("visible_time_ms")),
                        "scroll_depth_percent": _int(e.get("scroll_depth_percent")),
                        "quality_flags": e.get("quality_flags") or [],
                    }
                )
    return out


# ---------------------------------------------------------------------------
# small helpers
# ---------------------------------------------------------------------------


def _origin_of(raw: dict[str, Any]) -> str:
    return _txt(raw.get("origin_type")) or classify_origin(
        _txt(raw.get("referrer_domain")), _txt(raw.get("utm_source"))
    )


def _device_of(raw: dict[str, Any]) -> str:
    device = _txt(raw.get("device_type"))
    if device:
        return device
    width = _int(raw.get("viewport_width"))
    if width and width < 768:
        return "mobile"
    if width:
        return "desktop"
    return ""


def _min_iso(a: Any, b: Any) -> str:
    a, b = _txt(a), _txt(b)
    if not a:
        return b
    if not b:
        return a
    return a if a <= b else b


def _max_iso(a: Any, b: Any) -> str:
    a, b = _txt(a), _txt(b)
    if not a:
        return b
    if not b:
        return a
    return a if a >= b else b


__all__ = [
    "ANALYTICS_RECORD_KIND",
    "ANALYTICS_RECORD_SCHEMA",
    "CONVERSION_ACTIONS",
    "CONVERSION_EVENT_TYPES",
    "HIGH_INTENT_ACTIONS",
    "STORED_EVENT_TYPES",
    "empty_month",
    "finalize_month",
    "flatten_events",
    "link_prior_month",
    "merge_event",
]
