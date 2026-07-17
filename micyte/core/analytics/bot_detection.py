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


__all__ = ["classify_user_agent"]
