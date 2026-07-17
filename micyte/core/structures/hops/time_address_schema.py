from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class TimeAddressSchema:
    denotations: tuple[int, ...]
    stop_index_width: int
    denotation_count_width: int
    denotation_count: int
    stop_indexes: tuple[int, ...]


def _text(value: object) -> str:
    return "" if value is None else str(value).strip()


def _read_unary_width(bits: str, pos: int) -> tuple[int, int]:
    zeros = 0
    while pos < len(bits) and bits[pos] == "0":
        zeros += 1
        pos += 1
    if pos >= len(bits) or bits[pos] != "1":
        raise ValueError("invalid unary-width segment")
    pos += 1
    return zeros, pos


def _read_fixed(bits: str, pos: int, width: int) -> tuple[int, int]:
    if width <= 0:
        raise ValueError("fixed-width field must be > 0")
    end = pos + width
    if end > len(bits):
        raise ValueError("bit stream ended before fixed-width field")
    token = bits[pos:end]
    return int(token, 2), end


def decode_mixed_radix_magnitude(encoded_bits: str) -> TimeAddressSchema:
    bits = _text(encoded_bits)
    if not bits or any(ch not in {"0", "1"} for ch in bits):
        raise ValueError("magnitude must be a binary string")
    pos = 0
    stop_width, pos = _read_unary_width(bits, pos)
    count_width, pos = _read_unary_width(bits, pos)
    denotation_count, pos = _read_fixed(bits, pos, count_width)
    if denotation_count <= 0:
        raise ValueError("denotation count must be positive")
    stop_indexes: list[int] = []
    for _ in range(max(0, denotation_count - 1)):
        idx, pos = _read_fixed(bits, pos, stop_width)
        stop_indexes.append(idx)
    payload = bits[pos:]
    if denotation_count == 1:
        if not payload:
            raise ValueError("empty payload for single denotation schema")
        return TimeAddressSchema(
            denotations=(int(payload, 2),),
            stop_index_width=stop_width,
            denotation_count_width=count_width,
            denotation_count=denotation_count,
            stop_indexes=(),
        )
    prev = 0
    for stop in stop_indexes:
        if stop <= prev:
            raise ValueError("stop indexes must be strictly increasing")
        if stop > len(payload):
            raise ValueError("stop index exceeds payload length")
        prev = stop
    slices: list[str] = []
    start = 0
    for stop in stop_indexes:
        slices.append(payload[start:stop])
        start = stop
    slices.append(payload[start:])
    if len(slices) != denotation_count or any(not token for token in slices):
        raise ValueError("schema payload segments could not be reconstructed")
    denotations = tuple(int(token, 2) for token in slices)
    return TimeAddressSchema(
        denotations=denotations,
        stop_index_width=stop_width,
        denotation_count_width=count_width,
        denotation_count=denotation_count,
        stop_indexes=tuple(stop_indexes),
    )


def schema_from_anchor_payload(anchor_payload: dict[str, Any]) -> dict[str, Any]:
    row = anchor_payload.get("1-1-1")
    if not isinstance(row, list) or not row:
        return {"ok": False, "error": "datum 1-1-1 is missing", "schema": {}}
    header = row[0] if isinstance(row[0], list) else []
    if len(header) < 3:
        return {"ok": False, "error": "datum 1-1-1 header is malformed", "schema": {}}
    magnitude_bits = _text(header[2])
    label = ""
    if len(row) > 1 and isinstance(row[1], list) and row[1]:
        label = _text(row[1][0])
    try:
        decoded = decode_mixed_radix_magnitude(magnitude_bits)
    except Exception as exc:
        return {
            "ok": False,
            "error": str(exc),
            "schema": {"datum_id": "1-1-1", "label": label, "magnitude_bits": magnitude_bits},
        }
    return {
        "ok": True,
        "schema": {
            "datum_id": "1-1-1",
            "label": label or "UTC_mixed_radix",
            "magnitude_bits": magnitude_bits,
            "denotations": list(decoded.denotations),
            "validation_mode": "full",
            "stop_index_width": decoded.stop_index_width,
            "denotation_count_width": decoded.denotation_count_width,
            "denotation_count": decoded.denotation_count,
            "stop_indexes": list(decoded.stop_indexes),
        },
    }


def validate_address_with_schema(address: str, schema_payload: dict[str, Any]) -> dict[str, Any]:
    token = _text(address)
    if not token:
        return {"ok": False, "error": "address is required"}
    parts = token.split("-")
    if any(not part.isdigit() for part in parts):
        return {"ok": False, "error": "address segments must be non-negative integers"}
    segments = [int(part) for part in parts]
    schema = schema_payload.get("schema") if isinstance(schema_payload.get("schema"), dict) else {}
    if not bool(schema_payload.get("ok")):
        return {"ok": False, "error": str(schema_payload.get("error") or "schema unavailable"), "mode": "unavailable"}
    denotations = [int(x) for x in list(schema.get("denotations") or []) if isinstance(x, int)]
    if not denotations:
        return {"ok": False, "error": "schema has no denotations", "mode": "unavailable"}
    mode = str(schema.get("validation_mode") or "full")
    if mode != "full":
        return {"ok": False, "error": f"unsupported validation mode: {mode}", "mode": "unavailable"}
    if len(segments) > len(denotations):
        return {"ok": False, "error": "address has more segments than schema allows"}
    for idx, value in enumerate(segments):
        if value < 0 or value >= denotations[idx]:
            return {"ok": False, "error": f"segment[{idx}] out of schema range"}
    return {"ok": True, "mode": "full", "warnings": []}


def _tool_sandbox_root(path: Path) -> Path:
    token = Path(path)
    if token.name == "sandbox":
        return token
    if token.name == "data":
        return token / "sandbox"
    if token.name == "private":
        return token.parent / "data" / "sandbox"
    return token / "sandbox"


def anchor_path_for_tool(state_root: Path, tool_slug: str, anchor_file: str) -> Path:
    return _tool_sandbox_root(Path(state_root)) / tool_slug / anchor_file


__all__ = [
    "TimeAddressSchema",
    "anchor_path_for_tool",
    "decode_mixed_radix_magnitude",
    "schema_from_anchor_payload",
    "validate_address_with_schema",
]
