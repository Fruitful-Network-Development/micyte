"""Read-only operations over the raw analytics event log.

Every function in this module is a *pure derivation*: it takes a flat list of
event dicts (projected from the monthly analytics leaflet via
``leaflet_model.flatten_events``) and returns a JSON-serializable summary. No
I/O, no mutation, no caching at the function level (the caller decides when to
memoize).
"""

from __future__ import annotations

from collections import Counter, defaultdict
from collections.abc import Iterable
from typing import Any

# Default sessionization gap: a visitor is in the same session as
# long as consecutive events are within this many ms.
DEFAULT_INACTIVITY_GAP_MS = 30 * 60 * 1000


def _year_months_between(start: str, end: str) -> list[str]:
    """Inclusive list of YYYY-MM tokens between two YYYY-MM bounds."""
    sy, sm = (int(x) for x in start.split("-"))
    ey, em = (int(x) for x in end.split("-"))
    out: list[str] = []
    y, m = sy, sm
    while (y, m) <= (ey, em):
        out.append(f"{y:04d}-{m:02d}")
        m += 1
        if m > 12:
            m = 1
            y += 1
    return out


def filter_bots(
    events: Iterable[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Return ``(human_events, bot_events)`` based on ``is_bot``.

    The raw event captures bot_class as evidence (UA-regex match);
    this function is the canonical split for downstream analytics
    that want to look at one population at a time.
    """
    humans: list[dict[str, Any]] = []
    bots: list[dict[str, Any]] = []
    for event in events:
        if event.get("is_bot"):
            bots.append(event)
        else:
            humans.append(event)
    return humans, bots


def reconstruct_visitor_timeline(
    events: Iterable[dict[str, Any]],
    *,
    visitor_cookie_id_hash: str,
) -> list[dict[str, Any]]:
    """Return all events for one visitor, ordered by occurred_at_utc.

    The hash is the salted visitor_cookie_id_hash from the raw
    event row — callers typically obtain it by reading one event
    and following up with this function for the visitor's full
    history.
    """
    if not visitor_cookie_id_hash:
        return []
    rows = [
        event
        for event in events
        if event.get("visitor_cookie_id_hash") == visitor_cookie_id_hash
    ]
    rows.sort(key=lambda e: e.get("occurred_at_utc") or "")
    return rows


def _to_epoch_ms(iso_string: str) -> int:
    """Parse an ISO-8601 timestamp into epoch ms. Returns 0 on
    failure so sessionize can still group events deterministically
    even when the client clock is missing.
    """
    if not iso_string:
        return 0
    import datetime as _dt

    try:
        # Python 3.11+ handles trailing 'Z'.
        dt = _dt.datetime.fromisoformat(iso_string.replace("Z", "+00:00"))
        return int(dt.timestamp() * 1000)
    except (TypeError, ValueError):
        return 0


def sessionize(
    events: Iterable[dict[str, Any]],
    *,
    inactivity_gap_ms: int = DEFAULT_INACTIVITY_GAP_MS,
) -> list[dict[str, Any]]:
    """Group events into sessions per visitor.

    Within one visitor, consecutive events whose ``occurred_at_utc``
    gap exceeds ``inactivity_gap_ms`` start a new session. The
    client-supplied ``session_id`` is honored as a tiebreaker — if
    it changes between two adjacent events, that always starts a
    new session even when the time gap is small.

    Returns a flat list of session summary dicts:

      ``[{visitor_cookie_id_hash, session_id, started_at_utc,
         ended_at_utc, duration_ms, active_time_ms,
         page_view_count, entry_page, exit_page, origin_type,
         referrer_domain, event_types}, ...]``
    """
    by_visitor: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for event in events:
        visitor = event.get("visitor_cookie_id_hash") or ""
        by_visitor[visitor].append(event)

    summaries: list[dict[str, Any]] = []
    for visitor, rows in by_visitor.items():
        rows.sort(key=lambda e: e.get("occurred_at_utc") or "")
        current: list[dict[str, Any]] = []
        last_ms: int | None = None
        last_session_id: str | None = None
        for event in rows:
            event_ms = _to_epoch_ms(event.get("occurred_at_utc") or "")
            client_session = event.get("session_id") or ""
            split = False
            if last_ms is not None and event_ms - last_ms > inactivity_gap_ms:
                split = True
            if last_session_id is not None and client_session != last_session_id:
                split = True
            if split and current:
                summaries.append(_summarize_session(visitor, current))
                current = []
            current.append(event)
            last_ms = event_ms
            last_session_id = client_session
        if current:
            summaries.append(_summarize_session(visitor, current))
    summaries.sort(key=lambda s: s.get("started_at_utc") or "", reverse=True)
    return summaries


def _summarize_session(
    visitor_cookie_id_hash: str, events: list[dict[str, Any]]
) -> dict[str, Any]:
    started = events[0].get("occurred_at_utc") or ""
    ended = events[-1].get("occurred_at_utc") or ""
    started_ms = _to_epoch_ms(started)
    ended_ms = _to_epoch_ms(ended)
    duration_ms = max(0, ended_ms - started_ms) if started_ms and ended_ms else 0
    active_time_ms = sum(int(e.get("active_time_ms") or 0) for e in events)
    page_view_count = sum(1 for e in events if e.get("event_type") == "page_view")
    page_views = [e for e in events if e.get("event_type") == "page_view"]
    entry_page = page_views[0].get("page_path") if page_views else (events[0].get("page_path") or "")
    exit_page = page_views[-1].get("page_path") if page_views else (events[-1].get("page_path") or "")
    first = events[0]
    return {
        "visitor_cookie_id_hash": visitor_cookie_id_hash,
        "session_id": first.get("session_id") or "",
        "started_at_utc": started,
        "ended_at_utc": ended,
        "duration_ms": duration_ms,
        "active_time_ms": active_time_ms,
        "page_view_count": page_view_count,
        "entry_page": entry_page,
        "exit_page": exit_page,
        "origin_type": first.get("origin_type") or classify_origin(
            first.get("referrer_domain") or "", first.get("utm_source") or ""
        ),
        "referrer_domain": first.get("referrer_domain") or "",
        "event_types": sorted({e.get("event_type") or "" for e in events}),
        "is_bot": any(e.get("is_bot") for e in events),
        "is_bounce": page_view_count <= 1 and len(events) <= 2,
    }


def classify_origin(referrer_domain: str, utm_source: str = "") -> str:
    """Bucket a session's entry source into one of the canonical
    origin types: direct / search / social / email / paid / referral
    / internal / unknown.
    """
    utm = (utm_source or "").lower().strip()
    if utm == "newsletter" or utm == "email":
        return "email"
    if utm in {"google", "bing", "facebook", "twitter", "tiktok", "linkedin"}:
        # An explicit utm_source from a search/social ad is paid.
        return "paid"
    domain = (referrer_domain or "").lower().strip()
    if not domain:
        return "direct"
    if any(s in domain for s in ("google.", "bing.", "duckduckgo.", "yahoo.")):
        return "search"
    if any(
        s in domain
        for s in (
            "facebook.",
            "twitter.",
            "x.com",
            "instagram.",
            "tiktok.",
            "linkedin.",
            "reddit.",
            "youtube.",
        )
    ):
        return "social"
    if "mail." in domain or "gmail." in domain or "outlook." in domain:
        return "email"
    # An internal jump shows the same domain as the page being viewed,
    # but at this layer we don't have the page's domain — caller can
    # post-process. Default to referral.
    return "referral"


# ---------------------------------------------------------------------
# Phase 18c — richer insight derivations.
# Each function below reads pre-sessionized events (or accepts raw
# events + sessionizes internally) and returns a JSON-serializable
# result that lands in the Analytics extension card.
# ---------------------------------------------------------------------


def count_visitors(
    events: Iterable[dict[str, Any]], *, include_bots: bool = False
) -> int:
    """Distinct visitor cookies seen, optionally including bots."""
    seen: set[str] = set()
    for event in events:
        if not include_bots and event.get("is_bot"):
            continue
        token = event.get("visitor_cookie_id_hash") or ""
        if token:
            seen.add(token)
    return len(seen)


def count_repeat_visitors(
    sessions: Iterable[dict[str, Any]], *, min_sessions: int = 2
) -> int:
    """Number of visitors with at least ``min_sessions`` sessions."""
    by_visitor: dict[str, int] = defaultdict(int)
    for session in sessions:
        if session.get("is_bot"):
            continue
        token = session.get("visitor_cookie_id_hash") or ""
        if not token:
            continue
        by_visitor[token] += 1
    return sum(1 for c in by_visitor.values() if c >= min_sessions)


def rank_pages_by_attention(
    events: Iterable[dict[str, Any]], *, top_k: int = 10
) -> list[dict[str, Any]]:
    """Rank pages by their engagement signals.

    For each ``page_view`` event we accumulate view count, unique
    visitor count, average active_time_ms, and average scroll
    depth. Sorted by view count descending. Bots are excluded.
    """
    by_path: dict[str, dict[str, Any]] = defaultdict(
        lambda: {
            "view_count": 0,
            "visitors": set(),
            "active_time_ms": 0,
            "active_samples": 0,
            "scroll_depth_total": 0,
            "scroll_samples": 0,
        }
    )
    for event in events:
        if event.get("is_bot"):
            continue
        path = event.get("page_path") or ""
        if not path:
            continue
        bucket = by_path[path]
        if event.get("event_type") == "page_view":
            bucket["view_count"] += 1
            visitor = event.get("visitor_cookie_id_hash")
            if visitor:
                bucket["visitors"].add(visitor)
        active = int(event.get("active_time_ms") or 0)
        if active:
            bucket["active_time_ms"] += active
            bucket["active_samples"] += 1
        scroll = int(event.get("scroll_depth_percent") or 0)
        if scroll:
            bucket["scroll_depth_total"] += scroll
            bucket["scroll_samples"] += 1
    rows: list[dict[str, Any]] = []
    for path, bucket in by_path.items():
        rows.append(
            {
                "page_path": path,
                "view_count": bucket["view_count"],
                "unique_visitors": len(bucket["visitors"]),
                "average_active_time_ms": (
                    bucket["active_time_ms"] // bucket["active_samples"]
                    if bucket["active_samples"]
                    else 0
                ),
                "scroll_depth_average": (
                    bucket["scroll_depth_total"] // bucket["scroll_samples"]
                    if bucket["scroll_samples"]
                    else 0
                ),
            }
        )
    rows.sort(key=lambda r: (r["view_count"], r["unique_visitors"]), reverse=True)
    return rows[:top_k]


def rank_referrers(
    events: Iterable[dict[str, Any]], *, top_k: int = 10
) -> list[dict[str, Any]]:
    """Rank referrer domains by session count.

    Counts each visitor's first event in a session — that's the
    referrer for the whole session.
    """
    by_session: dict[tuple[str, str], dict[str, Any]] = {}
    for event in events:
        if event.get("is_bot"):
            continue
        key = (
            event.get("visitor_cookie_id_hash") or "",
            event.get("session_id") or "",
        )
        if key in by_session:
            continue
        by_session[key] = {
            "referrer_domain": (event.get("referrer_domain") or "").lower(),
            "active_time_ms": int(event.get("active_time_ms") or 0),
        }
    aggregates: dict[str, dict[str, Any]] = defaultdict(
        lambda: {"sessions": 0, "visitors": set(), "active_time_ms": 0}
    )
    for (visitor, _session), info in by_session.items():
        ref = info["referrer_domain"] or "(direct)"
        bucket = aggregates[ref]
        bucket["sessions"] += 1
        if visitor:
            bucket["visitors"].add(visitor)
        bucket["active_time_ms"] += info["active_time_ms"]
    rows = [
        {
            "referrer_domain": ref,
            "sessions": bucket["sessions"],
            "unique_visitors": len(bucket["visitors"]),
            "average_active_time_ms": (
                bucket["active_time_ms"] // bucket["sessions"]
                if bucket["sessions"]
                else 0
            ),
        }
        for ref, bucket in aggregates.items()
    ]
    rows.sort(key=lambda r: r["sessions"], reverse=True)
    return rows[:top_k]


def top_entry_pages(
    sessions: Iterable[dict[str, Any]], *, top_k: int = 10
) -> list[dict[str, Any]]:
    """Pages that most often start a session."""
    counts: dict[str, int] = defaultdict(int)
    for session in sessions:
        if session.get("is_bot"):
            continue
        entry = session.get("entry_page") or ""
        if entry:
            counts[entry] += 1
    rows = [{"page_path": p, "count": c} for p, c in counts.items()]
    rows.sort(key=lambda r: r["count"], reverse=True)
    return rows[:top_k]


def top_exit_pages(
    sessions: Iterable[dict[str, Any]], *, top_k: int = 10
) -> list[dict[str, Any]]:
    """Pages that most often end a session."""
    counts: dict[str, int] = defaultdict(int)
    for session in sessions:
        if session.get("is_bot"):
            continue
        exit_page = session.get("exit_page") or ""
        if exit_page:
            counts[exit_page] += 1
    rows = [{"page_path": p, "count": c} for p, c in counts.items()]
    rows.sort(key=lambda r: r["count"], reverse=True)
    return rows[:top_k]


def find_common_paths(
    events: Iterable[dict[str, Any]],
    *,
    min_length: int = 2,
    top_k: int = 10,
) -> list[dict[str, Any]]:
    """Most common ordered page-path sequences within a session.

    Considers each visitor's session as a string of page_view paths
    in order, and counts identical sub-sequences of at least
    ``min_length``. Returns the top_k most common.
    """
    # Build per-session page sequences.
    by_session: dict[tuple[str, str], list[str]] = defaultdict(list)
    for event in events:
        if event.get("is_bot"):
            continue
        if event.get("event_type") != "page_view":
            continue
        key = (
            event.get("visitor_cookie_id_hash") or "",
            event.get("session_id") or "",
        )
        path = event.get("page_path") or ""
        if path:
            by_session[key].append(path)
    counts: dict[tuple[str, ...], int] = defaultdict(int)
    for seq in by_session.values():
        if len(seq) < min_length:
            continue
        # Sliding window from min_length up to full sequence length.
        for window in range(min_length, len(seq) + 1):
            for start in range(0, len(seq) - window + 1):
                counts[tuple(seq[start : start + window])] += 1
    rows = [
        {"path": list(seq), "count": count, "length": len(seq)}
        for seq, count in counts.items()
    ]
    rows.sort(key=lambda r: (r["count"], r["length"]), reverse=True)
    return rows[:top_k]


def high_intent_sessions(
    sessions: Iterable[dict[str, Any]],
    *,
    min_active_ms: int = 60_000,
) -> list[dict[str, Any]]:
    """Sessions that visited an intent page AND spent meaningful
    active time. Used as the operator's "real buyers" filter. Intent pages
    are matched on a path SEGMENT boundary (see ``path_touches_intent``).
    """
    out: list[dict[str, Any]] = []
    for session in sessions:
        if session.get("is_bot"):
            continue
        if session.get("active_time_ms", 0) < min_active_ms:
            continue
        # Cheap heuristic: entry or exit page is an intent page.
        if path_touches_intent(session.get("entry_page")) or path_touches_intent(
            session.get("exit_page")
        ):
            out.append(session)
    return out


def detect_vpn_geo_jumps(
    events: Iterable[dict[str, Any]],
    *,
    max_prefixes_per_visitor: int = 1,
) -> list[dict[str, Any]]:
    """Suspect VPN / geo-jump: same visitor cookie seen from >1
    distinct ``ip_prefix``. The threshold is conservative — mobile
    networks rotate prefixes legitimately, so this is *evidence*
    not a conclusion.
    """
    prefixes_by_visitor: dict[str, set[str]] = defaultdict(set)
    for event in events:
        visitor = event.get("visitor_cookie_id_hash") or ""
        prefix = event.get("ip_prefix") or ""
        if visitor and prefix:
            prefixes_by_visitor[visitor].add(prefix)
    flagged: list[dict[str, Any]] = []
    for visitor, prefixes in prefixes_by_visitor.items():
        if len(prefixes) > max_prefixes_per_visitor:
            flagged.append(
                {
                    "visitor_cookie_id_hash": visitor,
                    "ip_prefixes": sorted(prefixes),
                    "evidence": ["multi_prefix"],
                }
            )
    return flagged


# ---------------------------------------------------------------------
# Schema-v3 / JSON Analytics Log Vision derivations.
# Six pure functions that map the existing event stream onto the
# remaining vision retrieval operations.
# ---------------------------------------------------------------------

# --- Single source of intent / conversion / action truth ----------------------
# Both this module (the dashboard widgets) and leaflet_model (the per-session
# summary) classify intent + conversions; they MUST agree or abandoned_intent /
# converted disagree between the two. So the canonical sets live here (the lower
# module — leaflet_model imports from derivations, never the reverse) and
# leaflet_model re-imports them. DEFAULT_* are kept as aliases for the existing
# function-default signatures.
INTENT_PATH_NEEDLES: tuple[str, ...] = (
    "/pricing", "/contact", "/donate", "/subscribe", "/book", "/quote",
)
CONVERSION_EVENT_TYPES: frozenset[str] = frozenset(
    {"form_submit", "outbound_click", "download"}
)
CONVERSION_ACTIONS: frozenset[str] = frozenset(
    {"contact_form_submit", "newsletter_signup", "booking_click", "checkout_complete"}
)
HIGH_INTENT_ACTIONS: frozenset[str] = frozenset(
    {"phone_click", "email_click", "checkout_start", "booking_click"}
) | CONVERSION_ACTIONS

DEFAULT_CONVERSION_EVENT_TYPES: tuple[str, ...] = tuple(sorted(CONVERSION_EVENT_TYPES))
DEFAULT_INTENT_PATHS: tuple[str, ...] = INTENT_PATH_NEEDLES


def path_touches_intent(path: str) -> bool:
    """True if ``path`` IS an intent page or a child of one — matched on a path
    SEGMENT boundary, not a bare substring, so ``/contact-list`` /
    ``/pricing-calculator`` do NOT falsely count. Shared by the widgets here and
    leaflet_model's session_summary so both classify intent identically."""
    p = (path or "").lower()
    return any(p == n or p.startswith(n + "/") for n in INTENT_PATH_NEEDLES)

DEFAULT_INTEREST_CATEGORIES: dict[str, tuple[str, ...]] = {
    "services": ("/services", "/work", "/what-we-do"),
    "pricing": ("/pricing", "/rates", "/quote"),
    "contact": ("/contact", "/connect", "/get-in-touch"),
    "about": ("/about", "/who-we-are", "/team"),
    "blog": ("/blog", "/news", "/articles"),
    "support": ("/support", "/help", "/faq"),
    "donate": ("/donate", "/give", "/support-us"),
    "home": ("/", "/home", "/index"),
}


def visitor_summary(
    events: Iterable[dict[str, Any]],
    visitor_cookie_id_hash: str,
    *,
    conversion_event_types: tuple[str, ...] = DEFAULT_CONVERSION_EVENT_TYPES,
) -> dict[str, Any]:
    """Roll one visitor's events into the vision's "Get visitor
    summary" shape. Returns a dict whose keys mirror the field names
    in the vision (first_seen_at, last_seen_at, ..., conversion_count).
    """
    target = visitor_cookie_id_hash or ""
    visitor_events = sorted(
        (e for e in events if (e.get("visitor_cookie_id_hash") or "") == target),
        key=lambda e: e.get("occurred_at_utc") or "",
    )
    if not visitor_events:
        return {
            "visitor_cookie_id_hash": target,
            "first_seen_at": "",
            "last_seen_at": "",
            "visit_count": 0,
            "session_count": 0,
            "total_events": 0,
            "total_active_time_ms": 0,
            "first_landing_page": "",
            "last_seen_page": "",
            "primary_origin_type": "",
            "primary_device": "",
            "bot_status": "unknown",
            "vpn_or_geo_jump_status": "unknown",
            "conversion_count": 0,
        }

    sessions_seen: set[str] = set()
    origin_counter: Counter[str] = Counter()
    device_counter: Counter[str] = Counter()
    prefix_set: set[str] = set()
    total_active = 0
    conversion_count = 0
    bot_any = False
    bot_all = True
    for ev in visitor_events:
        sid = ev.get("session_id") or ""
        if sid:
            sessions_seen.add(sid)
        origin = (ev.get("origin_type") or classify_origin(
            ev.get("referrer_domain") or "", ev.get("utm_source") or ""
        ))
        if origin:
            origin_counter[origin] += 1
        device = ev.get("device_type") or ""
        if device:
            device_counter[device] += 1
        prefix = ev.get("ip_prefix") or ""
        if prefix:
            prefix_set.add(prefix)
        total_active += int(ev.get("active_time_ms") or 0)
        if ev.get("event_type") in conversion_event_types:
            conversion_count += 1
        if ev.get("is_bot"):
            bot_any = True
        else:
            bot_all = False

    first = visitor_events[0]
    last = visitor_events[-1]
    primary_origin = origin_counter.most_common(1)[0][0] if origin_counter else ""
    primary_device = device_counter.most_common(1)[0][0] if device_counter else ""
    if bot_all:
        bot_status = "bot"
    elif bot_any:
        bot_status = "mixed"
    else:
        bot_status = "human"
    if len(prefix_set) > 1:
        vpn_status = "multi_prefix"
    elif len(prefix_set) == 1:
        vpn_status = "single_prefix"
    else:
        vpn_status = "unknown"

    return {
        "visitor_cookie_id_hash": target,
        "first_seen_at": first.get("occurred_at_utc") or "",
        "last_seen_at": last.get("occurred_at_utc") or "",
        "visit_count": len(sessions_seen),
        "session_count": len(sessions_seen),
        "total_events": len(visitor_events),
        "total_active_time_ms": total_active,
        "first_landing_page": first.get("page_path") or "",
        "last_seen_page": last.get("page_path") or "",
        "primary_origin_type": primary_origin,
        "primary_device": primary_device,
        "bot_status": bot_status,
        "vpn_or_geo_jump_status": vpn_status,
        "conversion_count": conversion_count,
    }


def visitor_interest_profile(
    events: Iterable[dict[str, Any]],
    visitor_cookie_id_hash: str,
    *,
    category_map: dict[str, tuple[str, ...]] | None = None,
    top_k_pages: int = 5,
) -> dict[str, Any]:
    """Roll a visitor's page-view events into category buckets. The
    map is path-substring → category (case-insensitive). Returns the
    bucket histogram, the visitor's top pages, and a coarse intent
    tier derived from the dominant category.
    """
    cmap = category_map or DEFAULT_INTEREST_CATEGORIES
    target = visitor_cookie_id_hash or ""
    page_counter: Counter[str] = Counter()
    category_counter: Counter[str] = Counter()
    total_views = 0
    for ev in events:
        if (ev.get("visitor_cookie_id_hash") or "") != target:
            continue
        if ev.get("event_type") != "page_view":
            continue
        path = (ev.get("page_path") or "").lower()
        if not path:
            continue
        page_counter[path] += 1
        total_views += 1
        for category, needles in cmap.items():
            if any(path.startswith(n.lower()) or n.lower() in path for n in needles):
                category_counter[category] += 1
                break  # one path → one category, first hit wins

    if total_views == 0:
        return {
            "visitor_cookie_id_hash": target,
            "categories": {},
            "top_pages": [],
            "total_page_views": 0,
            "intent_tier": "none",
        }

    categories = {
        name: {
            "hits": count,
            "pct_of_views": round(100 * count / total_views, 2),
        }
        for name, count in category_counter.most_common()
    }
    intent_tier = "browsing"
    if {"pricing", "contact", "donate"} & set(category_counter):
        intent_tier = "high"
    elif "services" in category_counter:
        intent_tier = "research"

    return {
        "visitor_cookie_id_hash": target,
        "categories": categories,
        "top_pages": [
            {"page_path": p, "view_count": c}
            for p, c in page_counter.most_common(top_k_pages)
        ],
        "total_page_views": total_views,
        "intent_tier": intent_tier,
    }


def abandoned_intent_sessions(
    sessions: Iterable[dict[str, Any]],
    *,
    intent_paths: tuple[str, ...] = DEFAULT_INTENT_PATHS,
    conversion_event_types: tuple[str, ...] = DEFAULT_CONVERSION_EVENT_TYPES,
    min_active_ms: int = 5_000,
) -> list[dict[str, Any]]:
    """Sessions where the visitor reached an intent page but did not
    convert. Returns a list ordered most-recent-first; entries contain
    enough context for the operator to decide whether to follow up.
    """
    needles = tuple(p.lower() for p in intent_paths)
    out: list[dict[str, Any]] = []
    for session in sessions:
        if session.get("is_bot"):
            continue
        if session.get("active_time_ms", 0) < min_active_ms:
            continue
        entry = (session.get("entry_page") or "").lower()
        exit_p = (session.get("exit_page") or "").lower()
        # SEGMENT-boundary match (not substring) so /contact-list ≠ /contact.
        visited_intent = [
            n for n in needles
            if entry == n or entry.startswith(n + "/")
            or exit_p == n or exit_p.startswith(n + "/")
        ]
        if not visited_intent:
            continue
        event_types = set(session.get("event_types") or [])
        if event_types & set(conversion_event_types):
            continue  # converted — not abandoned
        out.append(
            {
                "visitor_cookie_id_hash": session.get("visitor_cookie_id_hash") or "",
                "session_id": session.get("session_id") or "",
                "started_at_utc": session.get("started_at_utc") or "",
                "duration_ms": session.get("duration_ms") or 0,
                "active_time_ms": session.get("active_time_ms") or 0,
                "entry_page": session.get("entry_page") or "",
                "exit_page": session.get("exit_page") or "",
                "visited_intent_pages": sorted(set(visited_intent)),
                "referrer_domain": session.get("referrer_domain") or "",
                "origin_type": session.get("origin_type") or "",
            }
        )
    out.sort(key=lambda s: s.get("started_at_utc") or "", reverse=True)
    return out


def dead_end_pages(
    sessions: Iterable[dict[str, Any]],
    *,
    min_entries: int = 5,
    single_page_rate_threshold: float = 0.6,
    top_k: int = 10,
) -> list[dict[str, Any]]:
    """Entry pages whose sessions disproportionately bounce — entry
    and exit are the same page. The output field
    ``single_page_session_rate`` names exactly what the function
    measures (it is *not* a generalized "exit rate" — those would
    require event-level data, not just session start/end). Uses
    session-level entry/exit signals — caller should pass sessionized
    data.
    """
    by_entry: dict[str, dict[str, Any]] = defaultdict(
        lambda: {"entries": 0, "same_page_exits": 0, "active_time_total_ms": 0, "active_samples": 0}
    )
    for session in sessions:
        if session.get("is_bot"):
            continue
        entry = session.get("entry_page") or ""
        exit_p = session.get("exit_page") or ""
        if not entry:
            continue
        bucket = by_entry[entry]
        bucket["entries"] += 1
        active = int(session.get("active_time_ms") or 0)
        if active:
            bucket["active_time_total_ms"] += active
            bucket["active_samples"] += 1
        if exit_p == entry:
            bucket["same_page_exits"] += 1
    rows: list[dict[str, Any]] = []
    for page, bucket in by_entry.items():
        if bucket["entries"] < min_entries:
            continue
        rate = bucket["same_page_exits"] / bucket["entries"]
        if rate < single_page_rate_threshold:
            continue
        rows.append(
            {
                "page_path": page,
                "entry_count": bucket["entries"],
                "single_page_session_rate": round(rate, 3),
                "average_active_time_ms": (
                    bucket["active_time_total_ms"] // bucket["active_samples"]
                    if bucket["active_samples"]
                    else 0
                ),
            }
        )
    rows.sort(
        key=lambda r: (r["single_page_session_rate"], r["entry_count"]),
        reverse=True,
    )
    return rows[:top_k]


def conversion_assisting_pages(
    events: Iterable[dict[str, Any]],
    *,
    conversion_event_types: tuple[str, ...] = DEFAULT_CONVERSION_EVENT_TYPES,
    lookback: int = 5,
    top_k: int = 10,
) -> list[dict[str, Any]]:
    """Pages that frequently appear in the ``lookback`` events before
    a conversion. Returns a ranked list of (page_path, assist_count).
    """
    by_session: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for ev in events:
        if ev.get("is_bot"):
            continue
        key = (
            ev.get("visitor_cookie_id_hash") or "",
            ev.get("session_id") or "",
        )
        by_session[key].append(ev)
    assist_counter: Counter[str] = Counter()
    for evs in by_session.values():
        evs.sort(key=lambda e: e.get("occurred_at_utc") or "")
        for i, ev in enumerate(evs):
            if ev.get("event_type") not in conversion_event_types:
                continue
            window = evs[max(0, i - lookback) : i]
            seen: set[str] = set()
            for prior in window:
                if prior.get("event_type") != "page_view":
                    continue
                path = prior.get("page_path") or ""
                if path and path not in seen:
                    assist_counter[path] += 1
                    seen.add(path)
    rows = [
        {"page_path": p, "assist_count": c}
        for p, c in assist_counter.most_common(top_k)
    ]
    return rows


def traffic_origin_classification(
    events: Iterable[dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    """Aggregate sessions by origin_type bucket (uses
    ``classify_origin`` for events that didn't carry an explicit
    origin_type). Returns a dict keyed by origin token with sub-counts.

    NDJSON files are append-order, which is usually but not always
    chronological — server retries / out-of-order delivery can flip
    two adjacent rows. Sort by occurred_at_utc up-front so the
    "first event per session" we lock the origin to is the actual
    chronological first, not the first arrived.
    """
    events = sorted(events, key=lambda e: e.get("occurred_at_utc") or "")
    by_session: dict[tuple[str, str], dict[str, Any]] = {}
    for ev in events:
        if ev.get("is_bot"):
            continue
        key = (
            ev.get("visitor_cookie_id_hash") or "",
            ev.get("session_id") or "",
        )
        if key in by_session:
            continue
        origin = ev.get("origin_type") or classify_origin(
            ev.get("referrer_domain") or "", ev.get("utm_source") or ""
        )
        by_session[key] = {
            "origin_type": origin or "unknown",
            "visitor": key[0],
            "active_time_ms": int(ev.get("active_time_ms") or 0),
        }
    aggregates: dict[str, dict[str, Any]] = defaultdict(
        lambda: {"sessions": 0, "visitors": set(), "active_time_total_ms": 0}
    )
    for info in by_session.values():
        bucket = aggregates[info["origin_type"]]
        bucket["sessions"] += 1
        if info["visitor"]:
            bucket["visitors"].add(info["visitor"])
        bucket["active_time_total_ms"] += info["active_time_ms"]
    return {
        origin: {
            "sessions": bucket["sessions"],
            "unique_visitors": len(bucket["visitors"]),
            "average_active_time_ms": (
                bucket["active_time_total_ms"] // bucket["sessions"]
                if bucket["sessions"]
                else 0
            ),
        }
        for origin, bucket in aggregates.items()
    }


__all__ = [
    "CONVERSION_ACTIONS",
    "CONVERSION_EVENT_TYPES",
    "DEFAULT_CONVERSION_EVENT_TYPES",
    "DEFAULT_INACTIVITY_GAP_MS",
    "DEFAULT_INTENT_PATHS",
    "DEFAULT_INTEREST_CATEGORIES",
    "HIGH_INTENT_ACTIONS",
    "INTENT_PATH_NEEDLES",
    "abandoned_intent_sessions",
    "classify_origin",
    "conversion_assisting_pages",
    "count_repeat_visitors",
    "count_visitors",
    "dead_end_pages",
    "detect_vpn_geo_jumps",
    "filter_bots",
    "find_common_paths",
    "high_intent_sessions",
    "path_touches_intent",
    "rank_pages_by_attention",
    "rank_referrers",
    "reconstruct_visitor_timeline",
    "sessionize",
    "top_entry_pages",
    "top_exit_pages",
    "traffic_origin_classification",
    "visitor_interest_profile",
    "visitor_summary",
]
