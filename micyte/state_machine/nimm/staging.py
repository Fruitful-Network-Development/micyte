from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from micyte.state_machine.lens import Lens

from .directives import VERB_MANIPULATE, NimmDirective, NimmTargetAddress
from .envelope import NimmDirectiveEnvelope


def _as_text(value: object) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _target_key(target: NimmTargetAddress) -> str:
    file_key = _as_text(target.file_key)
    datum_address = _as_text(target.datum_address)
    object_ref = _as_text(target.object_ref)
    return "|".join((file_key, datum_address, object_ref))


@dataclass(frozen=True)
class StagedValue:
    target: NimmTargetAddress | dict[str, Any]
    lens_id: str
    display_value: Any
    canonical_value: Any
    validation_issues: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        target = self.target if isinstance(self.target, NimmTargetAddress) else NimmTargetAddress.from_value(self.target)
        object.__setattr__(self, "target", target)
        object.__setattr__(self, "lens_id", _as_text(self.lens_id) or "identity")
        object.__setattr__(self, "validation_issues", tuple(_as_text(item) for item in self.validation_issues if _as_text(item)))

    def to_dict(self) -> dict[str, Any]:
        return {
            "target": self.target.to_dict(),
            "lens_id": self.lens_id,
            "display_value": self.display_value,
            "canonical_value": self.canonical_value,
            "validation_issues": list(self.validation_issues),
        }


@dataclass(frozen=True)
class StagingArea:
    staged_values: tuple[StagedValue | dict[str, Any], ...] = ()

    def __post_init__(self) -> None:
        normalized = tuple(
            item if isinstance(item, StagedValue) else StagedValue(**dict(item))
            for item in self.staged_values
        )
        object.__setattr__(self, "staged_values", normalized)

    def stage_with_lens(
        self,
        *,
        target: NimmTargetAddress | dict[str, Any],
        lens: Lens,
        display_value: Any,
    ) -> StagingArea:
        normalized_target = target if isinstance(target, NimmTargetAddress) else NimmTargetAddress.from_value(target)
        issues = lens.validate_display(display_value)
        canonical_value = lens.encode(display_value)
        replacement = StagedValue(
            target=normalized_target,
            lens_id=_as_text(getattr(lens, "lens_id", "lens")) or "lens",
            display_value=display_value,
            canonical_value=canonical_value,
            validation_issues=issues,
        )
        next_values: dict[str, StagedValue] = {
            _target_key(item.target): item
            for item in self.staged_values
        }
        next_values[_target_key(replacement.target)] = replacement
        return StagingArea(staged_values=tuple(next_values.values()))

    def discard(self) -> StagingArea:
        return StagingArea(staged_values=())

    def to_dict(self) -> dict[str, Any]:
        return {"staged_values": [item.to_dict() for item in self.staged_values]}

    def compile_manipulation_envelope(
        self,
        *,
        target_authority: str,
        document_id: str = "",
        aitas: dict[str, Any] | None = None,
    ) -> NimmDirectiveEnvelope:
        if not self.staged_values:
            raise ValueError("staging area has no values to compile")
        payload_values = [
            {
                "target": item.target.to_dict(),
                "lens_id": item.lens_id,
                "canonical_value": item.canonical_value,
                "validation_issues": list(item.validation_issues),
            }
            for item in self.staged_values
        ]
        directive = NimmDirective(
            verb=VERB_MANIPULATE,
            target_authority=target_authority,
            document_id=document_id,
            targets=tuple(item.target for item in self.staged_values),
            payload={"staged_values": payload_values},
        )
        return NimmDirectiveEnvelope(directive=directive, aitas=dict(aitas or {}))
