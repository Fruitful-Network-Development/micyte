from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol, runtime_checkable

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


def _normalize_string_tuple(value: object, *, field_name: str) -> tuple[str, ...]:
    if value is None:
        return ()
    if not isinstance(value, (list, tuple)):
        raise ValueError(f"{field_name} must be a list, tuple, or null")
    normalized: list[str] = []
    seen: set[str] = set()
    for item in value:
        token = _as_text(item)
        if not token or token in seen:
            continue
        normalized.append(token)
        seen.add(token)
    return tuple(normalized)


@dataclass(frozen=True)
class PortalAuthorityRequest:
    scope_id: str
    known_tool_ids: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        scope_id = _as_text(self.scope_id)
        if not scope_id:
            raise ValueError("portal_authority_request.scope_id is required")
        object.__setattr__(self, "scope_id", scope_id)
        object.__setattr__(
            self,
            "known_tool_ids",
            _normalize_string_tuple(self.known_tool_ids, field_name="portal_authority_request.known_tool_ids"),
        )

    def to_dict(self) -> dict[str, JsonValue]:
        return {
            "scope_id": self.scope_id,
            "known_tool_ids": list(self.known_tool_ids),
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> PortalAuthorityRequest:
        if not isinstance(payload, dict):
            raise ValueError("portal_authority_request must be a dict")
        return cls(
            scope_id=payload.get("scope_id") or payload.get("portal_instance_id"),
            known_tool_ids=tuple(payload.get("known_tool_ids") or ()),
        )


@dataclass(frozen=True)
class PortalAuthoritySource:
    scope_id: str
    capabilities: tuple[str, ...]
    tool_exposure_policy: dict[str, JsonValue]
    ownership_posture: str = ""
    source_authority: str = "authoritative"

    def __post_init__(self) -> None:
        scope_id = _as_text(self.scope_id)
        if not scope_id:
            raise ValueError("portal_authority_source.scope_id is required")
        source_authority = _as_text(self.source_authority).lower() or "authoritative"
        if source_authority != "authoritative":
            raise ValueError("portal_authority_source.source_authority must be authoritative")
        object.__setattr__(self, "scope_id", scope_id)
        object.__setattr__(
            self,
            "capabilities",
            _normalize_string_tuple(self.capabilities, field_name="portal_authority_source.capabilities"),
        )
        normalized_policy = _normalize_json_value(
            self.tool_exposure_policy,
            field_name="portal_authority_source.tool_exposure_policy",
        )
        if not isinstance(normalized_policy, dict):
            raise ValueError("portal_authority_source.tool_exposure_policy must be a dict")
        object.__setattr__(self, "tool_exposure_policy", normalized_policy)
        object.__setattr__(self, "ownership_posture", _as_text(self.ownership_posture))
        object.__setattr__(self, "source_authority", source_authority)

    def to_dict(self) -> dict[str, JsonValue]:
        return {
            "scope_id": self.scope_id,
            "capabilities": list(self.capabilities),
            "tool_exposure_policy": self.tool_exposure_policy,
            "ownership_posture": self.ownership_posture,
            "source_authority": self.source_authority,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> PortalAuthoritySource:
        if not isinstance(payload, dict):
            raise ValueError("portal_authority_source must be a dict")
        return cls(
            scope_id=payload.get("scope_id") or payload.get("portal_instance_id"),
            capabilities=tuple(payload.get("capabilities") or ()),
            tool_exposure_policy=payload.get("tool_exposure_policy") or {},
            ownership_posture=payload.get("ownership_posture") or "",
            source_authority=payload.get("source_authority") or "authoritative",
        )


@dataclass(frozen=True)
class PortalAuthorityResult:
    source: PortalAuthoritySource | dict[str, Any] | None
    resolution_status: dict[str, JsonValue]
    warnings: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if self.source is None:
            normalized_source = None
        elif isinstance(self.source, PortalAuthoritySource):
            normalized_source = self.source
        elif isinstance(self.source, dict):
            normalized_source = PortalAuthoritySource.from_dict(self.source)
        else:
            raise ValueError("portal_authority_result.source must be PortalAuthoritySource, dict, or None")
        object.__setattr__(self, "source", normalized_source)
        normalized_status = _normalize_json_value(
            self.resolution_status,
            field_name="portal_authority_result.resolution_status",
        )
        if not isinstance(normalized_status, dict):
            raise ValueError("portal_authority_result.resolution_status must be a dict")
        object.__setattr__(self, "resolution_status", normalized_status)
        object.__setattr__(self, "warnings", tuple(_as_text(item) for item in self.warnings if _as_text(item)))

    @property
    def found(self) -> bool:
        return self.source is not None

    def to_dict(self) -> dict[str, JsonValue]:
        return {
            "found": self.found,
            "source": None if self.source is None else self.source.to_dict(),
            "resolution_status": self.resolution_status,
            "warnings": list(self.warnings),
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> PortalAuthorityResult:
        if not isinstance(payload, dict):
            raise ValueError("portal_authority_result must be a dict")
        warnings = payload.get("warnings") or ()
        if not isinstance(warnings, (list, tuple)):
            raise ValueError("portal_authority_result.warnings must be a list")
        return cls(
            source=payload.get("source"),
            resolution_status=payload.get("resolution_status") or {},
            warnings=tuple(str(item) for item in warnings),
        )


@runtime_checkable
class PortalAuthorityPort(Protocol):
    def read_portal_authority(self, request: PortalAuthorityRequest) -> PortalAuthorityResult:
        """Read portal-scope grants and tool-exposure posture for runtime composition."""
