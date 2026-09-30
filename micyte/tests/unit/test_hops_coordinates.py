from __future__ import annotations

import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from micyte.core.structures.hops import (
    classify_hops_coordinate_token,
    decode_hops_coordinate_token,
)


class HopsCoordinateUnitTests(unittest.TestCase):
    def test_decodes_current_numeric_hyphen_hops_token(self) -> None:
        token = "3-76-11-40-92-20-21-92-51-75-26-64-11-48-77-78-73"

        classification = classify_hops_coordinate_token(token)
        decoded = decode_hops_coordinate_token(token)

        self.assertEqual(classification["classification"], "hops")
        self.assertIsNotNone(decoded)
        self.assertEqual(decoded["encoding"], "hops_mixed_radix")
        self.assertEqual(decoded["address"], token)
        self.assertEqual(len(decoded["pair_text"]), 2)
        self.assertGreaterEqual(decoded["longitude"]["value"], -180.0)
        self.assertLessEqual(decoded["longitude"]["value"], 180.0)
        self.assertGreaterEqual(decoded["latitude"]["value"], -90.0)
        self.assertLessEqual(decoded["latitude"]["value"], 90.0)

    def test_numeric_hex_like_token_is_not_marked_ambiguous(self) -> None:
        token = "3-76-11-43-4-38-94-37-98-16-59-86-18-18-80-85-0-5"

        classification = classify_hops_coordinate_token(token)

        self.assertEqual(classification["classification"], "hops")

    def test_rejects_ambiguous_hyphenated_hex_token(self) -> None:
        classification = classify_hops_coordinate_token("aa-bb")
        decoded = decode_hops_coordinate_token("aa-bb")

        self.assertEqual(classification["classification"], "ambiguous")
        self.assertIsNone(decoded)

    def test_rejects_out_of_bounds_hops_segment(self) -> None:
        classification = classify_hops_coordinate_token("8-0-0")
        decoded = decode_hops_coordinate_token("8-0-0")

        self.assertEqual(classification["classification"], "invalid")
        self.assertIsNone(decoded)


if __name__ == "__main__":
    unittest.main()
