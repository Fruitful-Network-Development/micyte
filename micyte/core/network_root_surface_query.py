from __future__ import annotations

from collections.abc import Mapping
from typing import Any

NETWORK_ROOT_DEFAULT_VIEW = "map"
#: ONE view. `system_logs` was the root's only view until 2026-08-17, when the operator
#: made the Network page the map and the log rows became a contract's history in the
#: inbox. An old `?view=system_logs` bookmark canonicalizes to `map` rather than being
#: kept: keeping it would leave the canonical URL claiming a view the payload is not,
#: and an address that names one thing while the page shows another is worse than an
#: address that has been redirected.
NETWORK_ROOT_VIEWS = frozenset({"map"})
#: `node` is the map's selected pin, and it is in the canonical query for the reason
#: every other selection in this portal is: a view you cannot link to is a view you
#: cannot show anyone. `msn_filter` rides along because the map is drawn per instance —
#: dropping it here was why the network root's canonical URL forgot which portal you
#: were looking at.
NETWORK_ROOT_SUPPORTED_QUERY_KEYS = frozenset(
    {"view", "contract", "type", "record", "node", "msn_filter"}
)


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
    if view not in NETWORK_ROOT_VIEWS:
        view = NETWORK_ROOT_DEFAULT_VIEW

    out = {"view": view}
    if normalized.get("contract"):
        out["contract"] = normalized["contract"]
    if normalized.get("type"):
        out["type"] = normalized["type"]
    if normalized.get("record"):
        out["record"] = normalized["record"]
    if normalized.get("node"):
        out["node"] = normalized["node"]
    if normalized.get("msn_filter"):
        out["msn_filter"] = normalized["msn_filter"]
    return out, tuple(warnings)
