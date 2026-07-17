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


def _normalize_payload(value: object, *, field_name: str) -> dict[str, JsonValue]:
    if not isinstance(value, dict):
        raise ValueError(f"{field_name} must be a dict")
    normalized = _normalize_json_value(value, field_name=field_name)
    if not isinstance(normalized, dict) or not normalized:
        raise ValueError(f"{field_name} must be a non-empty dict")
    return normalized


@dataclass(frozen=True)
class AwsReadOnlyStatusRequest:
    tenant_scope_id: str

    def __post_init__(self) -> None:
        token = _as_text(self.tenant_scope_id)
        if not token:
            raise ValueError("aws_read_only_status_request.tenant_scope_id is required")
        object.__setattr__(self, "tenant_scope_id", token)

    def to_dict(self) -> dict[str, str]:
        return {
            "tenant_scope_id": self.tenant_scope_id,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> AwsReadOnlyStatusRequest:
        if not isinstance(payload, dict):
            raise ValueError("aws_read_only_status_request must be a dict")
        return cls(tenant_scope_id=payload.get("tenant_scope_id"))


@dataclass(frozen=True)
class AwsReadOnlyStatusSource:
    payload: dict[str, JsonValue]

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "payload",
            _normalize_payload(self.payload, field_name="aws_read_only_status_source.payload"),
        )

    def to_dict(self) -> dict[str, JsonValue]:
        return {
            "payload": dict(self.payload),
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> AwsReadOnlyStatusSource:
        if not isinstance(payload, dict):
            raise ValueError("aws_read_only_status_source must be a dict")
        return cls(payload=payload.get("payload"))


@dataclass(frozen=True)
class AwsReadOnlyStatusResult:
    source: AwsReadOnlyStatusSource | None

    def __post_init__(self) -> None:
        if self.source is None:
            return
        if isinstance(self.source, AwsReadOnlyStatusSource):
            return
        if isinstance(self.source, dict):
            object.__setattr__(self, "source", AwsReadOnlyStatusSource.from_dict(self.source))
            return
        raise ValueError("aws_read_only_status_result.source must be AwsReadOnlyStatusSource, dict, or None")

    @property
    def found(self) -> bool:
        return self.source is not None

    def to_dict(self) -> dict[str, JsonValue]:
        return {
            "found": self.found,
            "source": None if self.source is None else self.source.to_dict(),
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> AwsReadOnlyStatusResult:
        if not isinstance(payload, dict):
            raise ValueError("aws_read_only_status_result must be a dict")
        return cls(source=payload.get("source"))


@runtime_checkable
class AwsReadOnlyStatusPort(Protocol):
    def read_aws_read_only_status(self, request: AwsReadOnlyStatusRequest) -> AwsReadOnlyStatusResult:
        """Read one tenant-scoped AWS operational status snapshot without any writes."""
