from __future__ import annotations

import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from micyte.state_machine.lens import BinaryTextLens, resolve_datum_lens


class StateMachineLensRegistryTests(unittest.TestCase):
    def test_binary_text_lens_decodes_printable_ascii(self) -> None:
        self.assertEqual(BinaryTextLens().decode("0100000101000010"), "AB")

    def test_registry_prefers_family_then_value_kind(self) -> None:
        self.assertEqual(
            resolve_datum_lens(recognized_family="nominal_babelette").lens_id,
            "binary_text",
        )
        self.assertEqual(
            resolve_datum_lens(primary_value_kind="numeric_hyphen").lens_id,
            "numeric_hyphen",
        )


if __name__ == "__main__":
    unittest.main()
