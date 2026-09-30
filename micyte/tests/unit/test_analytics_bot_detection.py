"""Phase 18a — UA-regex bot classifier tests."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from micyte.core.analytics import classify_user_agent


class BotClassifierTests(unittest.TestCase):
    def test_googlebot_is_verified_search(self) -> None:
        is_bot, cls, evidence = classify_user_agent(
            "Mozilla/5.0 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)"
        )
        self.assertTrue(is_bot)
        self.assertEqual(cls, "verified_search")
        self.assertEqual(evidence, ["ua_googlebot"])

    def test_gptbot_is_ai_crawler(self) -> None:
        is_bot, cls, _ = classify_user_agent("Mozilla/5.0 (compatible; GPTBot/1.0)")
        self.assertTrue(is_bot)
        self.assertEqual(cls, "ai_crawler")

    def test_python_requests_is_scraper(self) -> None:
        is_bot, cls, _ = classify_user_agent("python-requests/2.31.0")
        self.assertTrue(is_bot)
        self.assertEqual(cls, "scraper")

    def test_pingdom_is_uptime_monitor(self) -> None:
        is_bot, cls, _ = classify_user_agent("Pingdom.com_bot_version_1.4")
        self.assertTrue(is_bot)
        self.assertEqual(cls, "uptime_monitor")

    def test_ahrefsbot_is_seo_tool(self) -> None:
        is_bot, cls, _ = classify_user_agent("Mozilla/5.0 (compatible; AhrefsBot/7.0)")
        self.assertTrue(is_bot)
        self.assertEqual(cls, "seo_tool")

    def test_empty_ua_is_likely_bot(self) -> None:
        is_bot, cls, evidence = classify_user_agent("")
        self.assertTrue(is_bot)
        self.assertEqual(cls, "likely_bot")
        self.assertEqual(evidence, ["ua_empty"])

    def test_real_browser_is_not_bot(self) -> None:
        ua = (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36"
        )
        is_bot, cls, evidence = classify_user_agent(ua)
        self.assertFalse(is_bot)
        self.assertEqual(cls, "")
        self.assertEqual(evidence, [])

    def test_case_insensitive_match(self) -> None:
        is_bot, cls, _ = classify_user_agent("GOOGLEBOT/2.1")
        self.assertTrue(is_bot)
        self.assertEqual(cls, "verified_search")

    def test_first_rule_wins(self) -> None:
        # A UA that mentions BOTH "Googlebot" and "Scrapy" lands as
        # verified_search because that rule comes first in the table.
        is_bot, cls, _ = classify_user_agent("Scrapy/2.0 (+Googlebot)")
        self.assertTrue(is_bot)
        self.assertEqual(cls, "verified_search")


if __name__ == "__main__":
    unittest.main()
