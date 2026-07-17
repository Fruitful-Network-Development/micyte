
"""
mss_compact_array_reference.py

Reference implementation of the MSS compact-array logic discussed in the chat.

Context boundary reminder
------------------------
This module is about MSS compact-array transport semantics, not anthology key
ordering rules and not SAMRAS structural addressing.

Do not treat MSS row/index handling as equivalent to datum-address ordering.
Datum ordering belongs to <layer>-<value_group>-<iteration> numeric handling
(see datum_structure.py).

Scope
-----
This file captures the clarified logic in executable Python:

- MSS is compiled from the transitive downward reference closure of selected datum(s)
- the closure is reindexed into an isolated anthology
- metadata records the isolated anthology structure
- COBM is inserted between populated layers
- tuple reference width is determined per layer from the active carry-over set
- stop-index width is determined by the largest stop position in the object stream
- VG0 rows store references only
- VG>0 rows store exactly `value_group` reference/magnitude tuples

Important caveat
----------------
A few low-level binary details are still design choices rather than fixed runtime law.
This file therefore implements a *sound reference model* with explicit assumptions,
not a promise that every bit matches the current repository writer byte-for-byte.

Explicit assumptions used here
------------------------------
1. Metadata integers are encoded as self-delimiting integers using:
       0...(k-1 times) + 1 + <k-bit payload>
   where k = bit length of the integer payload.
   Example:
       0  -> "10"
       1  -> "11"
       4  -> "00100"

2. The stop-index table uses a fixed width derived from the maximum stop position.

3. VG0 row grammar is:
       <ref_count:self-delimiting-int><ref_0><ref_1>...
   where each ref is encoded using the layer-local fixed reference width.

   This is a *reasonable explicit choice* for a deterministic VG0 wire grammar.
   The broader MSS rules are canonical; this exact VG0 row micro-grammar can
   still be changed later if needed.

4. Reference indexes are indexes into the active carry-over set for the current layer.

5. For an active carry-over set of size 1, the reference width is 0 bits.
   In that case, the sole active row is the implied reference target.

This file is meant to be read, run, modified, and used as a correctness aid while
you refine the canonical wire contract.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from math import ceil, log2
from typing import Dict, Iterable, List, Optional, Sequence, Tuple


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class RefMagTuple:
    ref: str
    magnitude: int


@dataclass
class DatumRow:
    layer: int
    value_group: int
    iteration: int
    refs_only: List[str] = field(default_factory=list)
    tuples: List[RefMagTuple] = field(default_factory=list)
    source_identifier: str = ""

    @property
    def identifier(self) -> str:
        return f"{self.layer}-{self.value_group}-{self.iteration}"

    def dependency_ids(self) -> List[str]:
        if self.value_group == 0:
            return list(self.refs_only)
        return [item.ref for item in self.tuples]

    def clone(self) -> "DatumRow":
        return DatumRow(
            layer=self.layer,
            value_group=self.value_group,
            iteration=self.iteration,
            refs_only=list(self.refs_only),
            tuples=[RefMagTuple(item.ref, item.magnitude) for item in self.tuples],
            source_identifier=self.source_identifier,
        )


@dataclass(frozen=True)
class MSSMetadata:
    layer_count: int
    layer_max: int
    value_group_count_per_layer: List[int]
    iteration_count_per_value_group: List[int]
    value_group_value_per_value_group: List[int]

    def as_debug_dict(self) -> Dict[str, object]:
        return {
            "layer_count": self.layer_count,
            "layer_max": self.layer_max,
            "value_group_count_per_layer": list(self.value_group_count_per_layer),
            "iteration_count_per_value_group": list(self.iteration_count_per_value_group),
            "value_group_value_per_value_group": list(self.value_group_value_per_value_group),
        }


@dataclass(frozen=True)
class RowSpec:
    layer: int
    value_group: int
    iteration: int

    @property
    def identifier(self) -> str:
        return f"{self.layer}-{self.value_group}-{self.iteration}"


@dataclass(frozen=True)
class EncodedMSS:
    bitstream: str
    width_sentinel: str
    metadata_bits: str
    stop_index_bits: str
    object_stream_bits: str
    stop_width: int
    stop_indexes: List[int]
    metadata: MSSMetadata
    isolated_rows: List[DatumRow]
    object_slices: List[str]
    debug_objects: List[Tuple[str, str]]  # [("cobm:L1", bits), ("row:1-1-1", bits), ...]


@dataclass(frozen=True)
class DecodedMSS:
    bitstream: str
    width_sentinel: str
    metadata_bits: str
    stop_index_bits: str
    object_stream_bits: str
    stop_width: int
    stop_indexes: List[int]
    metadata: MSSMetadata
    row_specs: List[RowSpec]
    decoded_rows: List[DatumRow]
    object_slices: List[str]
    debug_objects: List[Tuple[str, str]]


# ---------------------------------------------------------------------------
# Bit helpers
# ---------------------------------------------------------------------------

def bits_required(max_value: int) -> int:
    """
    Width needed to encode integer values from 0..max_value inclusive.

    Examples:
        bits_required(0)  -> 1
        bits_required(1)  -> 1
        bits_required(3)  -> 2
        bits_required(39) -> 6
    """
    if max_value < 0:
        raise ValueError("max_value must be >= 0")
    if max_value <= 1:
        return 1
    return int(ceil(log2(max_value + 1)))


def encode_fixed_width(value: int, width: int) -> str:
    if value < 0:
        raise ValueError("fixed-width values must be >= 0")
    if width < 0:
        raise ValueError("width must be >= 0")
    if width == 0:
        if value != 0:
            raise ValueError("cannot encode nonzero value with width 0")
        return ""
    max_value = (1 << width) - 1
    if value > max_value:
        raise ValueError(f"value {value} exceeds width {width}")
    return format(value, f"0{width}b")


def decode_fixed_width(bits: str, cursor: int, width: int) -> Tuple[int, int]:
    if width < 0:
        raise ValueError("width must be >= 0")
    if width == 0:
        return 0, cursor
    end = cursor + width
    if end > len(bits):
        raise ValueError("not enough bits for fixed-width decode")
    return int(bits[cursor:end], 2), end


def encode_self_delimiting_int(value: int) -> str:
    """
    Encode a nonnegative integer using a simple self-delimiting scheme:
        0...(k-1 times) + 1 + <k-bit payload>
    where k = bit length of the payload.

    Examples:
        0 -> payload "0"     -> "10"
        1 -> payload "1"     -> "11"
        4 -> payload "100"   -> "001100"
    """
    if value < 0:
        raise ValueError("self-delimiting int must be >= 0")
    payload = format(value, "b")
    k = len(payload)
    return ("0" * (k - 1)) + "1" + payload


def decode_self_delimiting_int(bits: str, cursor: int) -> Tuple[int, int]:
    zeros = 0
    while True:
        if cursor >= len(bits):
            raise ValueError("unexpected EOF while reading self-delimiting int prefix")
        if bits[cursor] == "1":
            cursor += 1
            break
        zeros += 1
        cursor += 1
    payload_width = zeros + 1
    end = cursor + payload_width
    if end > len(bits):
        raise ValueError("unexpected EOF while reading self-delimiting int payload")
    payload = bits[cursor:end]
    return int(payload, 2), end


def encode_width_sentinel(width: int) -> str:
    """
    Encode the stop-index width using:
        <count_0_bits>1<number_of_bits>

    If width = 6 ("110"), this becomes:
        "00110"
    """
    if width <= 0:
        raise ValueError("width sentinel requires width >= 1")
    payload = format(width, "b")
    return ("0" * (len(payload) - 1)) + "1" + payload


def decode_width_sentinel(bits: str, cursor: int = 0) -> Tuple[int, int, str]:
    start = cursor
    zeros = 0
    while True:
        if cursor >= len(bits):
            raise ValueError("unexpected EOF while reading width sentinel")
        if bits[cursor] == "1":
            cursor += 1
            break
        zeros += 1
        cursor += 1
    payload_width = zeros + 1
    end = cursor + payload_width
    if end > len(bits):
        raise ValueError("unexpected EOF while reading width sentinel payload")
    width = int(bits[cursor:end], 2)
    return width, end, bits[start:end]


# ---------------------------------------------------------------------------
# Closure and isolated anthology compilation
# ---------------------------------------------------------------------------

def parse_identifier(identifier: str) -> Tuple[int, int, int]:
    parts = identifier.split("-")
    if len(parts) != 3:
        raise ValueError(f"invalid identifier: {identifier}")
    return int(parts[0]), int(parts[1]), int(parts[2])


def sort_key_for_identifier(identifier: str) -> Tuple[int, int, int]:
    return parse_identifier(identifier)


def sort_rows(rows: Iterable[DatumRow]) -> List[DatumRow]:
    return sorted(rows, key=lambda row: (row.layer, row.value_group, row.iteration))


def build_row_index(rows: Sequence[DatumRow]) -> Dict[str, DatumRow]:
    out: Dict[str, DatumRow] = {}
    for row in rows:
        if row.identifier in out:
            raise ValueError(f"duplicate row identifier: {row.identifier}")
        out[row.identifier] = row
    return out


def transitive_closure(selected_ids: Sequence[str], anthology_rows: Sequence[DatumRow]) -> List[DatumRow]:
    """
    Return the downward transitive closure of the selected rows.

    This is the critical correction:
    - include every lower-layer dependency actually needed to interpret the target
    - do NOT include unrelated siblings merely because they are on layer 0
    """
    row_index = build_row_index(anthology_rows)
    visited: set[str] = set()
    ordered: List[DatumRow] = []

    def dfs(row_id: str) -> None:
        if row_id in visited:
            return
        row = row_index.get(row_id)
        if row is None:
            raise KeyError(f"missing dependency row: {row_id}")
        visited.add(row_id)
        for dep_id in row.dependency_ids():
            dfs(dep_id)
        ordered.append(row.clone())

    for selected_id in selected_ids:
        dfs(selected_id)

    return sort_rows(ordered)


def reindex_into_isolated_anthology(closure_rows: Sequence[DatumRow]) -> Tuple[List[DatumRow], Dict[str, str]]:
    """
    Reindex the closure rows into a compact isolated anthology.

    Rows are ordered by:
        layer -> value_group -> iteration

    Each (layer, value_group) subgroup gets iterations renumbered from 1..N.
    References are rewritten to the isolated identifiers.
    """
    sorted_closure = sort_rows(closure_rows)

    # Build new identifiers
    per_group_counter: Dict[Tuple[int, int], int] = {}
    id_map: Dict[str, str] = {}
    row_map_old: Dict[str, DatumRow] = {}

    for row in sorted_closure:
        old_id = row.identifier
        row_map_old[old_id] = row
        key = (row.layer, row.value_group)
        per_group_counter[key] = per_group_counter.get(key, 0) + 1
        new_iter = per_group_counter[key]
        new_id = f"{row.layer}-{row.value_group}-{new_iter}"
        id_map[old_id] = new_id

    # Rewrite rows
    isolated_rows: List[DatumRow] = []
    for row in sorted_closure:
        new_layer, new_vg, new_iter = parse_identifier(id_map[row.identifier])
        if row.value_group == 0:
            new_row = DatumRow(
                layer=new_layer,
                value_group=new_vg,
                iteration=new_iter,
                refs_only=[id_map[ref] for ref in row.refs_only],
                tuples=[],
                source_identifier=row.identifier,
            )
        else:
            new_row = DatumRow(
                layer=new_layer,
                value_group=new_vg,
                iteration=new_iter,
                refs_only=[],
                tuples=[RefMagTuple(id_map[item.ref], item.magnitude) for item in row.tuples],
                source_identifier=row.identifier,
            )
        isolated_rows.append(new_row)

    return sort_rows(isolated_rows), id_map


def compile_isolated_closure(selected_ids: Sequence[str], anthology_rows: Sequence[DatumRow]) -> Tuple[List[DatumRow], Dict[str, str]]:
    closure = transitive_closure(selected_ids, anthology_rows)
    return reindex_into_isolated_anthology(closure)


# ---------------------------------------------------------------------------
# Metadata
# ---------------------------------------------------------------------------

def build_metadata(isolated_rows: Sequence[DatumRow]) -> MSSMetadata:
    if not isolated_rows:
        raise ValueError("cannot build metadata for empty row set")

    layer_max = max(row.layer for row in isolated_rows)
    layer_count = layer_max + 1

    rows_by_layer: Dict[int, List[DatumRow]] = {layer: [] for layer in range(layer_count)}
    for row in isolated_rows:
        rows_by_layer.setdefault(row.layer, []).append(row)

    value_group_count_per_layer: List[int] = []
    iteration_count_per_value_group: List[int] = []
    value_group_value_per_value_group: List[int] = []

    for layer in range(layer_count):
        layer_rows = sort_rows(rows_by_layer.get(layer, []))
        if not layer_rows:
            value_group_count_per_layer.append(0)
            continue

        groups: Dict[int, List[DatumRow]] = {}
        for row in layer_rows:
            groups.setdefault(row.value_group, []).append(row)

        ordered_vgs = sorted(groups.keys())
        value_group_count_per_layer.append(len(ordered_vgs))

        for vg in ordered_vgs:
            rows_in_group = sort_rows(groups[vg])
            value_group_value_per_value_group.append(vg)
            iteration_count_per_value_group.append(len(rows_in_group))

    return MSSMetadata(
        layer_count=layer_count,
        layer_max=layer_max,
        value_group_count_per_layer=value_group_count_per_layer,
        iteration_count_per_value_group=iteration_count_per_value_group,
        value_group_value_per_value_group=value_group_value_per_value_group,
    )


def encode_metadata(metadata: MSSMetadata) -> str:
    bits = []
    bits.append(encode_self_delimiting_int(metadata.layer_count))
    bits.append(encode_self_delimiting_int(metadata.layer_max))

    for item in metadata.value_group_count_per_layer:
        bits.append(encode_self_delimiting_int(item))

    for item in metadata.iteration_count_per_value_group:
        bits.append(encode_self_delimiting_int(item))

    for item in metadata.value_group_value_per_value_group:
        bits.append(encode_self_delimiting_int(item))

    return "".join(bits)


def decode_metadata(bits: str, cursor: int) -> Tuple[MSSMetadata, int, str]:
    start = cursor

    layer_count, cursor = decode_self_delimiting_int(bits, cursor)
    layer_max, cursor = decode_self_delimiting_int(bits, cursor)

    value_group_count_per_layer: List[int] = []
    for _ in range(layer_count):
        value, cursor = decode_self_delimiting_int(bits, cursor)
        value_group_count_per_layer.append(value)

    total_value_groups = sum(value_group_count_per_layer)

    iteration_count_per_value_group: List[int] = []
    for _ in range(total_value_groups):
        value, cursor = decode_self_delimiting_int(bits, cursor)
        iteration_count_per_value_group.append(value)

    value_group_value_per_value_group: List[int] = []
    for _ in range(total_value_groups):
        value, cursor = decode_self_delimiting_int(bits, cursor)
        value_group_value_per_value_group.append(value)

    meta = MSSMetadata(
        layer_count=layer_count,
        layer_max=layer_max,
        value_group_count_per_layer=value_group_count_per_layer,
        iteration_count_per_value_group=iteration_count_per_value_group,
        value_group_value_per_value_group=value_group_value_per_value_group,
    )
    return meta, cursor, bits[start:cursor]


def expand_row_specs(metadata: MSSMetadata) -> List[RowSpec]:
    specs: List[RowSpec] = []
    flat_index = 0

    for layer in range(metadata.layer_count):
        vg_count = metadata.value_group_count_per_layer[layer]
        for _ in range(vg_count):
            value_group = metadata.value_group_value_per_value_group[flat_index]
            iteration_count = metadata.iteration_count_per_value_group[flat_index]
            flat_index += 1

            for iteration in range(1, iteration_count + 1):
                specs.append(RowSpec(layer=layer, value_group=value_group, iteration=iteration))

    return specs


# ---------------------------------------------------------------------------
# COBM and reference handling
# ---------------------------------------------------------------------------

def rows_grouped_by_layer(row_specs: Sequence[RowSpec]) -> Dict[int, List[RowSpec]]:
    out: Dict[int, List[RowSpec]] = {}
    for spec in row_specs:
        out.setdefault(spec.layer, []).append(spec)
    return out


def row_index_map(rows: Sequence[DatumRow]) -> Dict[str, DatumRow]:
    return {row.identifier: row for row in rows}


def cobm_active_set(accumulated_rows: Sequence[DatumRow], next_layer_rows: Sequence[DatumRow]) -> Tuple[str, List[DatumRow]]:
    """
    COBM logic:
    - accumulate rows seen so far
    - record which accumulated identifiers are referenced by the next layer
    - encode that as a bit log in cumulative row order
    """
    referenced_ids: set[str] = set()
    for row in next_layer_rows:
        referenced_ids.update(row.dependency_ids())

    bits = []
    active_rows: List[DatumRow] = []
    for row in accumulated_rows:
        if row.identifier in referenced_ids:
            bits.append("1")
            active_rows.append(row)
        else:
            bits.append("0")
    return "".join(bits), active_rows


def decode_cobm(cobm_bits: str, accumulated_rows: Sequence[DatumRow]) -> List[DatumRow]:
    if len(cobm_bits) != len(accumulated_rows):
        raise ValueError("COBM width does not match accumulated row count")
    out: List[DatumRow] = []
    for bit, row in zip(cobm_bits, accumulated_rows):
        if bit == "1":
            out.append(row)
        elif bit != "0":
            raise ValueError("invalid COBM bit")
    return out


def ref_width_for_active_set(active_set_size: int) -> int:
    """
    Width needed to index the active carry-over set.

    If there is exactly one active ref, width is 0 because the target is implicit.
    """
    if active_set_size < 0:
        raise ValueError("active_set_size must be >= 0")
    if active_set_size <= 1:
        return 0
    return int(ceil(log2(active_set_size)))


def active_set_index(active_set: Sequence[DatumRow], ref_id: str) -> int:
    for index, row in enumerate(active_set):
        if row.identifier == ref_id:
            return index
    raise KeyError(f"reference {ref_id} not found in active carry-over set")


def resolve_active_ref(active_set: Sequence[DatumRow], ref_index: int) -> str:
    if not active_set:
        raise ValueError("cannot resolve ref from empty active set")
    if len(active_set) == 1 and ref_index == 0:
        return active_set[0].identifier
    return active_set[ref_index].identifier


# ---------------------------------------------------------------------------
# Row object encoding/decoding
# ---------------------------------------------------------------------------

def encode_vg0_row(row: DatumRow, active_set: Sequence[DatumRow], ref_width: int) -> str:
    """
    Reference implementation choice for VG0 row grammar:

        <ref_count:self-delimiting-int><ref_0><ref_1>...

    This keeps VG0 as "references only" while still making the arity explicit.
    """
    if row.value_group != 0:
        raise ValueError("encode_vg0_row requires value_group == 0")

    bits = [encode_self_delimiting_int(len(row.refs_only))]
    for ref_id in row.refs_only:
        if ref_width == 0:
            # One active ref => implied target; must match sole active row.
            if len(active_set) != 1 or active_set[0].identifier != ref_id:
                raise ValueError(
                    f"VG0 row {row.identifier} implied ref mismatch for zero-width active set"
                )
            bits.append("")
        else:
            ref_index = active_set_index(active_set, ref_id)
            bits.append(encode_fixed_width(ref_index, ref_width))
    return "".join(bits)


def decode_vg0_row(bits: str, active_set: Sequence[DatumRow], ref_width: int) -> List[str]:
    cursor = 0
    ref_count, cursor = decode_self_delimiting_int(bits, cursor)
    refs: List[str] = []

    for _ in range(ref_count):
        if ref_width == 0:
            if len(active_set) != 1:
                raise ValueError("zero-width VG0 ref requires active set size 1")
            refs.append(active_set[0].identifier)
        else:
            ref_index, cursor = decode_fixed_width(bits, cursor, ref_width)
            refs.append(resolve_active_ref(active_set, ref_index))

    if cursor != len(bits):
        raise ValueError("extra bits remain after decoding VG0 row")
    return refs


def encode_ref_mag_tuple(item: RefMagTuple, active_set: Sequence[DatumRow], ref_width: int) -> str:
    if ref_width == 0:
        if len(active_set) != 1 or active_set[0].identifier != item.ref:
            raise ValueError("zero-width tuple ref implies the sole active row")
        ref_bits = ""
    else:
        ref_index = active_set_index(active_set, item.ref)
        ref_bits = encode_fixed_width(ref_index, ref_width)

    magnitude_bits = encode_self_delimiting_int(item.magnitude)
    return ref_bits + magnitude_bits


def decode_ref_mag_tuple(bits: str, cursor: int, active_set: Sequence[DatumRow], ref_width: int) -> Tuple[RefMagTuple, int]:
    if ref_width == 0:
        if len(active_set) != 1:
            raise ValueError("zero-width tuple ref requires active set size 1")
        ref_id = active_set[0].identifier
    else:
        ref_index, cursor = decode_fixed_width(bits, cursor, ref_width)
        ref_id = resolve_active_ref(active_set, ref_index)

    magnitude, cursor = decode_self_delimiting_int(bits, cursor)
    return RefMagTuple(ref=ref_id, magnitude=magnitude), cursor


def encode_row_object(row: DatumRow, active_set: Sequence[DatumRow], ref_width: int) -> str:
    if row.value_group == 0:
        return encode_vg0_row(row, active_set, ref_width)

    if len(row.tuples) != row.value_group:
        raise ValueError(
            f"row {row.identifier} has value_group={row.value_group} but {len(row.tuples)} tuples"
        )

    bits = []
    for item in row.tuples:
        bits.append(encode_ref_mag_tuple(item, active_set, ref_width))
    return "".join(bits)


def decode_row_object(row_bits: str, spec: RowSpec, active_set: Sequence[DatumRow], ref_width: int) -> DatumRow:
    if spec.value_group == 0:
        refs_only = decode_vg0_row(row_bits, active_set, ref_width)
        return DatumRow(
            layer=spec.layer,
            value_group=spec.value_group,
            iteration=spec.iteration,
            refs_only=refs_only,
            tuples=[],
        )

    cursor = 0
    tuples: List[RefMagTuple] = []
    for _ in range(spec.value_group):
        item, cursor = decode_ref_mag_tuple(row_bits, cursor, active_set, ref_width)
        tuples.append(item)

    if cursor != len(row_bits):
        raise ValueError(f"extra bits remain after decoding row {spec.identifier}")

    return DatumRow(
        layer=spec.layer,
        value_group=spec.value_group,
        iteration=spec.iteration,
        refs_only=[],
        tuples=tuples,
    )


# ---------------------------------------------------------------------------
# Stop index table
# ---------------------------------------------------------------------------

def cumulative_stop_indexes(objects: Sequence[str]) -> List[int]:
    out: List[int] = []
    total = 0
    for obj in objects:
        total += len(obj)
        out.append(total)
    return out


def encode_stop_indexes(stop_indexes: Sequence[int], width: int) -> str:
    return "".join(encode_fixed_width(value, width) for value in stop_indexes)


def decode_stop_indexes(bits: str, cursor: int, count: int, width: int) -> Tuple[List[int], int, str]:
    start = cursor
    values: List[int] = []
    for _ in range(count):
        value, cursor = decode_fixed_width(bits, cursor, width)
        values.append(value)
    return values, cursor, bits[start:cursor]


def slice_by_stop_indexes(object_stream_bits: str, stop_indexes: Sequence[int]) -> List[str]:
    last = 0
    out: List[str] = []
    for stop in stop_indexes:
        if stop < last or stop > len(object_stream_bits):
            raise ValueError("invalid stop index sequence")
        out.append(object_stream_bits[last:stop])
        last = stop
    if last != len(object_stream_bits):
        raise ValueError("stop indexes do not consume the full object stream")
    return out


# ---------------------------------------------------------------------------
# High-level encode / decode
# ---------------------------------------------------------------------------

def count_cobm_objects_for_specs(row_specs: Sequence[RowSpec]) -> int:
    populated_layers = sorted({spec.layer for spec in row_specs})
    if not populated_layers:
        return 0
    return max(0, len(populated_layers) - 1)


def encode_mss_from_isolated_rows(isolated_rows: Sequence[DatumRow]) -> EncodedMSS:
    isolated_rows = sort_rows(isolated_rows)
    metadata = build_metadata(isolated_rows)
    row_specs = expand_row_specs(metadata)
    grouped_specs = rows_grouped_by_layer(row_specs)
    grouped_rows: Dict[int, List[DatumRow]] = {}
    for row in isolated_rows:
        grouped_rows.setdefault(row.layer, []).append(row)

    objects: List[str] = []
    debug_objects: List[Tuple[str, str]] = []
    accumulated_rows: List[DatumRow] = []

    populated_layers = sorted(grouped_specs.keys())
    for layer in populated_layers:
        layer_rows = sort_rows(grouped_rows[layer])

        if layer > 0:
            cobm_bits, active_set = cobm_active_set(accumulated_rows, layer_rows)
            objects.append(cobm_bits)
            debug_objects.append((f"cobm:L{layer}", cobm_bits))
            ref_width = ref_width_for_active_set(len(active_set))
        else:
            active_set = []
            ref_width = 0

        for row in layer_rows:
            row_bits = encode_row_object(row, active_set, ref_width)
            objects.append(row_bits)
            debug_objects.append((f"row:{row.identifier}", row_bits))
            accumulated_rows.append(row)

    object_stream_bits = "".join(objects)
    stop_indexes = cumulative_stop_indexes(objects)
    stop_width = bits_required(max(stop_indexes))
    width_sentinel = encode_width_sentinel(stop_width)
    metadata_bits = encode_metadata(metadata)
    stop_index_bits = encode_stop_indexes(stop_indexes, stop_width)
    bitstream = width_sentinel + metadata_bits + stop_index_bits + object_stream_bits

    return EncodedMSS(
        bitstream=bitstream,
        width_sentinel=width_sentinel,
        metadata_bits=metadata_bits,
        stop_index_bits=stop_index_bits,
        object_stream_bits=object_stream_bits,
        stop_width=stop_width,
        stop_indexes=stop_indexes,
        metadata=metadata,
        isolated_rows=list(isolated_rows),
        object_slices=list(objects),
        debug_objects=debug_objects,
    )


def encode_mss_from_selection(selected_ids: Sequence[str], anthology_rows: Sequence[DatumRow]) -> EncodedMSS:
    isolated_rows, _id_map = compile_isolated_closure(selected_ids, anthology_rows)
    return encode_mss_from_isolated_rows(isolated_rows)


def decode_mss(bitstream: str) -> DecodedMSS:
    cursor = 0

    stop_width, cursor, width_sentinel = decode_width_sentinel(bitstream, cursor)
    metadata, cursor, metadata_bits = decode_metadata(bitstream, cursor)
    row_specs = expand_row_specs(metadata)

    object_count = len(row_specs) + count_cobm_objects_for_specs(row_specs)
    stop_indexes, cursor, stop_index_bits = decode_stop_indexes(bitstream, cursor, object_count, stop_width)

    object_stream_bits = bitstream[cursor:]
    object_slices = slice_by_stop_indexes(object_stream_bits, stop_indexes)

    grouped_specs = rows_grouped_by_layer(row_specs)
    populated_layers = sorted(grouped_specs.keys())

    decoded_rows: List[DatumRow] = []
    accumulated_rows: List[DatumRow] = []
    obj_i = 0
    debug_objects: List[Tuple[str, str]] = []

    for layer in populated_layers:
        layer_specs = grouped_specs[layer]

        if layer > 0:
            cobm_bits = object_slices[obj_i]
            obj_i += 1
            debug_objects.append((f"cobm:L{layer}", cobm_bits))
            active_set = decode_cobm(cobm_bits, accumulated_rows)
            ref_width = ref_width_for_active_set(len(active_set))
        else:
            active_set = []
            ref_width = 0

        for spec in layer_specs:
            row_bits = object_slices[obj_i]
            obj_i += 1
            row = decode_row_object(row_bits, spec, active_set, ref_width)
            decoded_rows.append(row)
            accumulated_rows.append(row)
            debug_objects.append((f"row:{row.identifier}", row_bits))

    return DecodedMSS(
        bitstream=bitstream,
        width_sentinel=width_sentinel,
        metadata_bits=metadata_bits,
        stop_index_bits=stop_index_bits,
        object_stream_bits=object_stream_bits,
        stop_width=stop_width,
        stop_indexes=list(stop_indexes),
        metadata=metadata,
        row_specs=row_specs,
        decoded_rows=decoded_rows,
        object_slices=object_slices,
        debug_objects=debug_objects,
    )


# ---------------------------------------------------------------------------
# Example from the discussion
# ---------------------------------------------------------------------------

def build_discussion_example_anthology() -> List[DatumRow]:
    """
    Build the user's example anthology:

        0-0-1
        0-0-2
        0-0-3
        0-0-4
        0-0-5
        1-1-1 -> 0-0-5, mag 256
        2-1-1 -> 1-1-1, mag 64
        3-1-1 -> 2-1-1, mag 0

    Only the transitive closure needed for 3-1-1 should be compiled.
    """
    return [
        DatumRow(layer=0, value_group=0, iteration=1, refs_only=[]),
        DatumRow(layer=0, value_group=0, iteration=2, refs_only=[]),
        DatumRow(layer=0, value_group=0, iteration=3, refs_only=[]),
        DatumRow(layer=0, value_group=0, iteration=4, refs_only=[]),
        DatumRow(layer=0, value_group=0, iteration=5, refs_only=[]),
        DatumRow(
            layer=1,
            value_group=1,
            iteration=1,
            tuples=[RefMagTuple(ref="0-0-5", magnitude=256)],
        ),
        DatumRow(
            layer=2,
            value_group=1,
            iteration=1,
            tuples=[RefMagTuple(ref="1-1-1", magnitude=64)],
        ),
        DatumRow(
            layer=3,
            value_group=1,
            iteration=1,
            tuples=[RefMagTuple(ref="2-1-1", magnitude=0)],
        ),
    ]


def discussion_example_selected_target() -> str:
    return "3-1-1"


def trace_discussion_example() -> Dict[str, object]:
    anthology = build_discussion_example_anthology()
    selected = [discussion_example_selected_target()]

    closure = transitive_closure(selected, anthology)
    isolated_rows, id_map = reindex_into_isolated_anthology(closure)
    encoded = encode_mss_from_isolated_rows(isolated_rows)
    decoded = decode_mss(encoded.bitstream)

    return {
        "selected": selected,
        "closure_old_ids": [row.identifier for row in closure],
        "isolated_id_map": dict(id_map),
        "isolated_rows": [row_to_debug_dict(row) for row in isolated_rows],
        "metadata": encoded.metadata.as_debug_dict(),
        "stop_width": encoded.stop_width,
        "stop_indexes": list(encoded.stop_indexes),
        "debug_objects": list(encoded.debug_objects),
        "bitstream": encoded.bitstream,
        "decoded_rows": [row_to_debug_dict(row) for row in decoded.decoded_rows],
    }


# ---------------------------------------------------------------------------
# Debug / display helpers
# ---------------------------------------------------------------------------

def row_to_debug_dict(row: DatumRow) -> Dict[str, object]:
    return {
        "identifier": row.identifier,
        "source_identifier": row.source_identifier,
        "layer": row.layer,
        "value_group": row.value_group,
        "iteration": row.iteration,
        "refs_only": list(row.refs_only),
        "tuples": [{"ref": item.ref, "magnitude": item.magnitude} for item in row.tuples],
    }


def pretty_print_trace(trace: Dict[str, object]) -> None:
    import json

    print("Selected target:")
    print(json.dumps(trace["selected"], indent=2))
    print()

    print("Old closure identifiers:")
    print(json.dumps(trace["closure_old_ids"], indent=2))
    print()

    print("Old -> isolated ID map:")
    print(json.dumps(trace["isolated_id_map"], indent=2))
    print()

    print("Isolated rows:")
    print(json.dumps(trace["isolated_rows"], indent=2))
    print()

    print("Metadata:")
    print(json.dumps(trace["metadata"], indent=2))
    print()

    print("Stop width:")
    print(trace["stop_width"])
    print()

    print("Stop indexes:")
    print(json.dumps(trace["stop_indexes"], indent=2))
    print()

    print("Objects:")
    print(json.dumps(trace["debug_objects"], indent=2))
    print()

    print("Bitstream:")
    print(trace["bitstream"])
    print()

    print("Decoded rows:")
    print(json.dumps(trace["decoded_rows"], indent=2))
    print()


# ---------------------------------------------------------------------------
# Minimal self-checks
# ---------------------------------------------------------------------------

def _assert_round_trip_example() -> None:
    trace = trace_discussion_example()
    isolated_ids = [row["identifier"] for row in trace["isolated_rows"]]
    decoded_ids = [row["identifier"] for row in trace["decoded_rows"]]
    if isolated_ids != decoded_ids:
        raise AssertionError(f"decoded identifiers differ: {isolated_ids} != {decoded_ids}")

    isolated_rows = trace["isolated_rows"]
    decoded_rows = trace["decoded_rows"]
    if isolated_rows != decoded_rows:
        raise AssertionError("decoded rows do not match isolated rows")

    # The critical correction: only the needed layer-0 datum survives into the isolated closure
    closure_old_ids = trace["closure_old_ids"]
    if closure_old_ids != ["0-0-5", "1-1-1", "2-1-1", "3-1-1"]:
        raise AssertionError(f"unexpected closure: {closure_old_ids}")

    # The isolated anthology should have one layer-0 row, not five
    metadata = trace["metadata"]
    if metadata["iteration_count_per_value_group"] != [1, 1, 1, 1]:
        raise AssertionError(f"unexpected isolated iteration counts: {metadata}")

    # The stop-index width must be driven by the largest stop position, not by a global address size
    max_stop = max(trace["stop_indexes"])
    if trace["stop_width"] != bits_required(max_stop):
        raise AssertionError("stop width does not match max stop index width rule")


if __name__ == "__main__":
    _assert_round_trip_example()
    pretty_print_trace(trace_discussion_example())
