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


def _normalize_email(value: object, *, field_name: str) -> str:
    token = _as_text(value).lower()
    if not token or "@" not in token or token.startswith("@") or token.endswith("@"):
        raise ValueError(f"{field_name} must be an email-like value")
    return token


@dataclass(frozen=True)
class AwsNarrowWriteRequest:
    tenant_scope_id: str
    profile_id: str
    selected_verified_sender: str

    def __post_init__(self) -> None:
        tenant_scope_id = _as_text(self.tenant_scope_id)
        profile_id = _as_text(self.profile_id)
        if not tenant_scope_id:
            raise ValueError("aws_narrow_write_request.tenant_scope_id is required")
        if not profile_id:
            raise ValueError("aws_narrow_write_request.profile_id is required")
        object.__setattr__(self, "tenant_scope_id", tenant_scope_id)
        object.__setattr__(self, "profile_id", profile_id)
        object.__setattr__(
            self,
            "selected_verified_sender",
            _normalize_email(
                self.selected_verified_sender,
                field_name="aws_narrow_write_request.selected_verified_sender",
            ),
        )

    def to_dict(self) -> dict[str, str]:
        return {
            "tenant_scope_id": self.tenant_scope_id,
            "profile_id": self.profile_id,
            "selected_verified_sender": self.selected_verified_sender,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> AwsNarrowWriteRequest:
        if not isinstance(payload, dict):
            raise ValueError("aws_narrow_write_request must be a dict")
        return cls(
            tenant_scope_id=payload.get("tenant_scope_id"),
            profile_id=payload.get("profile_id"),
            selected_verified_sender=payload.get("selected_verified_sender"),
        )


@dataclass(frozen=True)
class AwsNarrowWriteSource:
    payload: dict[str, JsonValue]

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "payload",
            _normalize_payload(self.payload, field_name="aws_narrow_write_source.payload"),
        )

    def to_dict(self) -> dict[str, JsonValue]:
        return {
            "payload": dict(self.payload),
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> AwsNarrowWriteSource:
        if not isinstance(payload, dict):
            raise ValueError("aws_narrow_write_source must be a dict")
        return cls(payload=payload.get("payload"))


@dataclass(frozen=True)
class AwsNarrowWriteResult:
    source: AwsNarrowWriteSource

    def __post_init__(self) -> None:
        if isinstance(self.source, AwsNarrowWriteSource):
            return
        if isinstance(self.source, dict):
            object.__setattr__(self, "source", AwsNarrowWriteSource.from_dict(self.source))
            return
        raise ValueError("aws_narrow_write_result.source must be AwsNarrowWriteSource or dict")

    def to_dict(self) -> dict[str, JsonValue]:
        return {
            "source": self.source.to_dict(),
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> AwsNarrowWriteResult:
        if not isinstance(payload, dict):
            raise ValueError("aws_narrow_write_result must be a dict")
        return cls(source=payload.get("source"))


@runtime_checkable
class AwsNarrowWritePort(Protocol):
    def apply_aws_narrow_write(self, request: AwsNarrowWriteRequest) -> AwsNarrowWriteResult:
        """Apply one bounded AWS operational write and return the updated source payload."""
