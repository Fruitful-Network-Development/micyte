from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol, runtime_checkable

from micyte.core.identities import normalize_optional_plain_domain

JsonScalar = str | int | float | bool | None
JsonValue = JsonScalar | list["JsonValue"] | dict[str, "JsonValue"]


def _as_text(value: object) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _normalize_json_value(value: Any, *, field_name: str) -> JsonValue:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, list):
        return [_normalize_json_value(item, field_name=f"{field_name}[]") for item in value]
    if isinstance(value, dict):
        out: dict[str, JsonValue] = {}
        for key, item in value.items():
            token = _as_text(key)
            if not token:
                raise ValueError(f"{field_name} keys must be non-empty strings")
            out[token] = _normalize_json_value(item, field_name=f"{field_name}.{token}")
        return out
    raise ValueError(f"{field_name} must be JSON-serializable data")


def _normalize_payload(value: object, *, field_name: str) -> dict[str, JsonValue]:
    if not isinstance(value, dict):
        raise ValueError(f"{field_name} must be a dict")
    normalized = _normalize_json_value(value, field_name=field_name)
    if not isinstance(normalized, dict) or not normalized:
        raise ValueError(f"{field_name} must be a non-empty dict")
    return normalized


@dataclass(frozen=True)
class NetworkRootReadModelRequest:
    portal_tenant_id: str
    portal_domain: str = ""
    surface_query: dict[str, str] | None = None

    def __post_init__(self) -> None:
        portal_tenant_id = _as_text(self.portal_tenant_id).lower()
        if not portal_tenant_id:
            raise ValueError("network_root_read_model_request.portal_tenant_id is required")
        object.__setattr__(self, "portal_tenant_id", portal_tenant_id)
        object.__setattr__(
            self,
            "portal_domain",
            normalize_optional_plain_domain(
                self.portal_domain,
                field_name="network_root_read_model_request.portal_domain",
            ),
        )
        query = self.surface_query
        if query is None:
            normalized_query: dict[str, str] = {}
        elif isinstance(query, dict):
            normalized_query = {}
            for key, value in query.items():
                token = _as_text(key)
                if not token:
                    raise ValueError("network_root_read_model_request.surface_query keys must be non-empty")
                normalized_query[token] = _as_text(value)
        else:
            raise ValueError("network_root_read_model_request.surface_query must be a dict when provided")
        object.__setattr__(self, "surface_query", normalized_query)

    def to_dict(self) -> dict[str, JsonValue]:
        payload: dict[str, Any] = {
            "portal_tenant_id": self.portal_tenant_id,
            "portal_domain": self.portal_domain,
        }
        if self.surface_query:
            payload["surface_query"] = dict(self.surface_query)
        return payload

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> NetworkRootReadModelRequest:
        if not isinstance(payload, dict):
            raise ValueError("network_root_read_model_request must be a dict")
        return cls(
            portal_tenant_id=payload.get("portal_tenant_id"),
            portal_domain=payload.get("portal_domain") or "",
            surface_query=payload.get("surface_query") if "surface_query" in payload else None,
        )


@dataclass(frozen=True)
class NetworkRootReadModelSource:
    payload: dict[str, JsonValue]

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "payload",
            _normalize_payload(self.payload, field_name="network_root_read_model_source.payload"),
        )

    def to_dict(self) -> dict[str, JsonValue]:
        return {"payload": dict(self.payload)}

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> NetworkRootReadModelSource:
        if not isinstance(payload, dict):
            raise ValueError("network_root_read_model_source must be a dict")
        return cls(payload=payload.get("payload"))


@dataclass(frozen=True)
class NetworkRootReadModelResult:
    source: NetworkRootReadModelSource | None

    def __post_init__(self) -> None:
        if self.source is None:
            return
        if isinstance(self.source, NetworkRootReadModelSource):
            return
        if isinstance(self.source, dict):
            object.__setattr__(self, "source", NetworkRootReadModelSource.from_dict(self.source))
            return
        raise ValueError("network_root_read_model_result.source must be NetworkRootReadModelSource, dict, or None")

    @property
    def found(self) -> bool:
        return self.source is not None

    def to_dict(self) -> dict[str, JsonValue]:
        return {
            "found": self.found,
            "source": None if self.source is None else self.source.to_dict(),
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> NetworkRootReadModelResult:
        if not isinstance(payload, dict):
            raise ValueError("network_root_read_model_result must be a dict")
        return cls(source=payload.get("source"))


@runtime_checkable
class NetworkRootReadModelPort(Protocol):
    def read_network_root_model(self, request: NetworkRootReadModelRequest) -> NetworkRootReadModelResult:
        """Read the canonical system-log workbench model behind the V2 NETWORK root."""
