"""MSS-DOC.v4 — the document TRANSPORT: a document's rows as one MSS bitstream that
decodes back to the rows EXACTLY (TASK-2026-09-17-001 phase C).

Why a second grammar
--------------------
``document_codec`` (``mos.mss_binary_v3``) is the document's IDENTITY: the canonical
isolated anthology of its downward reference closure, addresses derived, foreign
references dropped and counted. That is the right shape for a hash and the wrong shape
for a store of record. Measured over the live corpus on 2026-09-23 (read-only, every
``lv.`` row): 805,991 of 808,821 tuple references point OUTSIDE the document (the shared
base, ``rf.3-1-N``), 324 layer-0 rows reference the root ``0-0-0`` that no document
carries, 24 ``~`` collections hold tokens that are not addresses at all, 12 rows carry a
bare string where the grammar expects ``[[address, …], [title]]``, and every ``art.``
row is headless (``[[token, magnitude], []]``). A closure resolved from the document's
own rows loses all of that by construction, so the v3 stream cannot be what a reader
decodes rows FROM.

This grammar keeps what MSS is for — addresses are DERIVED from the layer / value-group /
iteration structure and a reference to a datum the document carries is an INDEX into
the layer's active set (the COBM machinery of v3, unchanged) — and carries everything
else as a typed token: any other string (a foreign or upward address, ``rf.``-marked or
bare, a collection token, a text magnitude, a title) by index into a per-document table
of DISTINCT strings — each stored once, byte-aligned, and a string over ``{0,1}`` (the
corpus writes its display labels as 8-bit-aligned binary text) at one bit per character;
integers, booleans and nulls by tag; a nested value by its canonical JSON. The row's shape and its title slot's shape are encoded, so ``[[a], [t]]``,
``[[a]]``, ``[[a], []]`` and a headless head are four different streams. The stream is
self-describing: the original layer numbers and iteration numbers are in it (delta
coded), so no side table is needed to read a document back and a gap (I8) survives.

Wire grammar (MSS-DOC.v4)
-------------------------
The micro-grammar is v3's: ``g`` is Elias-gamma over ``value + 1``; fixed-width fields
are big-endian of a known width, width 0 ⇒ omitted.

    g(L)                                     # layer count (0 ⇒ an empty document)
    for each layer, ascending:               # original layer numbers, delta coded
        g(layer - previous - 1)              #   (the first: g(layer))
        g(G)                                 #   value groups in this layer
        for each group, ascending:
            g(vg - previous - 1)             #   original value-group numbers (first: g(vg))
            g(K)                             #   datums in this group
            for each iteration, ascending:
                g(it - previous - 1)         #   original iteration numbers (first: g(it))
    for layer index 1..L-1:                  # COBM: one bit per datum of every earlier
        <bits>                               #   layer, 1 ⇒ in this layer's active set
    g(F); F × entry                          # the token table: distinct strings, sorted
      entry: g(form) g(n) <body>
        form 0: n UTF-8 bytes, 8 bits each   #   any text
        form 1: n bits                       #   text over the alphabet {0,1} — the
                                             #   corpus's 8-bit-aligned labels, 1 bit/char
    g(stop_width); g(stop_count)             # stop-index table (as v3)
    stop_count × <stop_width bits>
    <value stream>                           # per-datum object blobs, canonical order

Per-datum object blob:
    g(shape)
      shape 0 (addressed head, `raw = [[address, tokens…], title?]`): g(n); n × token; title
      shape 1 (headless head, `raw = [[tokens…], title?]`):           g(n); n × token; title
      shape 2 (opaque: any other `raw`):                              <table index> of its
                                                                       canonical JSON
    token: g(tag) + payload
      0 local address, bare            <ref_width bits>   index into the layer's active set
      1 local address, `rf.`-marked    <ref_width bits>
      2 string                         <table_width bits> index into the token table
      3 integer                        g(zigzag)
      4 boolean                        1 bit
      5 null                           —
      6 nested list/dict/float         <table_width bits> its canonical JSON, by table index
    title: g(title_shape) + payload
      0 absent (`len(raw) == 1`)  1 `[]`  2 `[text]` <table index>  3 bare `text` <table index>
      4 anything else <table index> of its canonical JSON

A "local address" is a string naming a datum address the document carries at a STRICTLY
LOWER layer — the only kind an active-set index can name. The same string at the same or
a higher layer, or naming a datum the document does not carry, is a string (tag 2): the
reader gets the exact token back either way. Canonical order is ascending (layer,
value_group, iteration), which is also the order the semantics engine stores rows in.

Refusals: a row whose ``datum_address`` is not ``<layer>-<vg>-<iteration>`` (nothing to
derive from) and two rows at one address (I1). Nothing else is refused: the transport is
TOTAL over what the store holds, which is the property the corpus rehearsal
(``fnd_app/scripts/rehearse_bitstream_parity.py``) measures as "row-identical".

The policy string is ``mos.mss_binary_v4``; the hash is sha256 over
``"<policy>:<bitstream>"`` as v3's is. v3 is untouched: it remains the identity the
manifests and the dual-write carry until the id flip (phase D) decides otherwise.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any

from micyte.core.datum_semantics.engine import is_datum_address, parse_datum_address

from .document_codec import (
    MssFormatError,
    _fixed_decode,
    _fixed_encode,
    _g_decode,
    _g_encode,
    _ref_width,
    bits_required,
)
from .magnitude import _zigzag_decode, _zigzag_encode

MSS_TRANSPORT_POLICY = "mos.mss_binary_v4"

# Wire constants — appending is safe, renumbering is a format break.
TOKEN_LOCAL = 0
TOKEN_LOCAL_RF = 1
TOKEN_TEXT = 2
TOKEN_INT = 3
TOKEN_BOOL = 4
TOKEN_NULL = 5
TOKEN_JSON = 6

SHAPE_HEAD = 0
SHAPE_HEADLESS = 1
SHAPE_OPAQUE = 2

TITLE_ABSENT = 0
TITLE_EMPTY = 1
TITLE_LISTED = 2
TITLE_BARE = 3
TITLE_JSON = 4

ENTRY_BYTES = 0
ENTRY_BITS = 1

_RF = "rf."
_BIT_CHARS = frozenset("01")


def _encode_entry(text: str) -> str:
    """One token-table entry. Binary text is itself already a bitstream."""
    if text and _BIT_CHARS.issuperset(text):
        return _g_encode(ENTRY_BITS) + _g_encode(len(text)) + text
    body = text.encode("utf-8")
    return (_g_encode(ENTRY_BYTES) + _g_encode(len(body))
            + (format(int.from_bytes(body, "big"), f"0{8 * len(body)}b") if body else ""))


def _decode_entry(bits: str, cursor: int) -> tuple[str, int]:
    form, cursor = _g_decode(bits, cursor)
    length, cursor = _g_decode(bits, cursor)
    if form == ENTRY_BITS:
        text = bits[cursor:cursor + length]
        if len(text) != length:
            raise MssFormatError("truncated binary-text table entry")
        return text, cursor + length
    if form != ENTRY_BYTES:
        raise MssFormatError(f"unknown token-table entry form {form}")
    width = 8 * length
    if cursor + width > len(bits):
        raise MssFormatError("truncated text table entry")
    body = int(bits[cursor:cursor + width], 2).to_bytes(length, "big") if length else b""
    try:
        return body.decode("utf-8"), cursor + width
    except UnicodeDecodeError as exc:
        raise MssFormatError(f"token-table entry is not utf-8: {exc}") from exc


@dataclass(frozen=True)
class EncodedTransport:
    bitstream: str
    datum_count: int

    @property
    def hash(self) -> str:
        digest = hashlib.sha256(f"{MSS_TRANSPORT_POLICY}:{self.bitstream}".encode()).hexdigest()
        return f"sha256:{digest}"


def canonical_json(value: Any) -> str:
    """The one JSON spelling of a nested value, so equal values share a table entry and
    the reader gets the same value back (`json.loads` of this)."""
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def rows_of(document: Any) -> list[tuple[str, Any]]:
    """``(datum_address, raw)`` pairs of a document-like object (rows with those two
    attributes, or dicts with those two keys)."""
    out: list[tuple[str, Any]] = []
    for row in getattr(document, "rows", None) or ():
        if isinstance(row, dict):
            out.append((str(row.get("datum_address") or ""), row.get("raw")))
        else:
            out.append((str(getattr(row, "datum_address", "") or ""), getattr(row, "raw", None)))
    return out


# --------------------------------------------------------------------------- #
# Shape analysis
# --------------------------------------------------------------------------- #
def _split_row(address: str, raw: Any) -> tuple[int, list[Any], tuple[int, Any]]:
    """``(shape, tokens, (title_shape, title_payload))`` of one raw row."""
    if not (isinstance(raw, list) and 1 <= len(raw) <= 2 and isinstance(raw[0], list)):
        return SHAPE_OPAQUE, [], (TITLE_ABSENT, None)
    head = raw[0]
    if head and head[0] == address:
        shape, tokens = SHAPE_HEAD, list(head[1:])
    else:
        shape, tokens = SHAPE_HEADLESS, list(head)
    if len(raw) == 1:
        title: tuple[int, Any] = (TITLE_ABSENT, None)
    else:
        slot = raw[1]
        if isinstance(slot, list) and len(slot) == 0:
            title = (TITLE_EMPTY, None)
        elif isinstance(slot, list) and len(slot) == 1 and isinstance(slot[0], str):
            title = (TITLE_LISTED, slot[0])
        elif isinstance(slot, str):
            title = (TITLE_BARE, slot)
        else:
            title = (TITLE_JSON, canonical_json(slot))
    return shape, tokens, title


def _classify(token: Any, *, layer: int, layer_of: dict[str, int]) -> tuple[int, Any]:
    """``(tag, payload)`` for one head token. ``layer_of`` maps every address the
    document carries to its layer; only a strictly lower layer can be indexed."""
    if isinstance(token, bool):
        return TOKEN_BOOL, token
    if isinstance(token, int):
        return TOKEN_INT, token
    if token is None:
        return TOKEN_NULL, None
    if isinstance(token, str):
        target = token[len(_RF):] if token.startswith(_RF) else token
        held = layer_of.get(target)
        if held is not None and held < layer:
            return (TOKEN_LOCAL_RF if token.startswith(_RF) else TOKEN_LOCAL), target
        return TOKEN_TEXT, token
    return TOKEN_JSON, canonical_json(token)


# --------------------------------------------------------------------------- #
# Encode
# --------------------------------------------------------------------------- #
def encode_rows(rows: Iterable[tuple[str, Any]]) -> EncodedTransport:
    """The rows of ONE document as an MSS-DOC.v4 bitstream. Total over any raw value;
    refuses only what nothing could derive an address from."""
    pairs = list(rows)
    coords: dict[str, tuple[int, int, int]] = {}
    for address, _raw in pairs:
        if not is_datum_address(address):
            raise MssFormatError(f"row address {address!r} is not <layer>-<value_group>-<iteration>")
        if address in coords:
            raise MssFormatError(f"duplicate datum address {address}")
        coords[address] = parse_datum_address(address)
    ordered = sorted(pairs, key=lambda pair: coords[pair[0]])
    layer_of = {address: c[0] for address, c in coords.items()}

    # Pass 1: shapes, tokens, the table, and each layer's locally referenced set.
    analysed: list[tuple[str, int, list[tuple[int, Any]], tuple[int, Any], Any]] = []
    strings: set[str] = set()
    layers = sorted({c[0] for c in coords.values()})
    referenced_by_layer: dict[int, set[str]] = {layer: set() for layer in layers}
    for address, raw in ordered:
        layer = coords[address][0]
        shape, tokens, title = _split_row(address, raw)
        classified: list[tuple[int, Any]] = []
        opaque = None
        if shape == SHAPE_OPAQUE:
            opaque = canonical_json(raw)
            strings.add(opaque)
        else:
            for token in tokens:
                tag, payload = _classify(token, layer=layer, layer_of=layer_of)
                classified.append((tag, payload))
                if tag in (TOKEN_LOCAL, TOKEN_LOCAL_RF):
                    referenced_by_layer[layer].add(payload)
                elif tag in (TOKEN_TEXT, TOKEN_JSON):
                    strings.add(payload)
            if title[0] in (TITLE_LISTED, TITLE_BARE, TITLE_JSON):
                strings.add(title[1])
        analysed.append((address, shape, classified, title, opaque))
    table = sorted(strings)
    table_index = {text: i for i, text in enumerate(table)}
    table_width = _ref_width(len(table))

    out: list[str] = [_g_encode(len(layers))]
    # Metadata: original numbers, delta coded, in canonical order.
    by_layer: dict[int, list[str]] = {layer: [] for layer in layers}
    for address, *_ in analysed:
        by_layer[coords[address][0]].append(address)
    previous_layer: int | None = None
    for layer in layers:
        out.append(_g_encode(layer if previous_layer is None else layer - previous_layer - 1))
        previous_layer = layer
        groups: dict[int, list[int]] = {}
        for address in by_layer[layer]:
            _, vg, it = coords[address]
            groups.setdefault(vg, []).append(it)
        out.append(_g_encode(len(groups)))
        previous_vg: int | None = None
        for vg in sorted(groups):
            out.append(_g_encode(vg if previous_vg is None else vg - previous_vg - 1))
            previous_vg = vg
            iterations = sorted(groups[vg])
            out.append(_g_encode(len(iterations)))
            previous_it: int | None = None
            for it in iterations:
                out.append(_g_encode(it if previous_it is None else it - previous_it - 1))
                previous_it = it

    # COBM per layer index ≥ 1, over every datum of the earlier layers (canonical order).
    prior: list[str] = []
    active_index: dict[int, dict[str, int]] = {}
    for position, layer in enumerate(layers):
        if position > 0:
            referenced = referenced_by_layer[layer]
            out.append("".join("1" if address in referenced else "0" for address in prior))
            active = [address for address in prior if address in referenced]
            active_index[layer] = {address: i for i, address in enumerate(active)}
        else:
            active_index[layer] = {}
        prior = prior + by_layer[layer]

    # The token table.
    out.append(_g_encode(len(table)))
    for text in table:
        out.append(_encode_entry(text))

    # Object blobs.
    objects: list[str] = []
    for address, shape, classified, title, opaque in analysed:
        layer = coords[address][0]
        index_of = active_index[layer]
        ref_width = _ref_width(len(index_of))
        blob: list[str] = [_g_encode(shape)]
        if shape == SHAPE_OPAQUE:
            blob.append(_fixed_encode(table_index[opaque], table_width))
        else:
            blob.append(_g_encode(len(classified)))
            for tag, payload in classified:
                blob.append(_g_encode(tag))
                if tag in (TOKEN_LOCAL, TOKEN_LOCAL_RF):
                    blob.append(_fixed_encode(index_of[payload], ref_width))
                elif tag in (TOKEN_TEXT, TOKEN_JSON):
                    blob.append(_fixed_encode(table_index[payload], table_width))
                elif tag == TOKEN_INT:
                    blob.append(_g_encode(_zigzag_encode(payload)))
                elif tag == TOKEN_BOOL:
                    blob.append("1" if payload else "0")
            blob.append(_g_encode(title[0]))
            if title[0] in (TITLE_LISTED, TITLE_BARE, TITLE_JSON):
                blob.append(_fixed_encode(table_index[title[1]], table_width))
        objects.append("".join(blob))

    stops: list[int] = []
    total = 0
    for blob in objects[:-1]:
        total += len(blob)
        stops.append(total)
    stop_width = bits_required(stops[-1] if stops else 0)
    out.append(_g_encode(stop_width))
    out.append(_g_encode(len(stops)))
    for stop in stops:
        out.append(_fixed_encode(stop, stop_width))
    out.append("".join(objects))
    return EncodedTransport(bitstream="".join(out), datum_count=len(ordered))


# --------------------------------------------------------------------------- #
# Decode
# --------------------------------------------------------------------------- #
def decode_rows(bitstream: str) -> list[tuple[str, Any]]:
    """The inverse of :func:`encode_rows`: ``(datum_address, raw)`` pairs in canonical
    order, each ``raw`` equal (and type-equal) to what was encoded."""
    cursor = 0
    layer_count, cursor = _g_decode(bitstream, cursor)
    specs: list[tuple[int, int, int]] = []
    by_layer: list[list[str]] = []
    previous_layer: int | None = None
    for _ in range(layer_count):
        delta, cursor = _g_decode(bitstream, cursor)
        layer = delta if previous_layer is None else previous_layer + delta + 1
        previous_layer = layer
        group_count, cursor = _g_decode(bitstream, cursor)
        members: list[str] = []
        previous_vg: int | None = None
        for _ in range(group_count):
            delta, cursor = _g_decode(bitstream, cursor)
            vg = delta if previous_vg is None else previous_vg + delta + 1
            previous_vg = vg
            iteration_count, cursor = _g_decode(bitstream, cursor)
            previous_it: int | None = None
            for _ in range(iteration_count):
                delta, cursor = _g_decode(bitstream, cursor)
                it = delta if previous_it is None else previous_it + delta + 1
                previous_it = it
                specs.append((layer, vg, it))
                members.append(f"{layer}-{vg}-{it}")
        by_layer.append(members)

    active_sets: list[list[str]] = []
    prior: list[str] = []
    for position in range(layer_count):
        if position > 0:
            width = len(prior)
            cobm = bitstream[cursor:cursor + width]
            if len(cobm) != width:
                raise MssFormatError("truncated COBM")
            cursor += width
            active_sets.append([address for address, bit in zip(prior, cobm, strict=True) if bit == "1"])
        else:
            active_sets.append([])
        prior = prior + by_layer[position]

    table_size, cursor = _g_decode(bitstream, cursor)
    table: list[str] = []
    for _ in range(table_size):
        text, cursor = _decode_entry(bitstream, cursor)
        table.append(text)
    table_width = _ref_width(len(table))

    stop_width, cursor = _g_decode(bitstream, cursor)
    stop_count, cursor = _g_decode(bitstream, cursor)
    stops: list[int] = []
    for _ in range(stop_count):
        stop, cursor = _fixed_decode(bitstream, cursor, stop_width)
        stops.append(stop)
    value_stream = bitstream[cursor:]
    if not specs:
        if value_stream:
            raise MssFormatError("an empty document carries a non-empty value stream")
        return []
    blobs: list[str] = []
    start = 0
    for stop in stops:
        blobs.append(value_stream[start:stop])
        start = stop
    blobs.append(value_stream[start:])
    if len(blobs) != len(specs):
        raise MssFormatError(f"stop table yields {len(blobs)} objects but metadata expects {len(specs)}")

    def lookup(index: int, kind: str) -> str:
        if index >= len(table):
            raise MssFormatError(f"{kind} index {index} is outside the token table ({len(table)})")
        return table[index]

    out: list[tuple[str, Any]] = []
    position = 0
    layer_positions = {layer: i for i, layer in enumerate(sorted({s[0] for s in specs}))}
    for (layer, vg, it), blob in zip(specs, blobs, strict=True):
        address = f"{layer}-{vg}-{it}"
        active = active_sets[layer_positions[layer]]
        ref_width = _ref_width(len(active))
        bc = 0
        shape, bc = _g_decode(blob, bc)
        if shape == SHAPE_OPAQUE:
            index, bc = _fixed_decode(blob, bc, table_width)
            out.append((address, json.loads(lookup(index, "opaque"))))
            position += 1
            continue
        if shape not in (SHAPE_HEAD, SHAPE_HEADLESS):
            raise MssFormatError(f"unknown row shape {shape} at {address}")
        count, bc = _g_decode(blob, bc)
        tokens: list[Any] = []
        for _ in range(count):
            tag, bc = _g_decode(blob, bc)
            if tag in (TOKEN_LOCAL, TOKEN_LOCAL_RF):
                index, bc = _fixed_decode(blob, bc, ref_width)
                if index >= len(active):
                    raise MssFormatError(f"local reference {index} is outside the active set at {address}")
                tokens.append((_RF if tag == TOKEN_LOCAL_RF else "") + active[index])
            elif tag == TOKEN_TEXT:
                index, bc = _fixed_decode(blob, bc, table_width)
                tokens.append(lookup(index, "string"))
            elif tag == TOKEN_JSON:
                index, bc = _fixed_decode(blob, bc, table_width)
                tokens.append(json.loads(lookup(index, "nested")))
            elif tag == TOKEN_INT:
                value, bc = _g_decode(blob, bc)
                tokens.append(_zigzag_decode(value))
            elif tag == TOKEN_BOOL:
                if bc >= len(blob):
                    raise MssFormatError("truncated boolean")
                tokens.append(blob[bc] == "1")
                bc += 1
            elif tag == TOKEN_NULL:
                tokens.append(None)
            else:
                raise MssFormatError(f"unknown token tag {tag} at {address}")
        title_shape, bc = _g_decode(blob, bc)
        head = [address, *tokens] if shape == SHAPE_HEAD else tokens
        if title_shape == TITLE_ABSENT:
            raw: Any = [head]
        elif title_shape == TITLE_EMPTY:
            raw = [head, []]
        else:
            index, bc = _fixed_decode(blob, bc, table_width)
            text = lookup(index, "title")
            if title_shape == TITLE_LISTED:
                raw = [head, [text]]
            elif title_shape == TITLE_BARE:
                raw = [head, text]
            elif title_shape == TITLE_JSON:
                raw = [head, json.loads(text)]
            else:
                raise MssFormatError(f"unknown title shape {title_shape} at {address}")
        out.append((address, raw))
        position += 1
    return out


# --------------------------------------------------------------------------- #
# Packing and hashing
# --------------------------------------------------------------------------- #
def pack_bits(bitstream: str) -> bytes:
    """``'0'/'1'`` text → bytes. A leading ``1`` sentinel keeps the bit count exact."""
    return int("1" + bitstream, 2).to_bytes((len(bitstream) + 8) // 8, "big")


def unpack_bits(packed: bytes) -> str:
    bits = bin(int.from_bytes(packed, "big"))[2:]
    if not bits.startswith("1"):
        raise MssFormatError("packed bitstream is missing its sentinel")
    return bits[1:]


def transport_hash(bitstream: str) -> str:
    return EncodedTransport(bitstream=bitstream, datum_count=0).hash


__all__ = [
    "MSS_TRANSPORT_POLICY",
    "EncodedTransport",
    "canonical_json",
    "decode_rows",
    "encode_rows",
    "pack_bits",
    "rows_of",
    "transport_hash",
    "unpack_bits",
]
