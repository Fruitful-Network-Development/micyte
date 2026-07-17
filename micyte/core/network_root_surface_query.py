from __future__ import annotations

from collections.abc import Mapping
from typing import Any

NETWORK_ROOT_DEFAULT_VIEW = "system_logs"
NETWORK_ROOT_SUPPORTED_QUERY_KEYS = frozenset({"view", "contract", "type", "record"})


def _as_text(value: object) -> str:
    if value is None:
        return ""
    return str(value).strip()


def normalize_network_surface_query(query: Mapping[str, Any] | None) -> tuple[dict[str, str], tuple[str, ...]]:
    normalized: dict[str, str] = {}
    for raw_key, raw_value in dict(query or {}).items():
        key = _as_text(raw_key)
        if not key:
            continue
        normalized[key] = _as_text(raw_value)

    unknown_keys = sorted(key for key in normalized if key not in NETWORK_ROOT_SUPPORTED_QUERY_KEYS)
    warnings: list[str] = []
    if unknown_keys:
        warnings.append(
            "Ignored unsupported NETWORK surface_query key(s): " + ", ".join(unknown_keys)
        )

    view = normalized.get("view") or NETWORK_ROOT_DEFAULT_VIEW
    if view != NETWORK_ROOT_DEFAULT_VIEW:
        view = NETWORK_ROOT_DEFAULT_VIEW

    out = {"view": view}
    if normalized.get("contract"):
        out["contract"] = normalized["contract"]
    if normalized.get("type"):
        out["type"] = normalized["type"]
    if normalized.get("record"):
        out["record"] = normalized["record"]
    return out, tuple(warnings)
