from __future__ import annotations

import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from micyte.state_machine.nimm import (
    NIMM_DIRECTIVE_TEXT_FORMAT,
    NIMM_VERB_FRAME_ENGAGEMENT,
    SUPPORTED_NIMM_VERBS,
    parse_directive_text,
)


class ParseDirectiveTextTests(unittest.TestCase):
    def test_canonical_verbs_accepted(self) -> None:
        cases = [
            ("navigate;cts_gis:1-1-2", "navigate", "cts_gis:1-1-2"),
            ("investigate;cts_gis:1-1-2", "investigate", "cts_gis:1-1-2"),
            ("mediate;cts_gis:1-1-2", "mediate", "cts_gis:1-1-2"),
            ("manipulate;cts_gis:1-1-2", "manipulate", "cts_gis:1-1-2"),
        ]
        for text, expected_verb, expected_target in cases:
            with self.subTest(text=text):
                result = parse_directive_text(text)
                self.assertEqual(result["verb"], expected_verb)
                self.assertEqual(result["target_text"], expected_target)
                self.assertEqual(result["raw"], text)

    def test_minimal_aliases_normalized(self) -> None:
        cases = [
            ("nav;x:y", "navigate"),
            ("inv;x:y", "investigate"),
            ("med;cts_gis:1-1-2", "mediate"),
            ("man;x:y", "manipulate"),
        ]
        for text, expected_verb in cases:
            with self.subTest(text=text):
                result = parse_directive_text(text)
                self.assertEqual(result["verb"], expected_verb)

    def test_raw_preserved(self) -> None:
        text = "med;cts_gis:3-2-3-17"
        result = parse_directive_text(text)
        self.assertEqual(result["raw"], text)

    def test_target_text_stripped(self) -> None:
        result = parse_directive_text("med;  cts_gis:1  ")
        self.assertEqual(result["target_text"], "cts_gis:1")

    def test_empty_raises(self) -> None:
        with self.assertRaises(ValueError) as ctx:
            parse_directive_text("")
        self.assertIn("empty", str(ctx.exception).lower())

    def test_whitespace_only_raises(self) -> None:
        with self.assertRaises(ValueError) as ctx:
            parse_directive_text("   ")
        self.assertIn("empty", str(ctx.exception).lower())

    def test_missing_semicolon_raises(self) -> None:
        with self.assertRaises(ValueError) as ctx:
            parse_directive_text("med cts_gis:1-1-2")
        self.assertIn("Invalid directive format", str(ctx.exception))

    def test_unknown_verb_raises(self) -> None:
        with self.assertRaises(ValueError) as ctx:
            parse_directive_text("jump;cts_gis:1-1-2")
        msg = str(ctx.exception)
        self.assertTrue(
            any(v in msg for v in ("navigate", "mediate", "nav", "med")),
            f"Expected supported verb list in error message, got: {msg}",
        )

    def test_verb_case_insensitive(self) -> None:
        result = parse_directive_text("MED;cts_gis:1-1-2")
        self.assertEqual(result["verb"], "mediate")


class NimmVerbFrameEngagementTests(unittest.TestCase):
    def test_all_canonical_verbs_present(self) -> None:
        for verb in SUPPORTED_NIMM_VERBS:
            self.assertIn(
                verb,
                NIMM_VERB_FRAME_ENGAGEMENT,
                f"Canonical verb {verb!r} missing from NIMM_VERB_FRAME_ENGAGEMENT",
            )

    def test_mediate_engages_profile_frame(self) -> None:
        self.assertEqual(
            NIMM_VERB_FRAME_ENGAGEMENT["mediate"],
            "administrative_node_profile",
        )

    def test_non_mediate_verbs_have_no_engagement(self) -> None:
        for verb in ("navigate", "investigate", "manipulate"):
            self.assertEqual(
                NIMM_VERB_FRAME_ENGAGEMENT[verb],
                "",
                f"Expected empty engagement for verb {verb!r}",
            )


class NimmDirectiveTextFormatTests(unittest.TestCase):
    def test_format_constant_is_nonempty_string(self) -> None:
        self.assertIsInstance(NIMM_DIRECTIVE_TEXT_FORMAT, str)
        self.assertTrue(NIMM_DIRECTIVE_TEXT_FORMAT)

    def test_format_constant_referenced_in_error_message(self) -> None:
        try:
            parse_directive_text("med cts_gis")
        except ValueError as exc:
            self.assertIn(NIMM_DIRECTIVE_TEXT_FORMAT, str(exc))
        else:
            self.fail("Expected ValueError for missing semicolon")


if __name__ == "__main__":
    unittest.main()
