"""UA-regex bot classifier — evidence-only, no conclusions.

The rules below are deliberately conservative + curated. The
intent is to *flag* automated traffic for later filtering, not to
gate access. False positives (e.g. a custom Python script crawling
its own site for ops probes) are fine — the operator can choose
to include or exclude bot rows from any analytics view.

Pattern order matters: the first match wins, so put high-confidence
verified bots before generic scraper patterns.
"""

from __future__ import annotations

import re

# Each entry is (bot_class, evidence_key, compiled regex).
# Patterns are case-insensitive. Anchored loosely with substring
# match because UAs are wildly varied.
_BOT_RULES: tuple[tuple[str, str, re.Pattern[str]], ...] = (
    ("verified_search", "ua_googlebot", re.compile(r"googlebot", re.I)),
    ("verified_search", "ua_bingbot", re.compile(r"bingbot", re.I)),
    ("verified_search", "ua_duckduckbot", re.compile(r"duckduckbot", re.I)),
    ("verified_search", "ua_yandex", re.compile(r"yandex(bot|images|video)", re.I)),
    ("verified_search", "ua_baidu", re.compile(r"baiduspider", re.I)),
    ("verified_search", "ua_applebot", re.compile(r"applebot", re.I)),
    ("ai_crawler", "ua_gptbot", re.compile(r"gptbot", re.I)),
    ("ai_crawler", "ua_claudebot", re.compile(r"claudebot", re.I)),
    ("ai_crawler", "ua_anthropic", re.compile(r"anthropic", re.I)),
    ("ai_crawler", "ua_perplexity", re.compile(r"perplexitybot", re.I)),
    ("ai_crawler", "ua_ccbot", re.compile(r"ccbot", re.I)),
    ("ai_crawler", "ua_bytespider", re.compile(r"bytespider", re.I)),
    ("uptime_monitor", "ua_pingdom", re.compile(r"pingdom", re.I)),
    ("uptime_monitor", "ua_uptimerobot", re.compile(r"uptimerobot", re.I)),
    ("uptime_monitor", "ua_statuscake", re.compile(r"statuscake", re.I)),
    ("uptime_monitor", "ua_betteruptime", re.compile(r"better\s*uptime", re.I)),
    ("scraper", "ua_scrapy", re.compile(r"scrapy", re.I)),
    ("scraper", "ua_python_requests", re.compile(r"python-requests", re.I)),
    ("scraper", "ua_python_urllib", re.compile(r"python-urllib", re.I)),
    ("scraper", "ua_curl", re.compile(r"^curl/", re.I)),
    ("scraper", "ua_wget", re.compile(r"^wget/", re.I)),
    ("scraper", "ua_httpx", re.compile(r"^httpx/", re.I)),
    ("scraper", "ua_node_fetch", re.compile(r"node-fetch", re.I)),
    ("scraper", "ua_go_http", re.compile(r"go-http-client", re.I)),
    ("seo_tool", "ua_ahrefsbot", re.compile(r"ahrefsbot", re.I)),
    ("seo_tool", "ua_semrush", re.compile(r"semrushbot", re.I)),
    ("seo_tool", "ua_mj12bot", re.compile(r"mj12bot", re.I)),
    # ops_probe is the legacy event_type used for portal-side health
    # probes — the matching UAs are the operator's own tooling, but
    # they're still automation.
    ("uptime_monitor", "ua_ops_probe", re.compile(r"ops-probe", re.I)),
    ("likely_bot", "ua_generic_bot", re.compile(r"\bbot\b|\bcrawler\b|\bspider\b", re.I)),
)


def classify_user_agent(user_agent: str) -> tuple[bool, str, list[str]]:
    """Return ``(is_bot, bot_class, evidence)`` for the given UA.

    ``evidence`` is a list of rule keys that fired (typically
    length 1 because we short-circuit on first match). Returns
    ``(True, "likely_bot", ["ua_empty"])`` for an empty UA — that
    case is almost always automation. A normal browser UA returns
    ``(False, "", [])``.
    """
    text = (user_agent or "").strip()
    if not text:
        return True, "likely_bot", ["ua_empty"]
    for bot_class, evidence_key, pattern in _BOT_RULES:
        if pattern.search(text):
            return True, bot_class, [evidence_key]
    return False, "", []


# Coarse /24 (or /48) prefixes whose traffic is ours, not the public's.
# Loopback is the decisive one: 338 visitor rows in the live store carry
# 127.0.0.0/24 — requests made ON the box, i.e. browser-smoke runs. 252 of
# those landed on one site on one day. They are not bots by UA (they drive a
# real headless browser) so nothing else catches them, and they inflate
# "unique visitors" with traffic the operator generated.
_INTERNAL_PREFIXES: tuple[str, ...] = (
    "127.",        # loopback — the box talking to itself
    "10.",         # RFC1918
    "192.168.",    # RFC1918
    "169.254.",    # link-local
    "::1",         # IPv6 loopback
    "fc00:", "fd00:",  # IPv6 unique-local
)


def prefix_is_internal(ip_prefix: str) -> bool:
    """True when a coarse ip_prefix names our own infrastructure.

    Evidence, like ``bot_class`` — it names a signal, not a verdict. The
    dashboard uses it to offer "hide internal traffic"; nothing drops a row.
    """
    token = (ip_prefix or "").strip().lower()
    if not token:
        return False
    return any(token.startswith(p) for p in _INTERNAL_PREFIXES)


__all__ = ["classify_user_agent", "prefix_is_internal"]
