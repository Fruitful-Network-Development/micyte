"""One magnitude per artifact cannot hold a file, and the reason is a hard limit.

Plan P5 gives the artifact row shape as ONE row per document — ``1-1-1 [0-0-12,
<magnitude>]`` — with the file's bytes as a single integer magnitude. Measured
2026-08-23, that shape cannot carry the pool it was designed for.

TWO SEPARATE PROBLEMS, and the first is absolute:

1. CPython refuses ``str(int)`` above ``sys.get_int_max_str_digits()``, 4300 by default.
   A magnitude is written to JSON as a decimal string, so **a file larger than ~1785
   bytes cannot be serialised as one magnitude at all** — it raises ValueError, it does
   not merely get slow. The pool P5 migrates is 956 files averaging 136 KiB.

2. Raising the limit trades a refusal for a cliff. int<->str is superlinear and the
   exponent RISES with size — measured O(n^1.10) at 4->64 KiB, O(n^1.30) at 64->256,
   O(n^1.43) at 256->1024. One 1 MiB file costs ~3.1 s to write and ~4.6 s to read.

THE CORPUS IS ALREADY UP AGAINST THIS. 26 live magnitudes across 12 documents exceed the
4300-digit default today, the longest at 89,947 digits (~37 KB of source), and they sit in
ANCHORS and ANTHOLOGIES. They work only because JSON keeps a magnitude as a STRING —
nothing trips until something calls `int()` or `str(int)`. The portal runs at the default
and never converts; `recompile_datum_semantics.py` does convert, and raises the limit
process-globally to cope. So the ceiling is not hypothetical, it is being worked around.

CHUNKING FIXES BOTH, and this file pins that it does: bounded rows are linear (4x the
data costs exactly 4x the time), byte-exact, and stay under the default limit with room
to spare. 1 MiB round-trips in ~190 ms chunked against ~7.8 s as one integer.

What chunking does NOT fix is the 2.41x storage ratio, and nothing will: a byte is 8
bits and a decimal digit is log2(10), so decimal costs 8/log2(10) = 2.41 characters per
source byte however it is sliced. That is a fact about the representation, not a
tunable, and 127 MB of artifacts is ~306 MB of digits whatever the chunk size.
"""

from __future__ import annotations

import math
import os
import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from micyte.core.mss.magnitude import decode_magnitude, encode_magnitude

#: Bytes per artifact row. 1 KiB encodes to ~2466 decimal digits — comfortably under the
#: 4300-digit default, with headroom for an interpreter that lowers it rather than a value
#: chosen to sit just inside today's.
ARTIFACT_CHUNK_BYTES = 1024

#: The default CPython refuses to print above. Not ours to rely on being raised: a
#: migration that needs `sys.set_int_max_str_digits` has made every future reader of those
#: rows depend on a process-global somebody has to remember to set.
DEFAULT_INT_STR_DIGIT_LIMIT = 4300


def _as_one_magnitude(blob: bytes) -> str:
    _kind, magnitude = encode_magnitude(int.from_bytes(blob, "big"))
    return str(magnitude)          # the JSON write path, and where it raises


def _chunk_rows(blob: bytes, chunk: int = ARTIFACT_CHUNK_BYTES):
    for start in range(0, len(blob), chunk):
        piece = blob[start:start + chunk]
        kind, magnitude = encode_magnitude(int.from_bytes(piece, "big"))
        yield kind, str(magnitude), len(piece)


def _from_rows(rows) -> bytes:
    out = bytearray()
    for kind, magnitude, width in rows:
        out += decode_magnitude(kind, int(magnitude)).to_bytes(width, "big")
    return bytes(out)


class OneMagnitudeCannotHoldAFile(unittest.TestCase):
    """Pinned at the DEFAULT limit, set here rather than assumed.

    The first version of this asserted `sys.get_int_max_str_digits() == 4300` and passed
    alone, then failed in CI — because the limit is process-global mutable state and this
    repo mutates it: `fnd_app/scripts/recompile_datum_semantics.py` calls
    `set_int_max_str_digits(1_000_000)` at import, "some live magnitudes are 11k+ digits".
    Collecting that module raises the ceiling for every test after it.

    So the assertion was reading a global that another test had already changed, which is
    the same mistake as reading a live value and calling it a constant. Set it, test the
    PROPERTY, put it back.
    """

    def setUp(self) -> None:
        self._prior_limit = sys.get_int_max_str_digits()
        sys.set_int_max_str_digits(DEFAULT_INT_STR_DIGIT_LIMIT)

    def tearDown(self) -> None:
        sys.set_int_max_str_digits(self._prior_limit)

    def test_a_small_payload_still_fits_in_one_magnitude(self) -> None:
        self.assertTrue(_as_one_magnitude(os.urandom(1024)))

    def test_a_file_of_any_real_size_RAISES(self) -> None:
        """Not slow — refused. 8 KiB is smaller than anything in the artifact pool."""
        with self.assertRaises(ValueError):
            _as_one_magnitude(os.urandom(8 * 1024))

    def test_the_ceiling_is_under_two_kilobytes(self) -> None:
        """~1785 bytes, and the pool averages 136 KiB — so the shape misses by ~78x."""
        self.assertTrue(_as_one_magnitude(os.urandom(1785)))
        with self.assertRaises(ValueError):
            _as_one_magnitude(os.urandom(1900))


class ChunkedRowsCarryIt(unittest.TestCase):
    def test_a_chunk_stays_well_under_the_limit(self) -> None:
        digits = len(str(encode_magnitude(int.from_bytes(
            os.urandom(ARTIFACT_CHUNK_BYTES), "big"))[1]))
        self.assertLess(digits, DEFAULT_INT_STR_DIGIT_LIMIT)
        # Headroom, not a value that merely fits today.
        self.assertLess(digits, DEFAULT_INT_STR_DIGIT_LIMIT * 0.7)

    def test_a_megabyte_round_trips_BYTE_EXACT(self) -> None:
        blob = os.urandom(1024 * 1024)
        self.assertEqual(_from_rows(_chunk_rows(blob)), blob)

    def test_a_partial_final_chunk_survives_leading_zero_bytes(self) -> None:
        """The failure a width-less decode would have: `int` forgets leading zeros.

        A chunk of b'\\x00\\x00\\x07' is the integer 7, and 7 decoded without its WIDTH is
        one byte. Every row therefore carries how many bytes it stood for.
        """
        blob = b"\x00\x00\x07" + os.urandom(ARTIFACT_CHUNK_BYTES) + b"\x00"
        self.assertEqual(_from_rows(_chunk_rows(blob)), blob)

    def test_an_empty_artifact_round_trips(self) -> None:
        self.assertEqual(_from_rows(_chunk_rows(b"")), b"")

    def test_cost_is_LINEAR_in_the_size(self) -> None:
        """The property that makes the pool migratable: 4x the data, ~4x the work.

        Timing in a test is ordinarily a smell. Here the whole point is a complexity
        CLASS, so the assertion is deliberately loose — it fails on a return to
        superlinear growth, not on a slow machine.

        It failed on a BUSY one, in the gate on 2026-08-26, at O(n^1.29). A single
        measurement per size means one scheduling hiccup on either sample moves the
        exponent, and the two samples are taken seconds apart, so they are not even
        contending with the same load. It passed 5/5 immediately afterwards on an idle
        machine.

        So each size is now the MINIMUM of three runs. Minimum is the right statistic for
        a timing sample: contention and preemption can only ever add time, so the smallest
        observation is the one least contaminated by whatever else the box was doing. The
        mean would import the noise the docstring above already promised to exclude.
        """
        import time

        def milliseconds(size: int) -> float:
            blob = os.urandom(size)

            def once() -> float:
                start = time.perf_counter()
                _from_rows(_chunk_rows(blob))
                return (time.perf_counter() - start) * 1000

            return min(once() for _ in range(3))

        small = milliseconds(256 * 1024)
        large = milliseconds(1024 * 1024)
        exponent = math.log(max(large, 0.001) / max(small, 0.001)) / math.log(4)
        self.assertLess(
            exponent, 1.25,
            f"chunked encoding grew as O(n^{exponent:.2f}); one magnitude per file was "
            "O(n^1.43) and rising, which is the shape this replaces")


class TheStorageRatioIsNotTunable(unittest.TestCase):
    def test_decimal_costs_2_41_characters_per_source_byte(self) -> None:
        """8 bits per byte / log2(10) bits per digit = 2.41, at every chunk size.

        Worth pinning because it is the number the migration is budgeted against: 127 MB
        of artifacts is ~306 MB of digits, and no chunk size changes that.
        """
        blob = os.urandom(128 * 1024)
        # 256/512/1024 and NOT 4096: a 4 KiB chunk is ~9864 digits, over the 4300 limit.
        # The first draft of this test used it and raised — the ceiling above applies to
        # the chunk size too, which is exactly why ARTIFACT_CHUNK_BYTES is 1 KiB and not
        # "as large as convenient".
        for chunk in (256, 512, 1024):
            with self.subTest(chunk=chunk):
                digits = sum(len(m) for _kind, m, _w in _chunk_rows(blob, chunk))
                self.assertAlmostEqual(digits / len(blob), 8 / math.log2(10), places=1)


if __name__ == "__main__":
    unittest.main()
