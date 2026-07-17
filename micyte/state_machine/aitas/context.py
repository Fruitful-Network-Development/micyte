from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from micyte.core.datum_refs import normalize_datum_ref, parse_datum_ref


def _as_text(value: object) -> str:
    if value is None:
        return ""
    return str(value).strip()


def normalize_attention(value: object, *, field_name: str = "attention") -> str:
    parsed = parse_datum_ref(value, field_name=field_name)
    if not parsed.qualified:
        raise ValueError(f"{field_name} must be a qualified datum_ref")
    return normalize_datum_ref(parsed.raw, write_format="dot", field_name=field_name)


@dataclass(frozen=True)
class AitasContext:
    attention: str = ""
    intention: str = ""
    time: str = ""
    archetype: str = ""
    scope: str = ""

    def __post_init__(self) -> None:
        normalized_attention = ""
        if self.attention:
            normalized_attention = normalize_attention(self.attention, field_name="aitas.attention")
        object.__setattr__(self, "attention", normalized_attention)
        object.__setattr__(self, "intention", _as_text(self.intention).lower())
        object.__setattr__(self, "time", _as_text(self.time))
        object.__setattr__(self, "archetype", _as_text(self.archetype))
        object.__setattr__(self, "scope", _as_text(self.scope))

    def to_dict(self) -> dict[str, str]:
        return {
            "attention": self.attention,
            "intention": self.intention,
            "time": self.time,
            "archetype": self.archetype,
            "scope": self.scope,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, object] | AitasContext | None) -> AitasContext:
        if isinstance(payload, cls):
            return payload
        data = payload if isinstance(payload, dict) else {}
        return cls(
            attention=data.get("attention") or "",
            intention=data.get("intention") or "",
            time=data.get("time") or data.get("time_directive") or "",
            archetype=data.get("archetype") or data.get("archetype_family_id") or "",
            scope=data.get("scope") or data.get("scope_id") or "",
        )


def merge_aitas_context(
    *,
    defaults: AitasContext | dict[str, Any] | None = None,
    overrides: AitasContext | dict[str, Any] | None = None,
) -> AitasContext:
    base = AitasContext.from_dict(defaults)
    override = AitasContext.from_dict(overrides)
    return AitasContext(
        attention=override.attention or base.attention,
        intention=override.intention or base.intention,
        time=override.time or base.time,
        archetype=override.archetype or base.archetype,
        scope=override.scope or base.scope,
    )
