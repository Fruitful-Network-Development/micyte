from __future__ import annotations

from datetime import datetime
from typing import Any

from micyte.core.network_root_surface_query import normalize_network_surface_query
from micyte.core.structures.hops.chronology import (
    ChronologyAuthority,
    build_chronology_authority,
    encode_utc_datetime_as_hops,
)
from micyte.core.structures.hops.time_address import compare_time_addresses
from micyte.core.structures.hops.time_address_schema import (
    schema_from_anchor_payload,
    validate_address_with_schema,
)

LOG_KIND_ID_KEY = "event_type_id"
LOCAL_LOG_KIND_ID_KEY = "local_event_type_id"
LOG_KIND_LABEL_KEY = "event_type_label"
LOG_KIND_SLUG_KEY = "event_type_slug"
LOG_KIND_FILTERS_KEY = "event_type_filters"
LOG_KIND_COUNT_KEY = "event_type_count"
LOG_KIND_COUNTS_KEY = "event_type_counts"
LOG_KIND_COLLECTION_LABEL = "event_type_collection"
LOG_KIND_BABELETTE_LABEL = "event_type_babelette"


def _as_text(value: object) -> str:
    if value is None:
        return ""
    return str(value).strip()


def build_network_chronology_authority(
    *,
    schema_payload: dict[str, Any],
    quadrennium_payload: dict[str, Any],
) -> ChronologyAuthority:
    return build_chronology_authority(
        schema_payload=schema_payload,
        quadrennium_payload=quadrennium_payload,
    )


def compare_network_hops_addresses(left: str, right: str) -> int:
    return compare_time_addresses(left, right)


def encode_network_datetime_as_hops(timestamp: datetime, *, authority: ChronologyAuthority) -> str:
    return encode_utc_datetime_as_hops(timestamp, authority=authority)


def network_hops_schema_from_anchor_payload(payload: dict[str, Any]) -> dict[str, Any]:
    return schema_from_anchor_payload(payload)


def validate_network_hops_address(address: str, schema_payload: dict[str, Any]) -> dict[str, Any]:
    return validate_address_with_schema(address, schema_payload)


def classify_network_log_kind(payload: dict[str, Any]) -> str:
    for key in ("type", "event_type", "schema"):
        value = payload.get(key)
        token = "" if value is None else str(value).strip()
        if token:
            return token
    return "unknown"


def build_log_kind_entry(*, kind_id: str, local_kind_id: str, slug: str, label: str) -> dict[str, str]:
    return {
        LOG_KIND_ID_KEY: kind_id,
        LOCAL_LOG_KIND_ID_KEY: local_kind_id,
        "slug": slug,
        "label": label,
    }


def build_log_kind_filter(
    *,
    kind_id: str,
    entry: dict[str, Any],
    count: int,
    active: bool,
) -> dict[str, Any]:
    return {
        LOG_KIND_ID_KEY: kind_id,
        "label": str(entry.get("label") or entry.get("slug") or kind_id).strip(),
        "slug": str(entry.get("slug") or "").strip(),
        "count": int(count),
        "active": bool(active),
    }


__all__ = [
    "LOCAL_LOG_KIND_ID_KEY",
    "LOG_KIND_BABELETTE_LABEL",
    "LOG_KIND_COLLECTION_LABEL",
    "LOG_KIND_COUNTS_KEY",
    "LOG_KIND_COUNT_KEY",
    "LOG_KIND_FILTERS_KEY",
    "LOG_KIND_ID_KEY",
    "LOG_KIND_LABEL_KEY",
    "LOG_KIND_SLUG_KEY",
    "ChronologyAuthority",
    "build_log_kind_entry",
    "build_log_kind_filter",
    "build_network_chronology_authority",
    "classify_network_log_kind",
    "compare_network_hops_addresses",
    "encode_network_datetime_as_hops",
    "network_hops_schema_from_anchor_payload",
    "normalize_network_surface_query",
    "validate_network_hops_address",
]
