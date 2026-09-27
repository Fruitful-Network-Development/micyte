"""The artifact codec — a file whose bytes ARE its rows, under the abstraction that says so.

The fourth time this codebase makes the same move. A document's KIND stopped being Python
(``archetype``), its LAYOUT stopped being JavaScript (``viewscope``), a PICTURE stopped
being an asset (``glyph``), and here an arbitrary FILE stops being one. An artifact is not
a pointer to bytes held somewhere else; the rows decode to the bytes and nothing else is
consulted.

## The chain (operator, 2026-09-08), declared in the document's own header

    2-1-1  [<boolean parent>, <size>]   layer 2 VG1: the anchor's Boolean parent, taken
                                        <size> times — the file, as one binary value's TYPE
    3-1-1  [2-1-1, 1]                   one of those
    4-1-1  [3-1-1, 0]                   the ``0`` that makes it referencable
    5-1-N  [4-1-1, kind, magnitude, width]   the bytes, in :data:`CHUNK_BYTES` pieces

The Boolean parent is the anchor's two-symbol nominal babelette — ``nominal-bacillete-2``,
the row the glyph anchor authors as ``1-1-3`` and the base-structure migration adds to
every other anchor beside the recompiled lcl magnitude. Read outside-in it is the same
sentence the glyph's grid chain makes: *extent, then a count, then the 0 that makes it
referencable* — and because that chain is four deep, the payload sits at layer 5. That is
a derivation, not a choice.

## Why the leaves stay CHUNKED (decision D3, 2026-09-08)

The abstraction says one binary value; the payload is many rows. Plan P5 wrote the row
shape as one row per document — the file's bytes as a single integer magnitude — and that
cannot be written. A magnitude reaches JSON as a DECIMAL STRING, and CPython refuses
``str(int)`` above ``sys.get_int_max_str_digits()`` (4300 by default), so a file larger
than about **1785 bytes raises** rather than merely being slow. The pool this was designed
for averages 136 KiB per file. Raising the limit trades a refusal for a cliff:
``int``/``str`` conversion is superlinear — measured O(n^1.10) at 4->64 KiB, O(n^1.30) at
64->256, O(n^1.43) at 256->1024 — so one 1 MiB file costs ~3.1 s to write and ~4.6 s to
read. At :data:`CHUNK_BYTES` it is linear, byte-exact, and inside the default limit with
room: 1 MiB round-trips in ~190 ms rather than ~7.8 s.

So the header DECLARES the single value — its type, its size — and the leaves carry it in
pieces every one of which references that declaration. A reader that wants "what is this
file" reads three rows; a reader that wants the bytes reads them all.

## Every payload row carries its WIDTH

``int`` forgets leading zeros. A chunk of ``b"\\x00\\x00\\x07"`` is the integer 7, and 7
decoded without its width is ONE byte, so the artifact would come back shorter than it went
in and only for files that happen to contain a zero byte at a chunk boundary. The width is
the cheapest possible fix and the only one that does not depend on the data.

## What this does NOT solve

The storage ratio. A byte is 8 bits and a decimal digit is log2(10), so decimal costs
8/log2(10) = **2.41 characters per source byte** at every chunk size. 127 MB of artifacts
is ~306 MB of digits however it is sliced; that is a fact about the representation, not a
parameter.
"""

from __future__ import annotations

import hashlib
from collections.abc import Iterable, Iterator, Sequence
from typing import Any

from micyte.core.mss.magnitude import decode_magnitude, encode_magnitude

#: The rudi an artifact's bytes are counted in: one octet. ``0-0-12``, the twelfth rudi,
#: added 2026-08-23. Declared in every anchor; the payload no longer references it
#: directly (it references the chain), but the width cell counts in it.
OCTET_RUDI = "0-0-12"
OCTET_RUDI_LABEL = "octet"

#: The Boolean parent's label in an anchor, and the rudi it rides on. The glyph anchor
#: authors it as ``("1-1-3", NIU, "2", "nominal-bacillete-2")``; the base-structure
#: migration adds the same row to every anchor that lacks it, beside the lcl magnitude.
#: The rudi's label keeps the corpus's own spelling.
BOOLEAN_PARENT_LABEL = "nominal-bacillete-2"
NIU_LABEL = "nominal-incramental-unit"

#: Source bytes per payload row. 1 KiB encodes to ~2466 decimal digits against a
#: 4300-digit default — headroom, rather than a value that merely fits today. A 4 KiB
#: chunk is ~9864 digits and raises, which is not a hypothetical: the first draft of the
#: test for this used one.
CHUNK_BYTES = 1024

#: The header chain's three addresses, and the payload family beneath them. The address
#: IS the arity: a layer-2 VG1 row carries one (reference, magnitude) pair.
SIZE_ADDRESS = "2-1-1"
ONE_ADDRESS = "3-1-1"
ZERO_ADDRESS = "4-1-1"
HEADER_ROWS = 3
#: Layer 5, one tuple per row: ``(chain, kind, magnitude, width)``.
ARTIFACT_ROW_PREFIX = "5-1-"


def boolean_parent_of(anchor: Any) -> str:
    """The anchor address of the Boolean parent, or ``""`` when the anchor has none.

    Found by LABEL, as every anchor row is: the glyph anchor holds it at ``1-1-3`` and a
    migrated registrar anchor at ``1-1-7``, and a hardcoded address would name a
    different chain in one of them.
    """
    for row in getattr(anchor, "rows", ()) or ():
        raw = getattr(row, "raw", None)
        label = (str(raw[1][0]) if isinstance(raw, list) and len(raw) > 1
                 and isinstance(raw[1], list) and raw[1] else "")
        if label == BOOLEAN_PARENT_LABEL:
            return str(getattr(row, "datum_address", ""))
    return ""


def header_rows(size: int, *, boolean_parent: str) -> list[tuple[str, list[Any]]]:
    """The three rows that say what the file IS before a byte of it is read."""
    if not str(boolean_parent).strip():
        raise ValueError(
            "an artifact's header references the anchor's Boolean parent "
            f"({BOOLEAN_PARENT_LABEL!r}); this anchor declares none")
    if size < 0:
        raise ValueError(f"an artifact cannot be {size} bytes long")
    return [
        (SIZE_ADDRESS, [str(boolean_parent), str(size)]),
        (ONE_ADDRESS, [SIZE_ADDRESS, "1"]),
        (ZERO_ADDRESS, [ONE_ADDRESS, "0"]),
    ]


def _rows_from_bytes(blob: bytes, *, chunk: int) -> Iterator[tuple[str, list[Any]]]:
    if chunk <= 0:
        raise ValueError(f"chunk must be positive: {chunk!r}")
    index = 0
    for start in range(0, len(blob), chunk):
        piece = blob[start:start + chunk]
        index += 1
        kind, magnitude = encode_magnitude(int.from_bytes(piece, "big"))
        yield f"{ARTIFACT_ROW_PREFIX}{index}", [ZERO_ADDRESS, kind, str(magnitude), len(piece)]


def encode_artifact(blob: bytes, *, boolean_parent: str,
                    chunk: int = CHUNK_BYTES) -> list[tuple[str, list[Any]]]:
    """``bytes`` -> the header chain, then ``[(address, [chain, kind, magnitude, width])…]``.

    ``boolean_parent`` is the anchor address the chain references — ask
    :func:`boolean_parent_of` the anchor the artifact belongs beside. Required rather than
    defaulted, because the address differs per anchor and a default would be a dangling
    reference on every anchor but one.

    An EMPTY artifact still declares itself: three header rows saying "a binary value of
    size 0", and no payload — a zero-byte file exists, and inventing a payload row to
    represent nothing would make the round trip lossy in the one direction nobody checks.
    """
    return [*header_rows(len(blob), boolean_parent=boolean_parent),
            *_rows_from_bytes(blob, chunk=chunk)]


def decode_artifact(rows: Iterable[Sequence[Any]]) -> bytes:
    """The inverse, in row order. Header rows are skipped; anything else it did not
    write raises.

    Refuses rather than skipping a PAYLOAD row it cannot read: such a row is a HOLE in a
    file, and a decoder that quietly dropped one would return a plausible artifact of the
    wrong length. Byte exactness is the only useful correctness property here, so
    anything short of it is a failure worth stopping for.
    """
    out = bytearray()
    for position, row in enumerate(rows, start=1):
        cells = list(row)
        if len(cells) == 2:
            continue  # a header row: (reference, magnitude)
        if len(cells) != 4:
            raise ValueError(
                f"artifact row {position} has {len(cells)} cells, expected 4 "
                "(chain, kind, magnitude, width) or a 2-cell header row")
        chain, kind, magnitude, width = cells
        if str(chain) != ZERO_ADDRESS:
            raise ValueError(
                f"artifact row {position} references {chain!r}, not the chain's "
                f"{ZERO_ADDRESS!r} — this is not an artifact row, and decoding it as one "
                "would invent bytes")
        piece = decode_magnitude(int(kind), int(magnitude))
        out += piece.to_bytes(int(width), "big")
    return bytes(out)


def declared_size(rows: Iterable[Sequence[Any]]) -> int | None:
    """What the header SAYS the file's size is — three rows read, no byte decoded."""
    for row in rows:
        cells = list(row)
        if len(cells) == 2 and str(cells[0]) not in (SIZE_ADDRESS, ONE_ADDRESS):
            # The size row references the anchor's Boolean parent, not another header row.
            try:
                return int(cells[1])
            except (TypeError, ValueError):
                return None
    return None


def artifact_digest(blob: bytes) -> str:
    """The identity an artifact's document id carries, and what a migration proves against.

    Over the SOURCE bytes, never over the rows: the rows are a representation and the
    chunk size is a parameter, so a digest over them would change when the parameter did
    and stop meaning "this is the same file".
    """
    return hashlib.sha256(blob).hexdigest()


def round_trips(blob: bytes, *, boolean_parent: str, chunk: int = CHUNK_BYTES) -> bool:
    """Byte-exact, for a per-tranche proof rather than a spot check."""
    return decode_artifact(
        row for _address, row in encode_artifact(blob, boolean_parent=boolean_parent,
                                                 chunk=chunk)) == blob


__all__ = [
    "ARTIFACT_ROW_PREFIX",
    "BOOLEAN_PARENT_LABEL",
    "CHUNK_BYTES",
    "HEADER_ROWS",
    "NIU_LABEL",
    "OCTET_RUDI",
    "OCTET_RUDI_LABEL",
    "ONE_ADDRESS",
    "SIZE_ADDRESS",
    "ZERO_ADDRESS",
    "artifact_digest",
    "boolean_parent_of",
    "declared_size",
    "decode_artifact",
    "encode_artifact",
    "header_rows",
    "round_trips",
]
