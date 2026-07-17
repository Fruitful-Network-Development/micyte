from __future__ import annotations

import re
from collections.abc import Iterable

from .structure import SamrasStructure, as_text
from .validation import (
    InvalidSamrasStructure,
    child_counts_from_addresses,
    derive_addresses_from_child_counts,
    validate_structure,
)

_BIN_RE = re.compile(r"^[01]+$")
_NUMERIC_HYPHEN_RE = re.compile(r"^[0-9]+(?:-[0-9]+)*$")
_LEGACY_HEADER_BITS = 8


def minimal_binary(value: int) -> str:
    token = int(value)
    if token < 0:
        raise InvalidSamrasStructure("values may not be negative")
    if token == 0:
        return "0"
    return format(token, "b")


def width_bits_for_integer(value: int) -> int:
    token = int(value)
    if token < 0:
        raise InvalidSamrasStructure("width cannot be computed for a negative integer")
    return 1 if token == 0 else len(format(token, "b"))


def encode_unary_width(width: int) -> str:
    token = int(width)
    if token <= 0:
        raise InvalidSamrasStructure("width must be positive")
    return ("0" * token) + "1"


def decode_unary_width(bitstream: str, start_index: int) -> tuple[int, int]:
    count = 0
    cursor = int(start_index)
    while cursor < len(bitstream) and bitstream[cursor] == "0":
        count += 1
        cursor += 1
    if cursor >= len(bitstream) or bitstream[cursor] != "1":
        raise InvalidSamrasStructure("unterminated unary width field")
    if count <= 0:
        raise InvalidSamrasStructure("width field must encode a positive width")
    return count, cursor + 1


def compute_stop_addresses(value_tokens: Iterable[str]) -> tuple[int, ...]:
    tokens = [str(item) for item in value_tokens]
    total = 0
    stops: list[int] = []
    for token in tokens[:-1]:
        total += len(token)
        stops.append(total)
    return tuple(stops)


def _structure_from_values(
    values: Iterable[int],
    *,
    root_ref: str = "0-0-5",
    source_format: str = "canonical",
    canonical_state: str = "canonical",
    warnings: Iterable[str] = (),
    bitstream_override: str = "",
    address_width_bits_override: int | None = None,
    stop_count_width_bits_override: int | None = None,
) -> SamrasStructure:
    value_list = [int(item) for item in values]
    addresses = derive_addresses_from_child_counts(value_list)
    value_tokens = tuple(minimal_binary(item) for item in value_list)
    stop_addresses = compute_stop_addresses(value_tokens)
    address_width_bits = (
        int(address_width_bits_override)
        if address_width_bits_override is not None
        else width_bits_for_integer(max(stop_addresses) if stop_addresses else 0)
    )
    stop_count = len(stop_addresses)
    stop_count_width_bits = (
        int(stop_count_width_bits_override)
        if stop_count_width_bits_override is not None
        else width_bits_for_integer(stop_count)
    )
    if bitstream_override:
        bitstream = str(bitstream_override)
    else:
        parts = [
            encode_unary_width(address_width_bits),
            encode_unary_width(stop_count_width_bits),
            format(stop_count, f"0{stop_count_width_bits}b"),
            "".join(format(item, f"0{address_width_bits}b") for item in stop_addresses),
            "".join(value_tokens),
        ]
        bitstream = "".join(parts)
    structure = SamrasStructure(
        root_ref=as_text(root_ref) or "0-0-5",
        bitstream=bitstream,
        address_width_bits=address_width_bits,
        stop_count_width_bits=stop_count_width_bits,
        stop_count=stop_count,
        stop_addresses=tuple(int(item) for item in stop_addresses),
        value_tokens=value_tokens,
        values=tuple(value_list),
        addresses=tuple(addresses),
        source_format=as_text(source_format) or "canonical",
        canonical_state=as_text(canonical_state) or "canonical",
        warnings=tuple(str(item) for item in warnings if as_text(item)),
    )
    report = validate_structure(structure, require_canonical_roundtrip=True)
    if not report.ok:
        raise InvalidSamrasStructure("; ".join(report.errors))
    return structure


def encode_canonical_structure_from_addresses(
    addresses: Iterable[str],
    *,
    root_ref: str = "0-0-5",
    warnings: Iterable[str] = (),
) -> SamrasStructure:
    values = child_counts_from_addresses(list(addresses))
    return _structure_from_values(values, root_ref=root_ref, source_format="canonical", canonical_state="canonical", warnings=warnings)


def encode_canonical_structure_from_values(
    values: Iterable[int],
    *,
    root_ref: str = "0-0-5",
    warnings: Iterable[str] = (),
) -> SamrasStructure:
    return _structure_from_values(values, root_ref=root_ref, source_format="canonical", canonical_state="canonical", warnings=warnings)


def decode_canonical_bitstream(bitstream: str, *, root_ref: str = "0-0-5") -> SamrasStructure:
    token = as_text(bitstream)
    if not token or _BIN_RE.fullmatch(token) is None:
        raise InvalidSamrasStructure("canonical SAMRAS bitstream must contain only 0 and 1")
    cursor = 0
    address_width_bits, cursor = decode_unary_width(token, cursor)
    stop_count_width_bits, cursor = decode_unary_width(token, cursor)
    stop_count_bits = token[cursor : cursor + stop_count_width_bits]
    if len(stop_count_bits) != stop_count_width_bits:
        raise InvalidSamrasStructure("truncated stop-count field")
    stop_count = int(stop_count_bits, 2)
    cursor += stop_count_width_bits
    stop_addresses: list[int] = []
    for _ in range(stop_count):
        stop_bits = token[cursor : cursor + address_width_bits]
        if len(stop_bits) != address_width_bits:
            raise InvalidSamrasStructure("truncated stop-address array")
        stop_addresses.append(int(stop_bits, 2))
        cursor += address_width_bits
    value_stream = token[cursor:]
    if not value_stream:
        raise InvalidSamrasStructure("missing value stream")
    starts = [0, *stop_addresses]
    ends = [*stop_addresses, len(value_stream)]
    value_tokens = [value_stream[left:right] for left, right in zip(starts, ends, strict=False)]
    if any(item == "" for item in value_tokens):
        raise InvalidSamrasStructure("empty value token")
    values = [int(item, 2) for item in value_tokens]
    structure = _structure_from_values(
        values,
        root_ref=root_ref,
        source_format="canonical",
        canonical_state="canonical",
        warnings=(),
        bitstream_override=token,
        address_width_bits_override=address_width_bits,
        stop_count_width_bits_override=stop_count_width_bits,
    )
    if structure.bitstream != token:
        raise InvalidSamrasStructure("decoded bitstream is structurally valid but not canonical")
    return structure


def decode_legacy_fixed_header_bitstream(bitstream: str, *, root_ref: str = "0-0-5") -> SamrasStructure:
    token = as_text(bitstream)
    if not token or _BIN_RE.fullmatch(token) is None:
        raise InvalidSamrasStructure("legacy SAMRAS bitstream must contain only 0 and 1")
    if len(token) < (_LEGACY_HEADER_BITS * 2):
        raise InvalidSamrasStructure("legacy SAMRAS bitstream is shorter than its fixed headers")
    cursor = 0
    address_width_bits = int(token[cursor : cursor + _LEGACY_HEADER_BITS], 2)
    cursor += _LEGACY_HEADER_BITS
    stop_count_width_bits = int(token[cursor : cursor + _LEGACY_HEADER_BITS], 2)
    cursor += _LEGACY_HEADER_BITS
    if address_width_bits <= 0:
        raise InvalidSamrasStructure("legacy address width must be positive")
    if stop_count_width_bits <= 0:
        raise InvalidSamrasStructure("legacy stop-count width must be positive")
    stop_count_bits = token[cursor : cursor + stop_count_width_bits]
    if len(stop_count_bits) != stop_count_width_bits:
        raise InvalidSamrasStructure("truncated legacy stop-count field")
    stop_count = int(stop_count_bits, 2)
    cursor += stop_count_width_bits
    stop_addresses: list[int] = []
    for _ in range(stop_count):
        stop_bits = token[cursor : cursor + address_width_bits]
        if len(stop_bits) != address_width_bits:
            raise InvalidSamrasStructure("truncated legacy stop-address array")
        stop_addresses.append(int(stop_bits, 2))
        cursor += address_width_bits
    value_stream = token[cursor:]
    if not value_stream:
        raise InvalidSamrasStructure("legacy value stream is empty")
    starts = [0, *stop_addresses]
    ends = [*stop_addresses, len(value_stream)]
    value_tokens = [value_stream[left:right] for left, right in zip(starts, ends, strict=False)]
    if any(item == "" for item in value_tokens):
        raise InvalidSamrasStructure("legacy value stream contains an empty token")
    values = [int(item, 2) for item in value_tokens]
    return _structure_from_values(
        values,
        root_ref=root_ref,
        source_format="legacy_fixed_header_binary",
        canonical_state="provisional_legacy",
        warnings=("legacy fixed-header SAMRAS bitstream was decoded and should be rewritten canonically",),
    )


def decode_legacy_hyphen_payload(raw: str, *, root_ref: str = "0-0-5") -> SamrasStructure:
    token = as_text(raw)
    if not token or _NUMERIC_HYPHEN_RE.fullmatch(token) is None:
        raise InvalidSamrasStructure("legacy SAMRAS payload must be numeric-hyphen")
    values: list[int] = []
    warnings: list[str] = ["legacy hyphen SAMRAS payload was decoded and should be rewritten canonically"]
    for item in token.split("-"):
        part = as_text(item)
        if not part:
            continue
        if all(ch in {"0", "1"} for ch in part) and len(part) > 1:
            values.append(int(part, 2))
            warnings.append(f"legacy binary-token segment normalized: {part}")
            continue
        values.append(int(part, 10))
    return _structure_from_values(
        values,
        root_ref=root_ref,
        source_format="legacy_hyphen",
        canonical_state="provisional_legacy",
        warnings=warnings,
    )


def decode_structure(raw: str, *, root_ref: str = "0-0-5") -> SamrasStructure:
    token = as_text(raw)
    if not token:
        raise InvalidSamrasStructure("SAMRAS structure payload is required")
    if _BIN_RE.fullmatch(token):
        try:
            return decode_canonical_bitstream(token, root_ref=root_ref)
        except InvalidSamrasStructure:
            return decode_legacy_fixed_header_bitstream(token, root_ref=root_ref)
    return decode_legacy_hyphen_payload(token, root_ref=root_ref)
