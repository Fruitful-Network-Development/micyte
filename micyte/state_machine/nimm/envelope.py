from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from micyte.state_machine.aitas import AitasContext, merge_aitas_context

from .directives import NimmDirective

NIMM_ENVELOPE_SCHEMA_V1 = "mycite.v2.nimm.envelope.v1"


def _as_text(value: object) -> str:
    if value is None:
        return ""
    return str(value).strip()


@dataclass(frozen=True)
class NimmDirectiveEnvelope:
    directive: NimmDirective | dict[str, Any]
    aitas: AitasContext | dict[str, Any] = field(default_factory=AitasContext)
    schema: str = field(default=NIMM_ENVELOPE_SCHEMA_V1, init=False)

    def __post_init__(self) -> None:
        directive = self.directive if isinstance(self.directive, NimmDirective) else NimmDirective.from_dict(self.directive)
        aitas = self.aitas if isinstance(self.aitas, AitasContext) else AitasContext.from_dict(self.aitas)
        object.__setattr__(self, "directive", directive)
        object.__setattr__(self, "aitas", aitas)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "directive": self.directive.to_dict(),
            "aitas": self.aitas.to_dict(),
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any] | NimmDirectiveEnvelope) -> NimmDirectiveEnvelope:
        if isinstance(payload, cls):
            return payload
        if not isinstance(payload, dict):
            raise ValueError("nimm envelope must be a dict")
        schema = _as_text(payload.get("schema"))
        if schema and schema != NIMM_ENVELOPE_SCHEMA_V1:
            raise ValueError(f"nimm envelope schema must be {NIMM_ENVELOPE_SCHEMA_V1}")
        return cls(
            directive=payload.get("directive") or {},
            aitas=payload.get("aitas") or {},
        )

    @classmethod
    def with_merged_aitas(
        cls,
        *,
        directive: NimmDirective | dict[str, Any],
        defaults: AitasContext | dict[str, Any] | None = None,
        overrides: AitasContext | dict[str, Any] | None = None,
    ) -> NimmDirectiveEnvelope:
        return cls(
            directive=directive,
            aitas=merge_aitas_context(defaults=defaults, overrides=overrides),
        )
