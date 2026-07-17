"""Canonical public API for HOPS coordinate decode and geometry assembly.

This package re-exports HOPS coordinate classification/decoding and the
chronology / time-address helpers from
``micyte.core.structures.hops``, plus the generic
polygon/multi-polygon row-group assembler used by the spatial chain
(family ``4 → 5 → 6 → 7``).

The implementation is intentionally pure-stdlib and file-agnostic.
"""

from __future__ import annotations

from micyte.core.structures.hops import (
    ChronologyAuthority,
    ParsedTimeAddress,
    TimeAddressSchema,
    anchor_path_for_tool,
    build_chronology_authority,
    classify_hops_coordinate_token,
    compare_time_addresses,
    contains_address,
    decode_hops_coordinate_token,
    decode_mixed_radix_magnitude,
    default_time_scope_for_schema,
    encode_unix_ms_as_hops,
    encode_utc_datetime_as_hops,
    infer_specificity,
    normalize_range,
    normalize_time_address,
    normalize_time_address_for_schema,
    parse_time_address,
    projection_year_month_day,
    schema_from_anchor_payload,
    validate_address_with_schema,
)

from .polygon_groups import assemble_polygon_groups

__all__ = [
    "ChronologyAuthority",
    "ParsedTimeAddress",
    "TimeAddressSchema",
    "anchor_path_for_tool",
    "assemble_polygon_groups",
    "build_chronology_authority",
    "classify_hops_coordinate_token",
    "compare_time_addresses",
    "contains_address",
    "decode_hops_coordinate_token",
    "decode_mixed_radix_magnitude",
    "default_time_scope_for_schema",
    "encode_unix_ms_as_hops",
    "encode_utc_datetime_as_hops",
    "infer_specificity",
    "normalize_range",
    "normalize_time_address",
    "normalize_time_address_for_schema",
    "parse_time_address",
    "projection_year_month_day",
    "schema_from_anchor_payload",
    "validate_address_with_schema",
]
