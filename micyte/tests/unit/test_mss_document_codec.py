"""Binary MSS document codec — round-trip + anthology-shape validation.

The codec implements the firm MSS rules (docs/contracts/mss_binary_sequence/) with
a clean, documented bit grammar (MSS-DOC.v1). Correctness is proven by exhaustive
encode→decode round-trips and by reproducing the anthology structure (rudis +
VG1 + a VG2 multi-tuple datum) from the recovered worked example.
"""

from __future__ import annotations

import random
import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from micyte.core.mss.document_codec import (
    MssDatum,
    MssFormatError,
    MssTuple,
    decode_document,
    encode_document,
    mss_document_hash,
    reindex_into_isolated_anthology,
)
from micyte.core.mss.magnitude import encode_magnitude


def T(ref: str, token: object = 0) -> MssTuple:
    """A tuple carrying ``token`` through the injective v3 magnitude codec.

    v3 pairs every magnitude with a KIND discriminator so the original token is
    recoverable, not merely comparable — these tests therefore build tuples
    through the codec rather than hand-packing an integer.
    """
    return MssTuple(ref, *encode_magnitude(token))


def _norm(datums: list[MssDatum]) -> list[tuple]:
    """Comparable normal form: (address, sorted refs, sorted tuples)."""
    out = []
    for d in sorted(datums, key=lambda x: (x.layer, x.value_group, x.iteration)):
        out.append((d.address, tuple(d.refs), tuple(d.tuples)))
    return out


def _random_canonical_document(rng: random.Random) -> list[MssDatum]:
    """Generate a valid canonical document. v2: arity (refs / tuples) is chosen
    INDEPENDENTLY of value_group (value_group is just the address segment). Layers
    are contiguous from 0; refs point strictly downward."""
    datums: list[MssDatum] = []
    by_layer: dict[int, list[str]] = {}
    layer_count = rng.randint(1, 4)
    for layer in range(layer_count):
        by_layer[layer] = []
        lower = [a for ll in range(layer) for a in by_layer[ll]]
        value_groups = [0] if not lower else rng.sample([0, 1, 2, 3], rng.randint(1, 3))
        for vg in sorted(set(value_groups)):
            count = rng.randint(1, 4)
            for it in range(1, count + 1):
                refs_only = (not lower) or rng.random() < 0.4
                if refs_only:
                    refs = tuple(rng.sample(lower, rng.randint(0, min(3, len(lower))))) if lower else ()
                    d = MssDatum(layer, vg, it, refs=refs)
                else:
                    arity = rng.randint(1, 4)              # NOT tied to vg
                    tuples = tuple(T(rng.choice(lower), rng.randint(0, 5000)) for _ in range(arity))
                    d = MssDatum(layer, vg, it, tuples=tuples)
                datums.append(d)
                by_layer[layer].append(d.address)
    return datums


class RoundTripTests(unittest.TestCase):
    def test_random_documents_round_trip(self) -> None:
        rng = random.Random(20260601)
        for trial in range(400):
            doc = _random_canonical_document(rng)
            if not doc:
                continue
            encoded = encode_document(doc)
            decoded = decode_document(encoded.bitstream)
            self.assertEqual(_norm(doc), _norm(decoded), f"trial {trial} mismatch")

    def test_hash_is_deterministic_and_content_sensitive(self) -> None:
        a = [MssDatum(0, 0, 1, refs=()), MssDatum(1, 1, 1, tuples=(T("0-0-1", 42),))]
        b = [MssDatum(0, 0, 1, refs=()), MssDatum(1, 1, 1, tuples=(T("0-0-1", 43),))]
        self.assertEqual(mss_document_hash(a), mss_document_hash(a))
        self.assertNotEqual(mss_document_hash(a), mss_document_hash(b))
        self.assertTrue(mss_document_hash(a).startswith("sha256:"))

    def test_reindex_canonicalizes_gappy_layers(self) -> None:
        # Layers {0, 2} with a gap, iterations not from 1 → reindex to {0,1}, 1..K.
        doc = [
            MssDatum(0, 0, 7, refs=()),
            MssDatum(0, 0, 9, refs=()),
            MssDatum(2, 1, 4, tuples=(T("0-0-7", 5),)),
        ]
        canonical, amap = reindex_into_isolated_anthology(doc)
        addrs = sorted(d.address for d in canonical)
        self.assertEqual(addrs, ["0-0-1", "0-0-2", "1-1-1"])
        # ref remapped to the canonical address; value_group (tuple count) preserved.
        leaf = next(d for d in canonical if d.layer == 1)
        self.assertEqual(leaf.value_group, 1)
        self.assertEqual(leaf.tuples, (T(amap["0-0-7"], 5),))
        # still round-trips
        self.assertEqual(_norm(canonical), _norm(decode_document(encode_document(canonical).bitstream)))


class AnthologyShapeTests(unittest.TestCase):
    def _anthology(self) -> list[MssDatum]:
        # A faithful subset of docs/contracts/mss_binary_sequence/anthology-notes.txt:
        # rudis 0-0-1..0-0-6 (VG0), layer-1 abstractions (VG1, one ref+magnitude),
        # and two VG2 datums each carrying exactly two (ref, magnitude) tuples.
        datums = [MssDatum(0, 0, i, refs=()) for i in range(1, 7)]  # top/tiu/sop/siu/nop/niu
        datums += [
            MssDatum(1, 1, 1, tuples=(T("0-0-4", 16162550000000000000000000000000000000),)),  # centameter-babel
            MssDatum(1, 1, 2, tuples=(T("0-0-6", 34560),)),                                    # phoneme
            MssDatum(1, 1, 3, tuples=(T("0-0-1", 946707763350000000),)),                       # UTC
        ]
        datums += [
            MssDatum(2, 1, 1, tuples=(T("1-1-3", 1),)),
        ]
        datums += [
            # VG2: two (ref, magnitude) tuples — the y2k / 21st-century events.
            MssDatum(2, 2, 1, tuples=(T("1-1-3", 63072000000), T("1-1-1", 1))),
            MssDatum(2, 2, 2, tuples=(T("1-1-3", 63072000000), T("1-1-1", 3153600000))),
        ]
        return datums

    def test_anthology_round_trips_and_preserves_tuple_arity(self) -> None:
        canonical, _ = reindex_into_isolated_anthology(self._anthology())
        decoded = decode_document(encode_document(canonical).bitstream)
        self.assertEqual(_norm(canonical), _norm(decoded))
        # The VG2 datums must decode back with exactly two tuples each.
        vg2 = [d for d in decoded if d.value_group == 2]
        self.assertEqual(len(vg2), 2)
        for d in vg2:
            self.assertEqual(len(d.tuples), 2)
        # Rudis are VG0, refs-only, no tuples.
        rudis = [d for d in decoded if d.layer == 0]
        self.assertEqual(len(rudis), 6)
        self.assertTrue(all(d.value_group == 0 and not d.tuples for d in rudis))

    def test_large_magnitudes_survive(self) -> None:
        big = 16162550000000000000000000000000000000
        doc = [MssDatum(0, 0, 1, refs=()), MssDatum(1, 1, 1, tuples=(T("0-0-1", big),))]
        decoded = decode_document(encode_document(doc).bitstream)
        self.assertEqual(decoded[1].tuples[0].token, big)


class ValidationTests(unittest.TestCase):
    def test_arity_decoupled_from_value_group(self) -> None:
        # v2: an entity-style record carrying 4 tuples under value_group=1 is valid
        # and round-trips (this is the live filament/entity case the audit found).
        doc = [
            MssDatum(0, 0, 1, refs=()),
            MssDatum(0, 0, 2, refs=()),
            MssDatum(1, 1, 1, tuples=(T("0-0-1", 11), T("0-0-2", 22), T("0-0-1", 33), T("0-0-2", 44))),
        ]
        decoded = decode_document(encode_document(doc).bitstream)
        leaf = next(d for d in decoded if d.layer == 1)
        self.assertEqual(leaf.value_group, 1)
        self.assertEqual(len(leaf.tuples), 4)
        self.assertEqual(_norm(doc), _norm(decoded))

    def test_refs_and_tuples_together_rejected(self) -> None:
        with self.assertRaises(MssFormatError):
            encode_document([
                MssDatum(0, 0, 1, refs=()),
                MssDatum(1, 1, 1, refs=("0-0-1",), tuples=(T("0-0-1", 1),)),
            ])

    def test_upward_reference_rejected(self) -> None:
        with self.assertRaises(MssFormatError):
            encode_document([
                MssDatum(0, 0, 1, refs=("1-1-1",)),  # refs upward
                MssDatum(1, 1, 1, tuples=(T("0-0-1", 1),)),
            ])

    def test_non_contiguous_layers_rejected_by_encode(self) -> None:
        with self.assertRaises(MssFormatError):
            encode_document([MssDatum(0, 0, 1, refs=()), MssDatum(2, 1, 1, tuples=(T("0-0-1", 1),))])


if __name__ == "__main__":
    unittest.main()
