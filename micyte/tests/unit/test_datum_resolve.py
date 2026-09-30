"""datum_resolve primitives — decode_label edge cases + bounded cached_index.

Pins the consolidation-spine behavior surfaced by the 2026-06-16 review:

* ``decode_label`` returns "" for an empty / all-zero (NUL-terminated) babelette and
  DROPS non-printable control bytes — this is the INTENDED behavior (an unset weight
  decodes to "" → 0.0, not the old BinaryTextLens "{N} bits" sentinel that
  ``_parse_weight`` mis-parsed as a numeric weight). A clean ASCII babelette round-trips;
  non-binary or non-byte-aligned input is returned verbatim.
* ``_INDEX_CACHE`` is bounded (FIFO eviction) so superseded content-hash document_ids do
  not accumulate unboundedly over the portal's process lifetime.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from micyte.core.datum_ops import datum_resolve
from micyte.core.datum_ops.datum_resolve import (
    Markers,
    cached_index,
    decode_label,
    encode_label,
    rewrite_title,
)


def _bits(text: str) -> str:
    return "".join(format(b, "08b") for b in text.encode("ascii"))


def _title_head(node: str = "1", *, addr: str = "4-2-1") -> list:
    """A canonical definition head: [addr, NODE_ID, node, TITLE, <blob>]."""
    return [addr, Markers.NODE_ID, node, Markers.TITLE, encode_label("brassica")]


class TestDecodeLabel(unittest.TestCase):
    def test_clean_ascii_roundtrips(self) -> None:
        self.assertEqual(decode_label(encode_label("25 lbs")), "25 lbs")
        self.assertEqual(decode_label(_bits("brassica")), "brassica")

    def test_empty_and_all_zero_decode_to_empty(self) -> None:
        # An unset weight (all-zero / NUL-terminated blob) is "", NOT the old
        # BinaryTextLens "{N} bits" sentinel that _parse_weight mis-read as a number.
        self.assertEqual(decode_label(""), "")
        self.assertEqual(decode_label("0" * 512), "")
        self.assertEqual(decode_label("0" * 136), "")

    def test_control_bytes_are_dropped_not_sentineled(self) -> None:
        # "AB" then a TAB (0x09) control byte: printable kept, control dropped.
        blob = _bits("AB") + format(9, "08b")
        self.assertEqual(decode_label(blob), "AB")

    def test_non_binary_or_unaligned_returned_verbatim(self) -> None:
        self.assertEqual(decode_label("25 lbs"), "25 lbs")   # not all 0/1
        self.assertEqual(decode_label("0101010"), "0101010")  # len % 8 != 0


class TestCachedIndexBounded(unittest.TestCase):
    def test_cache_is_bounded(self) -> None:
        class _Doc:
            def __init__(self, did: str) -> None:
                self.document_id = did
                self.rows: tuple = ()

        datum_resolve._INDEX_CACHE.clear()
        try:
            for i in range(datum_resolve._INDEX_CACHE_MAX * 2):
                cached_index(_Doc(f"lv.x.example_family_farm.doc.{i:064d}"))
            self.assertLessEqual(
                len(datum_resolve._INDEX_CACHE), datum_resolve._INDEX_CACHE_MAX
            )
        finally:
            datum_resolve._INDEX_CACHE.clear()


class TestRewriteTitle(unittest.TestCase):
    """The shared lock-step retitle codec (single-sources the two write paths)."""

    def test_reencodes_head_and_syncs_tail(self) -> None:
        raw = [_title_head(), ["brassica"]]
        new_raw = rewrite_title(raw, "kale")
        head, tail = new_raw[0], new_raw[1]
        self.assertEqual(head[4], encode_label("kale"))
        self.assertEqual(decode_label(head[4]), "kale")
        self.assertEqual(tail, ["kale"])
        # other head slots are untouched
        self.assertEqual(head[:4], _title_head()[:4])

    def test_preserves_tail_siblings_and_raw_sidecar(self) -> None:
        # Regression: the prior [head, [label]] rebuild dropped tail[1:] and raw[2:].
        raw = [_title_head(), ["brassica", "aux_echo"], {"meta": "x"}]
        new_raw = rewrite_title(raw, "kale")
        self.assertEqual(new_raw[1], ["kale", "aux_echo"])  # tail sibling kept
        self.assertEqual(new_raw[2], {"meta": "x"})          # sidecar kept
        self.assertEqual(len(new_raw), 3)

    def test_marker_only_walk_ignores_title_token_in_magnitude_slot(self) -> None:
        # A magnitude (even slot) literally equal to the TITLE marker must NOT be
        # mistaken for the marker; only the real odd-slot marker drives the rewrite.
        head = ["4-2-1", Markers.NODE_ID, Markers.TITLE, Markers.TITLE, encode_label("brassica")]
        new_raw = rewrite_title([head, ["brassica"]], "kale")
        self.assertEqual(new_raw[0][2], Markers.TITLE)        # data slot untouched
        self.assertEqual(decode_label(new_raw[0][4]), "kale")  # real title slot rewritten

    def test_refuses_record_dict_tail(self) -> None:
        # A record-shape (dict-tail) row must be refused, never converted to a list.
        raw = [_title_head(), {"weight": "10"}]
        with self.assertRaises(ValueError) as ctx:
            rewrite_title(raw, "kale")
        self.assertEqual(str(ctx.exception), "not_a_title_row")

    def test_refuses_row_without_title_marker(self) -> None:
        raw = [["4-2-1", Markers.NODE_ID, "1"], ["x"]]
        with self.assertRaises(ValueError) as ctx:
            rewrite_title(raw, "kale")
        self.assertEqual(str(ctx.exception), "title_slot_missing")

    def test_over_long_label_is_title_invalid(self) -> None:
        with self.assertRaises(ValueError) as ctx:
            rewrite_title([_title_head(), ["brassica"]], "x" * 65)
        self.assertIn("title_invalid", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
