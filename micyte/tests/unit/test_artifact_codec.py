"""A file whose bytes ARE its rows — encode, decode, and the ways it must refuse.

The properties that matter, in order of how badly they fail:

  * BYTE-EXACT. Anything less makes an artifact store worthless, and the failure is
    invisible: a file that comes back 3 bytes short still opens for most formats.
  * REFUSES a row it did not write, rather than skipping it. A skipped row is a hole,
    and a decoder that drops one returns a plausible artifact of the wrong length.
  * Every row carries its WIDTH, because `int` forgets leading zeros.
  * Since 2026-09-08 the document DECLARES itself first: three header rows — the size as a
    magnitude on the anchor's Boolean parent, then 1, then 0 — before the chunked payload.
    A zero-byte file is three header rows and nothing else.
"""

from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from micyte.core.datum_ops.artifact import (
    ARTIFACT_ROW_PREFIX,
    CHUNK_BYTES,
    HEADER_ROWS,
    ONE_ADDRESS,
    SIZE_ADDRESS,
    ZERO_ADDRESS,
    artifact_digest,
    declared_size,
    decode_artifact,
    encode_artifact,
    header_rows,
    round_trips,
)

DEFAULT_INT_STR_DIGIT_LIMIT = 4300
#: The anchor row the header chain references (`nominal-bacillete-2`); its address is a
#: fact about the anchor, which is why the codec takes it rather than assuming it.
BOOLEAN_PARENT = "1-1-41"


def _rows(blob: bytes, **kw):
    kw.setdefault("boolean_parent", BOOLEAN_PARENT)
    return [row for _address, row in encode_artifact(blob, **kw)]


def _payload(blob: bytes, **kw):
    """The chunk rows alone — what follows the three-row header."""
    return _rows(blob, **kw)[HEADER_ROWS:]


class ItRoundTrips(unittest.TestCase):
    def test_random_payloads_of_every_shape(self) -> None:
        for size in (0, 1, CHUNK_BYTES - 1, CHUNK_BYTES, CHUNK_BYTES + 1,
                     3 * CHUNK_BYTES, 64 * 1024):
            with self.subTest(size=size):
                blob = os.urandom(size)
                self.assertTrue(round_trips(blob, boolean_parent=BOOLEAN_PARENT),
                                f"{size} bytes did not round-trip")

    def test_leading_zero_bytes_survive(self) -> None:
        """The bug the WIDTH cell exists for.

        b"\\x00\\x00\\x07" is the integer 7. Decoded without a width it is ONE byte, so the
        artifact returns short — and only for files with a zero byte at a chunk boundary,
        which is the kind of defect that reaches production.
        """
        for blob in (b"\x00", b"\x00" * CHUNK_BYTES,
                     b"\x00\x00\x07" + os.urandom(CHUNK_BYTES),
                     os.urandom(CHUNK_BYTES) + b"\x00" * 5):
            with self.subTest(blob=len(blob)):
                self.assertEqual(decode_artifact(_rows(blob)), blob)

    def test_an_empty_artifact_is_its_header_and_NO_payload(self) -> None:
        """A zero-byte file is a real state. Inventing a payload row for it would make the
        round trip lossy in the direction nobody checks — but the document still says
        what it is: a binary value of size 0."""
        rows = encode_artifact(b"", boolean_parent=BOOLEAN_PARENT)
        self.assertEqual(rows, header_rows(0, boolean_parent=BOOLEAN_PARENT))
        self.assertEqual(len(rows), HEADER_ROWS)
        self.assertEqual(decode_artifact([row for _a, row in rows]), b"")
        self.assertEqual(declared_size([row for _a, row in rows]), 0)
        self.assertEqual(decode_artifact([]), b"")

    def test_the_header_chain_comes_first_then_the_payload_in_order(self) -> None:
        blob = os.urandom(3 * CHUNK_BYTES)
        addresses = [a for a, _row in encode_artifact(blob, boolean_parent=BOOLEAN_PARENT)]
        self.assertEqual(
            addresses,
            [SIZE_ADDRESS, ONE_ADDRESS, ZERO_ADDRESS,
             f"{ARTIFACT_ROW_PREFIX}1", f"{ARTIFACT_ROW_PREFIX}2", f"{ARTIFACT_ROW_PREFIX}3"])
        rows = _rows(blob)
        self.assertEqual(rows[0][0], BOOLEAN_PARENT, "the size row references the Boolean parent")
        self.assertEqual(int(rows[0][1]), len(blob), "and its magnitude IS the size")
        self.assertEqual(declared_size(rows), len(blob))


class ItStaysUnderTheDigitLimit(unittest.TestCase):
    """The whole reason for chunking, pinned at the DEFAULT rather than the ambient limit.

    `sys.get_int_max_str_digits()` is process-global and this repo raises it
    (`recompile_datum_semantics.py`, at import). A test that read the ambient value would
    pass or fail on collection order.
    """

    def setUp(self) -> None:
        self._prior = sys.get_int_max_str_digits()
        sys.set_int_max_str_digits(DEFAULT_INT_STR_DIGIT_LIMIT)

    def tearDown(self) -> None:
        sys.set_int_max_str_digits(self._prior)

    def test_a_megabyte_encodes_at_the_default_limit(self) -> None:
        """As one magnitude this raises. That is the point of the codec."""
        self.assertTrue(round_trips(os.urandom(1024 * 1024), boolean_parent=BOOLEAN_PARENT))

    def test_every_magnitude_has_headroom(self) -> None:
        widest = max(len(row[2]) for row in _payload(os.urandom(256 * 1024)))
        self.assertLess(widest, DEFAULT_INT_STR_DIGIT_LIMIT * 0.7, widest)


class ItRefusesWhatItDidNotWrite(unittest.TestCase):
    def test_a_row_chained_elsewhere_is_REFUSED(self) -> None:
        """Not an artifact row. Decoding it as one would invent bytes from a magnitude
        that means something else entirely.

        A payload row is [chain, kind, magnitude, width], and the chain is what says
        "octets": it references the header's 0-row, which references the 1-row, which
        references the size on the anchor's Boolean parent. Before the chain (until
        2026-09-08) the row named the octet rudi directly and this test moved that cell;
        now the chain cell is the one that means it."""
        rows = _rows(os.urandom(64))
        first = HEADER_ROWS                          # the first PAYLOAD row
        rows[first] = ["0-0-4", *rows[first][1:]]    # chained at the spatial rudi instead
        with self.assertRaises(ValueError) as caught:
            decode_artifact(rows)
        self.assertIn(ZERO_ADDRESS, str(caught.exception))

    def test_a_row_of_the_wrong_arity_is_REFUSED(self) -> None:
        """Two cells is a header row and four a chunk; three is neither."""
        rows = _rows(os.urandom(64))
        rows[HEADER_ROWS] = rows[HEADER_ROWS][:3]
        with self.assertRaises(ValueError):
            decode_artifact(rows)

    def test_it_does_not_SKIP_a_bad_row(self) -> None:
        """Stated separately because skipping is the tempting failure.

        A dropped row is a hole in a file. The artifact would decode, be the wrong length,
        and nothing would say so.
        """
        good = os.urandom(3 * CHUNK_BYTES)
        rows = _rows(good)
        middle = HEADER_ROWS + 1
        rows[middle] = ["0-0-4", *rows[middle][1:]]
        with self.assertRaises(ValueError):
            decode_artifact(rows)


class TheDigestIsOverTheSourceBytes(unittest.TestCase):
    def test_the_chunk_size_does_not_change_the_identity(self) -> None:
        """A digest over the ROWS would change when the chunk parameter did, and stop
        meaning "this is the same file" — which is the one thing a migration proves."""
        blob = os.urandom(8 * 1024)
        self.assertEqual(artifact_digest(blob), artifact_digest(blob))
        self.assertTrue(round_trips(blob, boolean_parent=BOOLEAN_PARENT, chunk=256))
        self.assertTrue(round_trips(blob, boolean_parent=BOOLEAN_PARENT, chunk=CHUNK_BYTES))

    def test_two_different_files_differ(self) -> None:
        self.assertNotEqual(artifact_digest(b"a"), artifact_digest(b"b"))


if __name__ == "__main__":
    unittest.main()
