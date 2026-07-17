from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .time_address_schema import validate_address_with_schema

_MAX_TEMPORAL_DEPTH = 6


@dataclass(frozen=True)
class ParsedTimeAddress:
    segments: tuple[int, ...]
    prefix: tuple[int, int]
    temporal: tuple[int, ...]

    @property
    def depth(self) -> int:
        return len(self.temporal)


def _as_int_segments(address: str) -> tuple[int, ...]:
    token = str(address or "").strip()
    if not token:
        raise ValueError("time address is required")
    parts = token.split("-")
    if len(parts) < 3:
        raise ValueError("time address must include prefix and at least one temporal segment")
    values: list[int] = []
    for part in parts:
        piece = str(part).strip()
        if not piece.isdigit():
            raise ValueError(f"time address segment must be non-negative integer: {part!r}")
        values.append(int(piece))
    return tuple(values)


def parse_time_address(address: str) -> ParsedTimeAddress:
    segments = _as_int_segments(address)
    prefix = (segments[0], segments[1])
    temporal = segments[2:]
    return ParsedTimeAddress(segments=segments, prefix=prefix, temporal=temporal)


def normalize_time_address(address: str) -> str:
    parsed = parse_time_address(address)
    return "-".join(str(item) for item in parsed.segments)


def normalize_time_address_for_schema(address: str, schema_payload: dict[str, Any]) -> str:
    validation = validate_address_with_schema(address, schema_payload)
    if not bool(validation.get("ok")):
        raise ValueError(str(validation.get("error") or "time address does not satisfy schema authority"))
    return normalize_time_address(address)


def _schema_denotations(schema_payload: dict[str, Any]) -> tuple[int, ...]:
    schema = schema_payload.get("schema") if isinstance(schema_payload.get("schema"), dict) else {}
    out: list[int] = []
    for item in list(schema.get("denotations") or []):
        if isinstance(item, int) and item > 0:
            out.append(item)
    return tuple(out)


def _fallback_radix(idx: int) -> int:
    return 1000 if idx < 4 else 100


def _schema_is_authoritative(schema_payload: dict[str, Any] | None) -> bool:
    payload = schema_payload if isinstance(schema_payload, dict) else {}
    schema = payload.get("schema") if isinstance(payload.get("schema"), dict) else {}
    denotations = _schema_denotations(payload)
    mode = str(schema.get("validation_mode") or "").strip().lower()
    return bool(payload.get("ok")) and bool(denotations) and mode == "full"


def _effective_radices(schema_payload: dict[str, Any] | None, required_len: int) -> tuple[int, ...]:
    denotations = _schema_denotations(schema_payload or {})
    out = list(denotations[:required_len])
    while len(out) < required_len:
        out.append(_fallback_radix(len(out)))
    return tuple(max(1, int(item)) for item in out)


def _clamp_to_radices(segments: tuple[int, ...], radices: tuple[int, ...]) -> tuple[int, ...]:
    out: list[int] = []
    for idx, value in enumerate(segments):
        radix = radices[idx] if idx < len(radices) else _fallback_radix(idx)
        if radix <= 0:
            out.append(0)
            continue
        out.append(max(0, min(int(value), int(radix) - 1)))
    return tuple(out)


def _compose_scope(prefix: tuple[int, int], temporal: tuple[int, ...]) -> str:
    return "-".join(str(item) for item in (*prefix, *temporal))


def default_time_scope_for_schema(schema_payload: dict[str, Any], *, specificity: str = "day") -> str:
    if not _schema_is_authoritative(schema_payload):
        raise ValueError("time schema authority is unavailable or invalid")
    depth_by_specificity = {
        "cycle_group": 1,
        "cycle": 2,
        "day": 3,
        "hour": 4,
        "minute": 5,
        "second": 6,
    }
    depth = depth_by_specificity.get(str(specificity or "").strip().lower(), 3)
    temporal = tuple([0] * max(1, depth))
    return _compose_scope((0, 0), temporal)


def infer_specificity(address: str) -> str:
    depth = parse_time_address(address).depth
    if depth <= 1:
        return "cycle_group"
    if depth == 2:
        return "cycle"
    if depth == 3:
        return "day"
    if depth == 4:
        return "hour"
    if depth == 5:
        return "minute"
    if depth == 6:
        return "second"
    return f"segment_{depth}"


def compare_time_addresses(a: str, b: str) -> int:
    aa = parse_time_address(a).segments
    bb = parse_time_address(b).segments
    min_len = min(len(aa), len(bb))
    for idx in range(min_len):
        if aa[idx] < bb[idx]:
            return -1
        if aa[idx] > bb[idx]:
            return 1
    if len(aa) == len(bb):
        return 0
    return -1 if len(aa) < len(bb) else 1


def _same_prefix(a: ParsedTimeAddress, b: ParsedTimeAddress) -> bool:
    return a.prefix == b.prefix


def _pad_temporal(values: tuple[int, ...], depth: int, fill: int) -> tuple[int, ...]:
    if len(values) >= depth:
        return values[:depth]
    return tuple(list(values) + [fill] * (depth - len(values)))


def normalize_range(
    start: str,
    end: str,
    *,
    allow_repair: bool = True,
    schema_payload: dict[str, Any] | None = None,
) -> tuple[str, str]:
    a = parse_time_address(start)
    b = parse_time_address(end)
    if not _same_prefix(a, b):
        raise ValueError("range endpoints must share the same cosmological prefix")
    left = a.temporal
    right = b.temporal
    if len(left) != len(right):
        if not allow_repair:
            raise ValueError("mixed-specificity ranges are invalid without normalization")
        depth = max(len(left), len(right))
        left = _pad_temporal(left, depth, 0)
        if schema_payload is not None:
            radices = _effective_radices(schema_payload, 2 + depth)[2:]
            right_fill = tuple(max(0, int(item) - 1) for item in radices)
            right = tuple(list(right) + list(right_fill[len(right) : depth]))
        else:
            right = _pad_temporal(right, depth, 10**9)
    start_norm = _compose_scope(a.prefix, left)
    end_norm = _compose_scope(a.prefix, right)
    if schema_payload is not None:
        start_norm = normalize_time_address_for_schema(start_norm, schema_payload)
        end_norm = normalize_time_address_for_schema(end_norm, schema_payload)
    if compare_time_addresses(start_norm, end_norm) > 0:
        raise ValueError("range start must be <= range end")
    return start_norm, end_norm


def contains_address(container: str, candidate: str) -> bool:
    a = parse_time_address(container)
    b = parse_time_address(candidate)
    if not _same_prefix(a, b):
        return False
    if len(a.temporal) > len(b.temporal):
        return False
    for idx, value in enumerate(a.temporal):
        if b.temporal[idx] != value:
            return False
    return True


def projection_year_month_day(selected_scope: str, *, schema_payload: dict[str, Any] | None = None) -> dict[str, Any]:
    parsed = parse_time_address(selected_scope)
    denotations = _effective_radices(schema_payload, max(3, len(parsed.segments)))
    segment_radices = tuple(denotations[2:]) if len(denotations) >= 3 else ()
    return {
        "prefix": [parsed.prefix[0], parsed.prefix[1]],
        "cycle_group": int(parsed.temporal[0]) if len(parsed.temporal) >= 1 else 0,
        "cycle": int(parsed.temporal[1]) if len(parsed.temporal) >= 2 else 0,
        "day_in_cycle": int(parsed.temporal[2]) if len(parsed.temporal) >= 3 else 0,
        "hours_in_day": int(segment_radices[3]) if len(segment_radices) >= 4 else 24,
        "minutes_in_hour": int(segment_radices[4]) if len(segment_radices) >= 5 else 60,
        "seconds_in_minute": int(segment_radices[5]) if len(segment_radices) >= 6 else 60,
    }


__all__ = [
    "ParsedTimeAddress",
    "compare_time_addresses",
    "contains_address",
    "default_time_scope_for_schema",
    "infer_specificity",
    "normalize_range",
    "normalize_time_address",
    "normalize_time_address_for_schema",
    "parse_time_address",
    "projection_year_month_day",
]
