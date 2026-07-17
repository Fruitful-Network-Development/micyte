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


def _normalize_object_payload(value: Any, *, field_name: str) -> dict[str, JsonValue]:
    normalized = _normalize_json_value(value, field_name=field_name)
    if not isinstance(normalized, dict):
        raise ValueError(f"{field_name} must be a dict")
    return normalized


@dataclass(frozen=True)
class DirectiveContextRequest:
    portal_instance_id: str
    tool_id: str
    subject_hyphae_hash: str = ""
    subject_version_hash: str = ""

    def __post_init__(self) -> None:
        portal_instance_id = _as_text(self.portal_instance_id)
        tool_id = _as_text(self.tool_id)
        subject_hyphae_hash = _as_text(self.subject_hyphae_hash)
        subject_version_hash = _as_text(self.subject_version_hash)
        if not portal_instance_id:
            raise ValueError("directive_context_request.portal_instance_id is required")
        if not tool_id:
            raise ValueError("directive_context_request.tool_id is required")
        if not subject_hyphae_hash and not subject_version_hash:
            raise ValueError("directive_context_request requires subject_hyphae_hash or subject_version_hash")
        object.__setattr__(self, "portal_instance_id", portal_instance_id)
        object.__setattr__(self, "tool_id", tool_id)
        object.__setattr__(self, "subject_hyphae_hash", subject_hyphae_hash)
        object.__setattr__(self, "subject_version_hash", subject_version_hash)

    def to_dict(self) -> dict[str, JsonValue]:
        return {
            "portal_instance_id": self.portal_instance_id,
            "tool_id": self.tool_id,
            "subject_hyphae_hash": self.subject_hyphae_hash,
            "subject_version_hash": self.subject_version_hash,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> DirectiveContextRequest:
        if not isinstance(payload, dict):
            raise ValueError("directive_context_request must be a dict")
        return cls(
            portal_instance_id=payload.get("portal_instance_id") or payload.get("scope_id"),
            tool_id=payload.get("tool_id") or payload.get("surface_id"),
            subject_hyphae_hash=payload.get("subject_hyphae_hash") or "",
            subject_version_hash=payload.get("subject_version_hash") or "",
        )


@dataclass(frozen=True)
class DirectiveContextSource:
    context_id: str
    portal_instance_id: str
    tool_id: str
    subject_hyphae_hash: str = ""
    subject_version_hash: str = ""
    nimm_state: dict[str, JsonValue] | None = None
    aitas_state: dict[str, JsonValue] | None = None
    scope: dict[str, JsonValue] | None = None
    provenance: dict[str, JsonValue] | None = None
    source_authority: str = "authoritative"

    def __post_init__(self) -> None:
        context_id = _as_text(self.context_id)
        portal_instance_id = _as_text(self.portal_instance_id)
        tool_id = _as_text(self.tool_id)
        subject_hyphae_hash = _as_text(self.subject_hyphae_hash)
        subject_version_hash = _as_text(self.subject_version_hash)
        source_authority = _as_text(self.source_authority).lower() or "authoritative"
        if not context_id:
            raise ValueError("directive_context_source.context_id is required")
        if not portal_instance_id:
            raise ValueError("directive_context_source.portal_instance_id is required")
        if not tool_id:
            raise ValueError("directive_context_source.tool_id is required")
        if not subject_hyphae_hash and not subject_version_hash:
            raise ValueError("directive_context_source requires subject_hyphae_hash or subject_version_hash")
        if source_authority != "authoritative":
            raise ValueError("directive_context_source.source_authority must be authoritative")
        object.__setattr__(self, "context_id", context_id)
        object.__setattr__(self, "portal_instance_id", portal_instance_id)
        object.__setattr__(self, "tool_id", tool_id)
        object.__setattr__(self, "subject_hyphae_hash", subject_hyphae_hash)
        object.__setattr__(self, "subject_version_hash", subject_version_hash)
        object.__setattr__(
            self,
            "nimm_state",
            _normalize_object_payload(self.nimm_state or {}, field_name="directive_context_source.nimm_state"),
        )
        object.__setattr__(
            self,
            "aitas_state",
            _normalize_object_payload(self.aitas_state or {}, field_name="directive_context_source.aitas_state"),
        )
        object.__setattr__(
            self,
            "scope",
            _normalize_object_payload(self.scope or {}, field_name="directive_context_source.scope"),
        )
        object.__setattr__(
            self,
            "provenance",
            _normalize_object_payload(self.provenance or {}, field_name="directive_context_source.provenance"),
        )
        object.__setattr__(self, "source_authority", source_authority)

    def to_dict(self) -> dict[str, JsonValue]:
        return {
            "context_id": self.context_id,
            "portal_instance_id": self.portal_instance_id,
            "tool_id": self.tool_id,
            "subject_hyphae_hash": self.subject_hyphae_hash,
            "subject_version_hash": self.subject_version_hash,
            "nimm_state": self.nimm_state or {},
            "aitas_state": self.aitas_state or {},
            "scope": self.scope or {},
            "provenance": self.provenance or {},
            "source_authority": self.source_authority,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> DirectiveContextSource:
        if not isinstance(payload, dict):
            raise ValueError("directive_context_source must be a dict")
        return cls(
            context_id=payload.get("context_id"),
            portal_instance_id=payload.get("portal_instance_id") or payload.get("scope_id"),
            tool_id=payload.get("tool_id") or payload.get("surface_id"),
            subject_hyphae_hash=payload.get("subject_hyphae_hash") or "",
            subject_version_hash=payload.get("subject_version_hash") or "",
            nimm_state=payload.get("nimm_state") or {},
            aitas_state=payload.get("aitas_state") or {},
            scope=payload.get("scope") or {},
            provenance=payload.get("provenance") or {},
            source_authority=payload.get("source_authority") or "authoritative",
        )


@dataclass(frozen=True)
class DirectiveContextResult:
    source: DirectiveContextSource | dict[str, Any] | None
    resolution_status: dict[str, JsonValue]
    warnings: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if self.source is None:
            normalized_source = None
        elif isinstance(self.source, DirectiveContextSource):
            normalized_source = self.source
        elif isinstance(self.source, dict):
            normalized_source = DirectiveContextSource.from_dict(self.source)
        else:
            raise ValueError("directive_context_result.source must be DirectiveContextSource, dict, or None")
        object.__setattr__(self, "source", normalized_source)
        normalized_status = _normalize_json_value(
            self.resolution_status,
            field_name="directive_context_result.resolution_status",
        )
        if not isinstance(normalized_status, dict):
            raise ValueError("directive_context_result.resolution_status must be a dict")
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
    def from_dict(cls, payload: dict[str, Any]) -> DirectiveContextResult:
        if not isinstance(payload, dict):
            raise ValueError("directive_context_result must be a dict")
        warnings = payload.get("warnings") or ()
        if not isinstance(warnings, (list, tuple)):
            raise ValueError("directive_context_result.warnings must be a list")
        return cls(
            source=payload.get("source"),
            resolution_status=payload.get("resolution_status") or {},
            warnings=tuple(str(item) for item in warnings),
        )


@dataclass(frozen=True)
class DirectiveContextEventRecord:
    event_id: str
    context_id: str
    portal_instance_id: str
    tool_id: str
    event_kind: str
    payload: dict[str, JsonValue] | None = None
    provenance: dict[str, JsonValue] | None = None
    subject_hyphae_hash: str = ""
    subject_version_hash: str = ""
    recorded_at_unix_ms: int = 0

    def __post_init__(self) -> None:
        event_id = _as_text(self.event_id)
        context_id = _as_text(self.context_id)
        portal_instance_id = _as_text(self.portal_instance_id)
        tool_id = _as_text(self.tool_id)
        event_kind = _as_text(self.event_kind)
        subject_hyphae_hash = _as_text(self.subject_hyphae_hash)
        subject_version_hash = _as_text(self.subject_version_hash)
        if not event_id:
            raise ValueError("directive_context_event.event_id is required")
        if not context_id:
            raise ValueError("directive_context_event.context_id is required")
        if not portal_instance_id:
            raise ValueError("directive_context_event.portal_instance_id is required")
        if not tool_id:
            raise ValueError("directive_context_event.tool_id is required")
        if not event_kind:
            raise ValueError("directive_context_event.event_kind is required")
        object.__setattr__(self, "event_id", event_id)
        object.__setattr__(self, "context_id", context_id)
        object.__setattr__(self, "portal_instance_id", portal_instance_id)
        object.__setattr__(self, "tool_id", tool_id)
        object.__setattr__(self, "event_kind", event_kind)
        object.__setattr__(self, "subject_hyphae_hash", subject_hyphae_hash)
        object.__setattr__(self, "subject_version_hash", subject_version_hash)
        object.__setattr__(
            self,
            "payload",
            _normalize_object_payload(self.payload or {}, field_name="directive_context_event.payload"),
        )
        object.__setattr__(
            self,
            "provenance",
            _normalize_object_payload(self.provenance or {}, field_name="directive_context_event.provenance"),
        )
        object.__setattr__(self, "recorded_at_unix_ms", int(self.recorded_at_unix_ms or 0))

    def to_dict(self) -> dict[str, JsonValue]:
        return {
            "event_id": self.event_id,
            "context_id": self.context_id,
            "portal_instance_id": self.portal_instance_id,
            "tool_id": self.tool_id,
            "event_kind": self.event_kind,
            "payload": self.payload or {},
            "provenance": self.provenance or {},
            "subject_hyphae_hash": self.subject_hyphae_hash,
            "subject_version_hash": self.subject_version_hash,
            "recorded_at_unix_ms": self.recorded_at_unix_ms,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> DirectiveContextEventRecord:
        if not isinstance(payload, dict):
            raise ValueError("directive_context_event must be a dict")
        return cls(
            event_id=payload.get("event_id"),
            context_id=payload.get("context_id"),
            portal_instance_id=payload.get("portal_instance_id") or payload.get("scope_id"),
            tool_id=payload.get("tool_id") or payload.get("surface_id"),
            event_kind=payload.get("event_kind"),
            payload=payload.get("payload") or {},
            provenance=payload.get("provenance") or {},
            subject_hyphae_hash=payload.get("subject_hyphae_hash") or "",
            subject_version_hash=payload.get("subject_version_hash") or "",
            recorded_at_unix_ms=payload.get("recorded_at_unix_ms") or 0,
        )


@dataclass(frozen=True)
class DirectiveContextEventQuery:
    portal_instance_id: str
    tool_id: str = ""
    context_id: str = ""
    limit: int = 20

    def __post_init__(self) -> None:
        portal_instance_id = _as_text(self.portal_instance_id)
        if not portal_instance_id:
            raise ValueError("directive_context_event_query.portal_instance_id is required")
        object.__setattr__(self, "portal_instance_id", portal_instance_id)
        object.__setattr__(self, "tool_id", _as_text(self.tool_id))
        object.__setattr__(self, "context_id", _as_text(self.context_id))
        object.__setattr__(self, "limit", max(1, int(self.limit or 20)))

    def to_dict(self) -> dict[str, JsonValue]:
        return {
            "portal_instance_id": self.portal_instance_id,
            "tool_id": self.tool_id,
            "context_id": self.context_id,
            "limit": self.limit,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> DirectiveContextEventQuery:
        if not isinstance(payload, dict):
            raise ValueError("directive_context_event_query must be a dict")
        return cls(
            portal_instance_id=payload.get("portal_instance_id") or payload.get("scope_id"),
            tool_id=payload.get("tool_id") or payload.get("surface_id") or "",
            context_id=payload.get("context_id") or "",
            limit=payload.get("limit") or 20,
        )


@runtime_checkable
class DirectiveContextPort(Protocol):
    def read_directive_context(self, request: DirectiveContextRequest) -> DirectiveContextResult:
        """Read normalized directive context keyed to version/hyphae semantic subjects."""


@runtime_checkable
class DirectiveContextEventPort(Protocol):
    def read_directive_context_events(self, request: DirectiveContextEventQuery) -> tuple[DirectiveContextEventRecord, ...]:
        """Read append-only directive-context events for review, replay, and rollback."""
