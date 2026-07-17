from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

NIMM_DIRECTIVE_SCHEMA_V1 = "mycite.v2.nimm.directive.v1"

VERB_NAVIGATE = "navigate"
VERB_INVESTIGATE = "investigate"
VERB_MEDIATE = "mediate"
VERB_MANIPULATE = "manipulate"

VERB_ALIAS_NAVIGATE = "nav"
VERB_ALIAS_INVESTIGATE = "inv"
VERB_ALIAS_MEDIATE = "med"
VERB_ALIAS_MANIPULATE = "man"

SUPPORTED_NIMM_VERBS = (
    VERB_NAVIGATE,
    VERB_INVESTIGATE,
    VERB_MEDIATE,
    VERB_MANIPULATE,
)

MINIMAL_NIMM_VERBS = (
    VERB_ALIAS_NAVIGATE,
    VERB_ALIAS_INVESTIGATE,
    VERB_ALIAS_MEDIATE,
    VERB_ALIAS_MANIPULATE,
)

NIMM_VERB_ALIASES = {
    VERB_ALIAS_NAVIGATE: VERB_NAVIGATE,
    VERB_ALIAS_INVESTIGATE: VERB_INVESTIGATE,
    VERB_ALIAS_MEDIATE: VERB_MEDIATE,
    VERB_ALIAS_MANIPULATE: VERB_MANIPULATE,
}

SUPPORTED_NIMM_VERB_TOKENS = (*SUPPORTED_NIMM_VERBS, *MINIMAL_NIMM_VERBS)

DEFAULT_SHELL_VERB = VERB_NAVIGATE
SUPPORTED_SHELL_VERBS = SUPPORTED_NIMM_VERB_TOKENS

NIMM_DIRECTIVE_GRAMMAR_V1 = {
    "schema": NIMM_DIRECTIVE_SCHEMA_V1,
    "required": ("verb", "targets"),
    "verbs": SUPPORTED_NIMM_VERB_TOKENS,
    "canonical_verbs": SUPPORTED_NIMM_VERBS,
    "minimal_aliases": NIMM_VERB_ALIASES,
    "fields": {
        "verb": "One of navigate/investigate/mediate/manipulate or nav/inv/med/man.",
        "target_authority": "Runtime authority that interprets the directive.",
        "document_id": "Optional document/file authority when target_authority is implicit.",
        "aitas_ref": "Named AITAS context reference when envelope context is external.",
        "targets": "Non-empty list of file_key, datum_address, or object_ref target addresses.",
        "payload": "Runtime-owned directive payload.",
    },
}


def _as_text(value: object) -> str:
    if value is None:
        return ""
    return str(value).strip()


def normalize_shell_verb(value: object, *, field_name: str = "shell_verb") -> str:
    token = _as_text(value).lower()
    if token not in SUPPORTED_SHELL_VERBS:
        supported = ", ".join(SUPPORTED_SHELL_VERBS)
        raise ValueError(f"{field_name} must be one of: {supported}")
    return NIMM_VERB_ALIASES.get(token, token)


def normalize_nimm_verb(value: object, *, field_name: str = "nimm.verb") -> str:
    token = _as_text(value).lower()
    if token not in SUPPORTED_NIMM_VERB_TOKENS:
        supported = ", ".join(SUPPORTED_NIMM_VERB_TOKENS)
        raise ValueError(f"{field_name} must be one of: {supported}")
    return NIMM_VERB_ALIASES.get(token, token)


NIMM_DIRECTIVE_TEXT_FORMAT = "verb;target_authority:datum_address  (e.g. med;cts_gis:1-1-2)"


def parse_directive_text(text: str) -> dict[str, str]:
    """Validate and parse directive terminal input.

    Returns {"verb": canonical_verb, "target_text": rest, "raw": original}.
    Raises ValueError on empty input, missing ";", or unrecognized verb.
    """
    text = _as_text(text)
    if not text:
        raise ValueError("Directive text cannot be empty.")
    if ";" not in text:
        raise ValueError(
            f"Invalid directive format: {text!r}. "
            f"Expected {NIMM_DIRECTIVE_TEXT_FORMAT}."
        )
    verb_part, _, target_part = text.partition(";")
    verb = normalize_nimm_verb(verb_part)
    return {"verb": verb, "target_text": target_part.strip(), "raw": text}


@dataclass(frozen=True)
class NimmTargetAddress:
    file_key: str = ""
    datum_address: str = ""
    object_ref: str = ""

    def __post_init__(self) -> None:
        file_key = _as_text(self.file_key)
        datum_address = _as_text(self.datum_address)
        object_ref = _as_text(self.object_ref)
        if not (file_key or datum_address or object_ref):
            raise ValueError("nimm.target requires at least one of file_key, datum_address, object_ref")
        object.__setattr__(self, "file_key", file_key)
        object.__setattr__(self, "datum_address", datum_address)
        object.__setattr__(self, "object_ref", object_ref)

    def to_dict(self) -> dict[str, str]:
        payload: dict[str, str] = {}
        if self.file_key:
            payload["file_key"] = self.file_key
        if self.datum_address:
            payload["datum_address"] = self.datum_address
        if self.object_ref:
            payload["object_ref"] = self.object_ref
        return payload

    @classmethod
    def from_value(cls, payload: dict[str, Any] | NimmTargetAddress) -> NimmTargetAddress:
        if isinstance(payload, cls):
            return payload
        if not isinstance(payload, dict):
            raise ValueError("nimm.targets entries must be dicts")
        return cls(
            file_key=payload.get("file_key") or "",
            datum_address=payload.get("datum_address") or "",
            object_ref=payload.get("object_ref") or "",
        )


@dataclass(frozen=True)
class NimmDirective:
    verb: str
    targets: tuple[NimmTargetAddress | dict[str, Any], ...]
    target_authority: str = ""
    document_id: str = ""
    aitas_ref: str = "default"
    payload: dict[str, Any] = field(default_factory=dict)
    schema: str = field(default=NIMM_DIRECTIVE_SCHEMA_V1, init=False)

    def __post_init__(self) -> None:
        if self.schema != NIMM_DIRECTIVE_SCHEMA_V1:
            raise ValueError(f"nimm.schema must be {NIMM_DIRECTIVE_SCHEMA_V1}")
        verb = normalize_nimm_verb(self.verb)
        target_authority = _as_text(self.target_authority)
        document_id = _as_text(self.document_id)
        if not (target_authority or document_id):
            raise ValueError("nimm.target_authority or nimm.document_id is required")
        normalized_targets = tuple(NimmTargetAddress.from_value(item) for item in self.targets)
        if not normalized_targets:
            raise ValueError("nimm.targets must contain at least one target")
        payload = dict(self.payload or {})
        object.__setattr__(self, "verb", verb)
        object.__setattr__(self, "target_authority", target_authority)
        object.__setattr__(self, "document_id", document_id)
        object.__setattr__(self, "aitas_ref", _as_text(self.aitas_ref) or "default")
        object.__setattr__(self, "targets", normalized_targets)
        object.__setattr__(self, "payload", payload)

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "schema": self.schema,
            "verb": self.verb,
            "target_authority": self.target_authority,
            "document_id": self.document_id,
            "aitas_ref": self.aitas_ref,
            "targets": [item.to_dict() for item in self.targets],
        }
        if self.payload:
            payload["payload"] = dict(self.payload)
        return payload

    @classmethod
    def from_dict(cls, payload: dict[str, Any] | NimmDirective) -> NimmDirective:
        if isinstance(payload, cls):
            return payload
        if not isinstance(payload, dict):
            raise ValueError("nimm directive must be a dict")
        schema = _as_text(payload.get("schema"))
        if schema and schema != NIMM_DIRECTIVE_SCHEMA_V1:
            raise ValueError(f"nimm.schema must be {NIMM_DIRECTIVE_SCHEMA_V1}")
        return cls(
            verb=payload.get("verb") or "",
            target_authority=payload.get("target_authority") or "",
            document_id=payload.get("document_id") or "",
            aitas_ref=payload.get("aitas_ref") or "default",
            targets=tuple(payload.get("targets") or ()),
            payload=dict(payload.get("payload") or {}),
        )


def validate_nimm_directive_payload(payload: dict[str, Any] | NimmDirective) -> NimmDirective:
    return NimmDirective.from_dict(payload)


def handle_nimm_navigate(directive: NimmDirective | dict[str, Any]) -> NimmDirective:
    normalized = validate_nimm_directive_payload(directive)
    if normalized.verb != VERB_NAVIGATE:
        raise ValueError("navigate handler requires verb=navigate")
    return normalized


def handle_nimm_investigate(directive: NimmDirective | dict[str, Any]) -> NimmDirective:
    normalized = validate_nimm_directive_payload(directive)
    if normalized.verb != VERB_INVESTIGATE:
        raise ValueError("investigate handler requires verb=investigate")
    raise NotImplementedError("NIMM investigate semantics are deferred to a later phase.")


def handle_nimm_mediate(directive: NimmDirective | dict[str, Any]) -> NimmDirective:
    normalized = validate_nimm_directive_payload(directive)
    if normalized.verb != VERB_MEDIATE:
        raise ValueError("mediate handler requires verb=mediate")
    # Validation passes; resolution is delegated to the tool-specific runtime handler.
    # The caller uses the normalized directive's target_authority and payload to dispatch
    # to the appropriate mediation builder (e.g. nimm.mediate_handlers for cts_gis).
    return normalized


def handle_nimm_manipulate(directive: NimmDirective | dict[str, Any]) -> NimmDirective:
    normalized = validate_nimm_directive_payload(directive)
    if normalized.verb != VERB_MANIPULATE:
        raise ValueError("manipulate handler requires verb=manipulate")
    # Validation passes; resolution is delegated to the tool-specific runtime handler.
    # The caller uses the normalized directive's target_authority and payload to dispatch
    # to the appropriate mutation handler (e.g. datum_workbench for rename/delete).
    return normalized
