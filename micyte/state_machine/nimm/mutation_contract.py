from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any

from .envelope import NimmDirectiveEnvelope

DEFAULT_MUTATION_ENDPOINTS = {
    "stage": "/portal/api/v2/mutations/stage",
    "validate": "/portal/api/v2/mutations/validate",
    "preview": "/portal/api/v2/mutations/preview",
    "apply": "/portal/api/v2/mutations/apply",
    "discard": "/portal/api/v2/mutations/discard",
}

DEFAULT_MUTATION_ACTIONS = ("stage", "validate", "preview", "apply", "discard")

CTS_GIS_MUTATION_ACTION_ALIASES = {
    "stage_insert_yaml": "stage",
    "validate_stage": "validate",
    "preview_apply": "preview",
    "apply_stage": "apply",
    "discard_stage": "discard",
}

CTS_GIS_CANONICAL_ACTIONS = {
    "stage": "stage_insert_yaml",
    "validate": "validate_stage",
    "preview": "preview_apply",
    "apply": "apply_stage",
    "discard": "discard_stage",
}

AWS_CSM_ACTION_LIFECYCLE = {
    "create_domain": "apply",
    "refresh_domain_status": "validate",
    "ensure_domain_identity": "apply",
    "sync_domain_dns": "apply",
    "ensure_domain_receipt_rule": "apply",
    "create_profile": "apply",
    "update_profile": "apply",
    "delete_profile": "apply",
    "stage_smtp_credentials": "stage",
    "send_handoff_email": "apply",
    "reveal_smtp_password": "preview",
    "refresh_provider_status": "validate",
    "capture_verification": "apply",
    "confirm_verified": "apply",
    "confirm_verified_attested": "apply",
}


def _as_text(value: object) -> str:
    if value is None:
        return ""
    return str(value).strip()


def mutation_action_endpoint(action: object) -> str:
    action_name = normalize_mutation_lifecycle_action(action)
    if action_name not in DEFAULT_MUTATION_ENDPOINTS:
        allowed = ", ".join(sorted(DEFAULT_MUTATION_ENDPOINTS))
        raise ValueError(f"mutation action must be one of: {allowed}")
    return DEFAULT_MUTATION_ENDPOINTS[action_name]


def normalize_mutation_lifecycle_action(action: object) -> str:
    action_name = _as_text(action).lower()
    return CTS_GIS_MUTATION_ACTION_ALIASES.get(action_name, action_name)


def cts_gis_runtime_action_kind(action: object) -> str:
    action_name = _as_text(action).lower()
    if action_name in CTS_GIS_MUTATION_ACTION_ALIASES:
        return action_name
    return CTS_GIS_CANONICAL_ACTIONS.get(action_name, action_name)


def aws_lifecycle_action(action_kind: object) -> str:
    return AWS_CSM_ACTION_LIFECYCLE.get(_as_text(action_kind).lower(), "apply")


@dataclass(frozen=True)
class MutationContractResult:
    status: str
    message: str
    envelope: NimmDirectiveEnvelope | None = None
    details: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "status": _as_text(self.status) or "accepted",
            "message": _as_text(self.message),
        }
        if self.envelope is not None:
            payload["envelope"] = self.envelope.to_dict()
        if isinstance(self.details, dict) and self.details:
            payload["details"] = dict(self.details)
        return payload


class MutationContractRuntimeHandler(ABC):
    """Runtime handler seam for stage/validate/preview/apply/discard."""

    @abstractmethod
    def stage(self, envelope: NimmDirectiveEnvelope) -> MutationContractResult:
        raise NotImplementedError

    @abstractmethod
    def validate(self, envelope: NimmDirectiveEnvelope) -> MutationContractResult:
        raise NotImplementedError

    @abstractmethod
    def preview(self, envelope: NimmDirectiveEnvelope) -> MutationContractResult:
        raise NotImplementedError

    @abstractmethod
    def apply(self, envelope: NimmDirectiveEnvelope) -> MutationContractResult:
        raise NotImplementedError

    @abstractmethod
    def discard(self, envelope: NimmDirectiveEnvelope) -> MutationContractResult:
        raise NotImplementedError
