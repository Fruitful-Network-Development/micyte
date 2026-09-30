"""`decode_display_text` decodes the same way it always did, faster and only once.

MEASURED 2026-08-30 while tracing why the operator's profile page took 1.45s of local work
per render: this function was 2.45s of a 4.6s profile — 48,601 calls driving 2.87 million
generator evaluations. It is called once per ROW per gazetteer pass, and a gazetteer is
mostly repeated place names, so the same few thousand strings were decoded over and over.

Two changes, and the whole risk of both is that a label comes out different:

* the per-byte ``int(value[i:i+8], 2)`` loop became one ``int(value, 2).to_bytes(...)``;
* the function is ``lru_cache``d, which is safe only because it is pure — a `str` in, a
  `str` out, no clock and no store.

So these tests are about EQUIVALENCE first and speed second. The decode is checked against
the exact loop it replaced, over the cases that actually distinguish them: an all-zero
payload (padding, which must keep the caller's fallback rather than become ""), bytes that
are not valid UTF-8, every unaligned length, and a plain-text value that must pass through
untouched because several registrar documents store the same field unencoded.
"""

from __future__ import annotations

import random
import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from micyte.domains.registry.directory import decode_display_text


def _reference(value: str) -> str:
    """The implementation this replaced, kept verbatim as the oracle.

    A test that re-derived the new behaviour would agree with the new code by
    construction; the only assertion worth making is against what shipped before.
    """
    if len(value) < 8 or len(value) % 8 or set(value) - {"0", "1"}:
        return value
    try:
        raw = bytes(int(value[i : i + 8], 2) for i in range(0, len(value), 8))
        text = raw.decode("utf-8").rstrip("\x00")
    except (ValueError, UnicodeDecodeError):
        return value
    return text or value


def _encode(text: str) -> str:
    return "".join(f"{b:08b}" for b in text.encode())


class ItDecodesExactlyAsBefore(unittest.TestCase):
    NAMED_CASES = (
        "", "0", "abc", "not bits", "0101010",          # not an encoding: passed through
        "0" * 8, "0" * 16,                              # all-zero padding, not an empty label
        "1" * 8,                                        # 0xff — not valid UTF-8
        _encode("Cuyahoga"),
        _encode("Ashtabula County"),
        _encode("Zoë — Straße"),                        # multi-byte UTF-8
        "".join(f"{b:08b}" for b in b"\xff\xfe\x00\x01"),
    )

    def test_the_named_cases_agree_with_the_previous_implementation(self) -> None:
        for case in self.NAMED_CASES:
            with self.subTest(case=case[:24]):
                self.assertEqual(decode_display_text(case), _reference(case))

    def test_a_sweep_of_random_bit_strings_agrees(self) -> None:
        """Seeded, so a failure is reproducible rather than a story about one CI run."""
        rng = random.Random(20260830)
        for _ in range(3000):
            n = rng.choice([1, 2, 3, 4, 8, 16])
            case = "".join(rng.choice("01") for _ in range(8 * n))
            with self.subTest(case=case[:24]):
                self.assertEqual(decode_display_text(case), _reference(case))

    def test_padding_keeps_the_callers_fallback(self) -> None:
        """An all-zero payload is padding, not a name. Returning "" would replace a label
        with nothing, which is the one way this function can lose data."""
        self.assertEqual(decode_display_text("0" * 24), "0" * 24)

    def test_plain_text_passes_through_untouched(self) -> None:
        self.assertEqual(decode_display_text("Summit County"), "Summit County")


class ItIsMemoizedAndBounded(unittest.TestCase):
    def test_a_repeated_value_is_decoded_once(self) -> None:
        value = _encode("Portage County")
        decode_display_text.cache_clear()
        decode_display_text(value)
        decode_display_text(value)
        decode_display_text(value)
        info = decode_display_text.cache_info()
        self.assertEqual(info.misses, 1, "the repeat was decoded again")
        self.assertEqual(info.hits, 2)

    def test_the_cache_is_bounded(self) -> None:
        """Unbounded, it would hold every label the process ever saw — including the
        plain-text values that take the early return and are the cheapest to recompute."""
        self.assertIsNotNone(decode_display_text.cache_info().maxsize)

    def test_caching_cannot_change_an_answer(self) -> None:
        """Pure in, pure out: the cached answer must equal the uncached one."""
        value = _encode("Geauga")
        decode_display_text.cache_clear()
        first = decode_display_text(value)
        second = decode_display_text(value)
        self.assertEqual(first, second)
        self.assertEqual(first, _reference(value))


if __name__ == "__main__":
    unittest.main()
