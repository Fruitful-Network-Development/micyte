"""Tests for the bacillete encoders (name-babelette, email-babellette)."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from micyte.core.datum_templates.bacillete import (
    EMAIL_BABELLETTE_ASCII_BYTE_LIMIT,
    NAME_BABELETTE_BYTE_LIMIT,
    decode_email_bacillete,
    decode_name_bacillete,
    encode_email_bacillete,
    encode_name_bacillete,
)


class NameBacilleteTests(unittest.TestCase):
    def test_round_trip_ascii_within_limit(self):
        encoded, confirmed = encode_name_bacillete("Mary Zaun")
        self.assertTrue(confirmed)
        self.assertEqual(decode_name_bacillete(encoded), "Mary Zaun")

    def test_empty_value_is_unconfirmed(self):
        encoded, confirmed = encode_name_bacillete("")
        self.assertFalse(confirmed)
        self.assertEqual(encoded, "")

    def test_overlong_name_is_truncated_and_unconfirmed(self):
        value = "x" * (NAME_BABELETTE_BYTE_LIMIT + 5)
        encoded, confirmed = encode_name_bacillete(value)
        self.assertFalse(confirmed)
        self.assertEqual(decode_name_bacillete(encoded), "x" * NAME_BABELETTE_BYTE_LIMIT)

    def test_non_ascii_is_unconfirmed_but_strips_to_recoverable_form(self):
        encoded, confirmed = encode_name_bacillete("Müller")
        self.assertFalse(confirmed)
        # ü is dropped; we still get a sensible decoded fallback
        self.assertEqual(decode_name_bacillete(encoded), "Mller")


class EmailBacilleteTests(unittest.TestCase):
    def test_round_trip_simple_email(self):
        encoded, confirmed = encode_email_bacillete("dylan@fnd.example.com")
        self.assertTrue(confirmed)
        self.assertEqual(decode_email_bacillete(encoded), "dylan@fnd.example.com")
        # Three octal digits per ASCII byte
        self.assertEqual(len(encoded), 3 * len("dylan@fnd.example.com"))

    def test_email_at_byte_limit_still_confirms(self):
        local = "a" * 50
        domain = "b" * (EMAIL_BABELLETTE_ASCII_BYTE_LIMIT - len(local) - len("@.x"))
        value = f"{local}@{domain}.x"
        self.assertEqual(len(value), EMAIL_BABELLETTE_ASCII_BYTE_LIMIT)
        _, confirmed = encode_email_bacillete(value)
        self.assertTrue(confirmed)

    def test_overlong_email_is_unconfirmed(self):
        value = "a" * (EMAIL_BABELLETTE_ASCII_BYTE_LIMIT + 5) + "@x.com"
        _, confirmed = encode_email_bacillete(value)
        self.assertFalse(confirmed)

    def test_non_ascii_email_is_unconfirmed(self):
        _, confirmed = encode_email_bacillete("üser@example.com")
        self.assertFalse(confirmed)

    def test_empty_value_unconfirmed(self):
        encoded, confirmed = encode_email_bacillete("")
        self.assertEqual(encoded, "")
        self.assertFalse(confirmed)

    def test_decoded_octal_treats_invalid_chunks_gracefully(self):
        # Encode "ab@x.com" then corrupt the chunk for 'b' (positions 3-5).
        # The corrupt chunk is dropped; the remaining characters round-trip.
        encoded, _ = encode_email_bacillete("ab@x.com")
        corrupted = encoded[:3] + "9zz" + encoded[6:]
        self.assertEqual(decode_email_bacillete(corrupted), "a@x.com")


if __name__ == "__main__":
    unittest.main()
