"""Pure HOPS coordinate and chronology helpers for V2 surfaces."""

from __future__ import annotations

from typing import Any

from .chronology import (
    ChronologyAuthority,
    build_chronology_authority,
    decode_hops_as_utc_datetime,
    encode_unix_ms_as_hops,
    encode_utc_datetime_as_hops,
)
from .cyclical import (
    DAYS_PER_QUADRENNIUM,
    EPOCH,
    HC_MAGNITUDE_BITS,
    LC_MAGNITUDE_BITS,
    QC_MAGNITUDE_BITS,
    current_open_window,
    cycle_start_year_of,
    date_of_qc_day,
    encode_mixed_radix_magnitude,
    format_ic_stamp,
    hc_day_of,
    lc_day_of,
    next_hc_occurrences,
    open_runs_from_closures,
    parse_ic_stamp,
    qc_day_in_closures,
    qc_day_of,
)
from .time_address import (
    ParsedTimeAddress,
    compare_time_addresses,
    contains_address,
    default_time_scope_for_schema,
    infer_specificity,
    normalize_range,
    normalize_time_address,
    normalize_time_address_for_schema,
    parse_time_address,
    projection_year_month_day,
)
from .time_address_schema import (
    TimeAddressSchema,
    anchor_path_for_tool,
    decode_mixed_radix_magnitude,
    schema_from_anchor_payload,
    validate_address_with_schema,
)

_DEFAULT_HOPS_RADICES = (8, 81, 100, 100, 100, 100)


def _as_text(value: object) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _looks_like_hyphenated_hex(token: str) -> bool:
    if "-" not in token:
        return False
    parts = [part for part in token.split("-") if part]
    if not parts:
        return False
    if all(part.isdigit() for part in parts):
        return False
    compact = "".join(parts)
    if not compact or (len(compact) % 2) != 0:
        return False
    return all(part.isalnum() and all(ch in "0123456789abcdefABCDEF" for ch in part) for part in parts)


def _as_hops_radices(schema_payload: dict[str, Any] | None) -> tuple[int, ...]:
    if isinstance(schema_payload, dict):
        schema = schema_payload.get("schema")
        if isinstance(schema, dict):
            denotations = schema.get("denotations")
            if isinstance(denotations, list):
                out = [int(item) for item in denotations if isinstance(item, int) and item > 0]
                if out:
                    return tuple(out)
    return _DEFAULT_HOPS_RADICES


def _radix_for_index(radices: tuple[int, ...], index: int) -> int:
    if index < len(radices):
        return int(radices[index])
    return 100


def classify_hops_coordinate_token(
    raw_value: Any,
    *,
    schema_payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    token = _as_text(raw_value)
    if not token:
        return {"classification": "invalid", "reason": "empty token", "token": token}
    if _looks_like_hyphenated_hex(token):
        return {
            "classification": "ambiguous",
            "reason": "token is hyphenated hex and can be interpreted multiple ways",
            "token": token,
        }
    parts = token.split("-")
    if "-" not in token or any(not piece.isdigit() for piece in parts):
        return {"classification": "invalid", "reason": "token is not a numeric hyphenated HOPS coordinate", "token": token}
    segments = tuple(int(piece) for piece in parts)
    radices = _as_hops_radices(schema_payload)
    for idx, value in enumerate(segments):
        radix = _radix_for_index(radices, idx)
        if value < 0 or value >= radix:
            return {"classification": "invalid", "reason": "token exceeds HOPS radix bounds", "token": token}
    return {"classification": "hops", "reason": "token matches HOPS schema", "token": token}


def decode_hops_coordinate_token(
    raw_value: Any,
    *,
    schema_payload: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    classification = classify_hops_coordinate_token(raw_value, schema_payload=schema_payload)
    if classification.get("classification") != "hops":
        return None

    token = _as_text(raw_value)
    segments = tuple(int(piece) for piece in token.split("-"))
    radices = _as_hops_radices(schema_payload)

    lon_min, lon_max = -180.0, 180.0
    lat_min, lat_max = -90.0, 90.0
    partition_dims = segments[2:]
    for idx, value in enumerate(partition_dims):
        radix = max(1, _radix_for_index(radices, idx + 2))
        if idx % 2 == 0:
            span = (lon_max - lon_min) / radix
            lon_min = lon_min + (span * value)
            lon_max = lon_min + span
        else:
            span = (lat_max - lat_min) / radix
            lat_min = lat_min + (span * value)
            lat_max = lat_min + span

    longitude = (lon_min + lon_max) / 2.0
    latitude = (lat_min + lat_max) / 2.0
    return {
        "encoding": "hops_mixed_radix",
        "address": token,
        "segments": list(segments),
        "radices": [_radix_for_index(radices, idx) for idx in range(len(segments))],
        "longitude": {
            "value": longitude,
            "text": f"{longitude:.13f}",
            "range": [lon_min, lon_max],
        },
        "latitude": {
            "value": latitude,
            "text": f"{latitude:.13f}",
            "range": [lat_min, lat_max],
        },
        "pair_text": [f"{longitude:.13f}", f"{latitude:.13f}"],
    }


__all__ = [
    "ChronologyAuthority",
    "DAYS_PER_QUADRENNIUM",
    "EPOCH",
    "HC_MAGNITUDE_BITS",
    "LC_MAGNITUDE_BITS",
    "ParsedTimeAddress",
    "QC_MAGNITUDE_BITS",
    "TimeAddressSchema",
    "anchor_path_for_tool",
    "build_chronology_authority",
    "classify_hops_coordinate_token",
    "compare_time_addresses",
    "contains_address",
    "current_open_window",
    "cycle_start_year_of",
    "date_of_qc_day",
    "decode_hops_as_utc_datetime",
    "decode_mixed_radix_magnitude",
    "decode_hops_coordinate_token",
    "default_time_scope_for_schema",
    "encode_mixed_radix_magnitude",
    "encode_unix_ms_as_hops",
    "encode_utc_datetime_as_hops",
    "format_ic_stamp",
    "hc_day_of",
    "infer_specificity",
    "lc_day_of",
    "next_hc_occurrences",
    "normalize_range",
    "normalize_time_address",
    "normalize_time_address_for_schema",
    "open_runs_from_closures",
    "parse_ic_stamp",
    "parse_time_address",
    "projection_year_month_day",
    "qc_day_in_closures",
    "qc_day_of",
    "schema_from_anchor_payload",
    "validate_address_with_schema",
]
