"""Portal shell dataclasses and their normalization helpers."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from micyte.core.scalars import as_text
from micyte.state_machine.nimm import (
    NimmDirectiveEnvelope,
    normalize_nimm_verb,
)

from .shell_schemas import (
    FOCUS_LEVEL_INDEX,
    FOCUS_LEVEL_SANDBOX,
    PORTAL_SCOPE_DEFAULT_ID,
    PORTAL_SHELL_REQUEST_SCHEMA,
    PORTAL_SHELL_STATE_SCHEMA,
    PORTAL_SHELL_TRANSITIONS,
    PORTAL_SURFACE_CATALOG_ENTRY_SCHEMA,
    ROOT_SURFACE_IDS,
    SYSTEM_ROOT_SURFACE_ID,
    VERB_NAVIGATE,
)


def _normalize_slug(value: object) -> str:
    return as_text(value).lower().replace("-", "_").replace(" ", "_")


def _require_schema(payload: dict[str, Any], *, expected: str, field_name: str) -> None:
    schema = as_text(payload.get("schema"))
    if schema != expected:
        raise ValueError(f"{field_name} must be {expected}")


def _normalize_surface_query(value: object, *, field_name: str) -> dict[str, str]:
    if value is None:
        return {}
    if not isinstance(value, Mapping):
        raise ValueError(f"{field_name} must be a mapping or null")
    out: dict[str, str] = {}
    for raw_key, raw_value in value.items():
        key = as_text(raw_key)
        if not key:
            raise ValueError(f"{field_name} keys must be non-empty")
        token = as_text(raw_value)
        if token:
            out[key] = token
    return out


def _normalize_capabilities(value: object, *, field_name: str) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, str) and not as_text(value):
        return ()
    if not isinstance(value, (list, tuple)):
        raise ValueError(f"{field_name} must be a list, tuple, or null")
    normalized: list[str] = []
    seen: set[str] = set()
    for raw_item in value:
        item = _normalize_slug(raw_item)
        if not item or item in seen:
            continue
        normalized.append(item)
        seen.add(item)
    return tuple(normalized)


@dataclass(frozen=True)
class PortalScope:
    scope_id: str = PORTAL_SCOPE_DEFAULT_ID
    capabilities: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        scope_id = as_text(self.scope_id) or PORTAL_SCOPE_DEFAULT_ID
        object.__setattr__(self, "scope_id", scope_id)
        object.__setattr__(
            self,
            "capabilities",
            _normalize_capabilities(self.capabilities, field_name="portal_scope.capabilities"),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "scope_id": self.scope_id,
            "capabilities": list(self.capabilities),
        }

    @classmethod
    def from_value(cls, payload: dict[str, Any] | str | None) -> PortalScope:
        if payload is None:
            return cls()
        if isinstance(payload, str):
            return cls(scope_id=payload)
        if isinstance(payload, dict):
            return cls(
                scope_id=payload.get("scope_id") or payload.get("portal_instance_id") or PORTAL_SCOPE_DEFAULT_ID,
                capabilities=payload.get("capabilities"),
            )
        raise ValueError("portal_scope must be a dict, string, or null")


@dataclass(frozen=True)
class PortalShellChrome:
    control_panel_collapsed: bool = False

    def __post_init__(self) -> None:
        if not isinstance(self.control_panel_collapsed, bool):
            raise ValueError("shell_chrome.control_panel_collapsed must be a bool")

    def to_dict(self) -> dict[str, Any]:
        return {
            "control_panel_collapsed": self.control_panel_collapsed,
        }

    @classmethod
    def from_value(cls, payload: dict[str, Any] | None) -> PortalShellChrome:
        if payload is None:
            return cls()
        if not isinstance(payload, dict):
            raise ValueError("shell_chrome must be a dict or null")
        return cls(
            control_panel_collapsed=payload.get("control_panel_collapsed") is True,
        )


@dataclass(frozen=True)
class PortalFocusSegment:
    level: str
    id: str

    def __post_init__(self) -> None:
        level = _normalize_slug(self.level)
        token = as_text(self.id)
        if level not in FOCUS_LEVEL_INDEX:
            raise ValueError("focus_segment.level is invalid")
        if not token:
            raise ValueError("focus_segment.id is required")
        object.__setattr__(self, "level", level)
        object.__setattr__(self, "id", token)

    def to_dict(self) -> dict[str, str]:
        return {"level": self.level, "id": self.id}

    @classmethod
    def from_value(cls, payload: dict[str, Any] | PortalFocusSegment) -> PortalFocusSegment:
        if isinstance(payload, cls):
            return payload
        if not isinstance(payload, dict):
            raise ValueError("focus_segment must be a dict")
        return cls(level=payload.get("level"), id=payload.get("id"))


def _normalize_focus_path(
    value: object,
    *,
    scope_id: str,
) -> tuple[PortalFocusSegment, ...]:
    if value is None:
        raw_segments: list[Any] = []
    elif isinstance(value, (list, tuple)):
        raw_segments = list(value)
    else:
        raise ValueError("portal_shell_state.focus_path must be a list, tuple, or null")

    segments: list[PortalFocusSegment] = []
    seen_levels: set[str] = set()
    for raw_segment in raw_segments:
        segment = PortalFocusSegment.from_value(raw_segment)
        if segment.level in seen_levels:
            continue
        segments.append(segment)
        seen_levels.add(segment.level)

    if not segments or segments[0].level != FOCUS_LEVEL_SANDBOX:
        segments.insert(0, PortalFocusSegment(level=FOCUS_LEVEL_SANDBOX, id=scope_id))
    else:
        segments[0] = PortalFocusSegment(level=FOCUS_LEVEL_SANDBOX, id=segments[0].id or scope_id)

    normalized: list[PortalFocusSegment] = []
    expected_index = 0
    for segment in sorted(segments, key=lambda item: FOCUS_LEVEL_INDEX[item.level]):
        if FOCUS_LEVEL_INDEX[segment.level] != expected_index:
            break
        normalized.append(segment)
        expected_index += 1
    return tuple(normalized)


def _subject_from_segment(segment: PortalFocusSegment | None) -> dict[str, str] | None:
    if segment is None:
        return None
    return segment.to_dict()


def _normalize_subject(value: object) -> dict[str, str] | None:
    if value is None:
        return None
    if isinstance(value, PortalFocusSegment):
        return value.to_dict()
    if isinstance(value, dict):
        segment = PortalFocusSegment.from_value(value)
        return segment.to_dict()
    raise ValueError("focus_subject and mediation_subject must be dicts or null")


@dataclass(frozen=True)
class PortalShellState:
    active_surface_id: str
    focus_path: tuple[PortalFocusSegment | dict[str, Any], ...]
    focus_subject: dict[str, str] | None = None
    mediation_subject: dict[str, str] | None = None
    verb: str = VERB_NAVIGATE
    chrome: PortalShellChrome = field(default_factory=PortalShellChrome)
    schema: str = field(default=PORTAL_SHELL_STATE_SCHEMA, init=False)

    def __post_init__(self) -> None:
        active_surface_id = as_text(self.active_surface_id) or SYSTEM_ROOT_SURFACE_ID
        verb = normalize_nimm_verb(self.verb, field_name="portal_shell_state.verb")
        chrome = self.chrome if isinstance(self.chrome, PortalShellChrome) else PortalShellChrome.from_value(self.chrome)
        scope_id = PORTAL_SCOPE_DEFAULT_ID
        if self.focus_path:
            first_segment = self.focus_path[0]
            if isinstance(first_segment, PortalFocusSegment):
                scope_id = first_segment.id or PORTAL_SCOPE_DEFAULT_ID
            elif isinstance(first_segment, dict):
                scope_id = as_text(first_segment.get("id")) or PORTAL_SCOPE_DEFAULT_ID
        focus_path = _normalize_focus_path(self.focus_path, scope_id=scope_id)
        if not focus_path:
            raise ValueError("portal_shell_state.focus_path must include sandbox focus")
        focus_subject = _normalize_subject(self.focus_subject) or _subject_from_segment(focus_path[-1])
        mediation_subject = _normalize_subject(self.mediation_subject)
        object.__setattr__(self, "active_surface_id", active_surface_id)
        object.__setattr__(self, "focus_path", focus_path)
        object.__setattr__(self, "focus_subject", focus_subject)
        object.__setattr__(self, "mediation_subject", mediation_subject)
        object.__setattr__(self, "verb", verb)
        object.__setattr__(self, "chrome", chrome)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "active_surface_id": self.active_surface_id,
            "focus_path": [segment.to_dict() for segment in self.focus_path],
            "focus_subject": dict(self.focus_subject) if isinstance(self.focus_subject, dict) else None,
            "mediation_subject": dict(self.mediation_subject) if isinstance(self.mediation_subject, dict) else None,
            "verb": self.verb,
            "chrome": self.chrome.to_dict(),
        }

    @classmethod
    def from_value(
        cls,
        payload: dict[str, Any] | PortalShellState | None,
        *,
        portal_scope: PortalScope | None = None,
        fallback_surface_id: str = SYSTEM_ROOT_SURFACE_ID,
    ) -> PortalShellState:
        if isinstance(payload, cls):
            return payload
        if payload is None:
            # Deferred import to avoid circular dependency with shell.py
            from .shell import initial_portal_shell_state
            return initial_portal_shell_state(surface_id=fallback_surface_id, portal_scope=portal_scope or PortalScope())
        if not isinstance(payload, dict):
            raise ValueError("portal_shell_state must be a dict or null")
        if as_text(payload.get("schema")) not in {"", PORTAL_SHELL_STATE_SCHEMA}:
            raise ValueError(f"portal_shell_state.schema must be {PORTAL_SHELL_STATE_SCHEMA}")
        scope_id = (portal_scope or PortalScope()).scope_id
        focus_path = _normalize_focus_path(payload.get("focus_path"), scope_id=scope_id)
        return cls(
            active_surface_id=payload.get("active_surface_id") or fallback_surface_id,
            focus_path=focus_path,
            focus_subject=_normalize_subject(payload.get("focus_subject")) or _subject_from_segment(focus_path[-1]),
            mediation_subject=_normalize_subject(payload.get("mediation_subject")),
            verb=as_text(payload.get("verb")) or VERB_NAVIGATE,
            chrome=PortalShellChrome.from_value(payload.get("chrome")),
        )


@dataclass(frozen=True)
class PortalShellTransition:
    kind: str
    surface_id: str = ""
    file_key: str = ""
    datum_id: str = ""
    object_id: str = ""
    verb: str = ""

    def __post_init__(self) -> None:
        kind = _normalize_slug(self.kind)
        verb = _normalize_slug(self.verb)
        if kind not in PORTAL_SHELL_TRANSITIONS:
            raise ValueError("portal_shell_transition.kind is invalid")
        if verb:
            verb = normalize_nimm_verb(verb, field_name="portal_shell_transition.verb")
        object.__setattr__(self, "kind", kind)
        object.__setattr__(self, "surface_id", as_text(self.surface_id))
        object.__setattr__(self, "file_key", as_text(self.file_key))
        object.__setattr__(self, "datum_id", as_text(self.datum_id))
        object.__setattr__(self, "object_id", as_text(self.object_id))
        object.__setattr__(self, "verb", verb)

    def to_dict(self) -> dict[str, Any]:
        payload = {"kind": self.kind}
        if self.surface_id:
            payload["surface_id"] = self.surface_id
        if self.file_key:
            payload["file_key"] = self.file_key
        if self.datum_id:
            payload["datum_id"] = self.datum_id
        if self.object_id:
            payload["object_id"] = self.object_id
        if self.verb:
            payload["verb"] = self.verb
        return payload

    @classmethod
    def from_value(cls, payload: dict[str, Any] | PortalShellTransition | None) -> PortalShellTransition | None:
        if payload is None:
            return None
        if isinstance(payload, cls):
            return payload
        if not isinstance(payload, dict):
            raise ValueError("portal_shell_transition must be a dict or null")
        return cls(
            kind=payload.get("kind"),
            surface_id=payload.get("surface_id") or payload.get("requested_surface_id") or "",
            file_key=payload.get("file_key") or "",
            datum_id=payload.get("datum_id") or "",
            object_id=payload.get("object_id") or "",
            verb=payload.get("verb") or "",
        )


@dataclass(frozen=True)
class PortalShellRequest:
    requested_surface_id: str = SYSTEM_ROOT_SURFACE_ID
    portal_scope: PortalScope = field(default_factory=PortalScope)
    shell_state: PortalShellState | None = None
    transition: PortalShellTransition | None = None
    nimm_envelope: NimmDirectiveEnvelope | None = None
    surface_query: dict[str, str] = field(default_factory=dict)
    schema: str = field(default=PORTAL_SHELL_REQUEST_SCHEMA, init=False)

    def __post_init__(self) -> None:
        requested_surface_id = as_text(self.requested_surface_id) or SYSTEM_ROOT_SURFACE_ID
        portal_scope = self.portal_scope if isinstance(self.portal_scope, PortalScope) else PortalScope.from_value(self.portal_scope)
        shell_state = (
            self.shell_state
            if isinstance(self.shell_state, PortalShellState) or self.shell_state is None
            else PortalShellState.from_value(self.shell_state, portal_scope=portal_scope, fallback_surface_id=requested_surface_id)
        )
        transition = (
            self.transition
            if isinstance(self.transition, PortalShellTransition) or self.transition is None
            else PortalShellTransition.from_value(self.transition)
        )
        nimm_envelope = (
            self.nimm_envelope
            if isinstance(self.nimm_envelope, NimmDirectiveEnvelope) or self.nimm_envelope is None
            else NimmDirectiveEnvelope.from_dict(self.nimm_envelope)
        )
        surface_query = _normalize_surface_query(
            self.surface_query,
            field_name="portal_shell_request.surface_query",
        )
        object.__setattr__(self, "requested_surface_id", requested_surface_id)
        object.__setattr__(self, "portal_scope", portal_scope)
        object.__setattr__(self, "shell_state", shell_state)
        object.__setattr__(self, "transition", transition)
        object.__setattr__(self, "nimm_envelope", nimm_envelope)
        object.__setattr__(self, "surface_query", surface_query)

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "schema": self.schema,
            "requested_surface_id": self.requested_surface_id,
            "portal_scope": self.portal_scope.to_dict(),
        }
        if self.shell_state is not None:
            payload["shell_state"] = self.shell_state.to_dict()
        if self.transition is not None:
            payload["transition"] = self.transition.to_dict()
        if self.nimm_envelope is not None:
            payload["nimm_envelope"] = self.nimm_envelope.to_dict()
        if self.surface_query:
            payload["surface_query"] = dict(self.surface_query)
        return payload

    @classmethod
    def from_dict(cls, payload: dict[str, Any] | None) -> PortalShellRequest:
        if payload is None:
            return cls()
        if not isinstance(payload, dict):
            raise ValueError("portal_shell_request must be a dict")
        _require_schema(payload, expected=PORTAL_SHELL_REQUEST_SCHEMA, field_name="portal_shell_request.schema")
        portal_scope = PortalScope.from_value(payload.get("portal_scope"))
        requested_surface_id = payload.get("requested_surface_id") or SYSTEM_ROOT_SURFACE_ID
        return cls(
            requested_surface_id=requested_surface_id,
            portal_scope=portal_scope,
            shell_state=PortalShellState.from_value(
                payload.get("shell_state"),
                portal_scope=portal_scope,
                fallback_surface_id=requested_surface_id,
            )
            if payload.get("shell_state") is not None
            else None,
            transition=PortalShellTransition.from_value(payload.get("transition")),
            nimm_envelope=NimmDirectiveEnvelope.from_dict(payload.get("nimm_envelope"))
            if payload.get("nimm_envelope") is not None
            else None,
            surface_query=_normalize_surface_query(
                payload.get("surface_query"),
                field_name="portal_shell_request.surface_query",
            ),
        )


@dataclass(frozen=True)
class PortalSurfaceCatalogEntry:
    surface_id: str
    label: str
    route: str
    root_surface_id: str
    surface_kind: str
    page_owner: str
    read_write_posture: str = "read-only"
    tool_id: str = ""
    launchable: bool = True
    default_surface: bool = False
    schema: str = field(default=PORTAL_SURFACE_CATALOG_ENTRY_SCHEMA, init=False)

    def __post_init__(self) -> None:
        if not as_text(self.surface_id):
            raise ValueError("surface_catalog.surface_id is required")
        if not as_text(self.label):
            raise ValueError("surface_catalog.label is required")
        if not as_text(self.route):
            raise ValueError("surface_catalog.route is required")
        if self.root_surface_id not in ROOT_SURFACE_IDS:
            raise ValueError("surface_catalog.root_surface_id must be SYSTEM, NETWORK, or UTILITIES")
        if self.read_write_posture not in {"read-only", "write"}:
            raise ValueError("surface_catalog.read_write_posture must be read-only or write")

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "surface_id": self.surface_id,
            "label": self.label,
            "route": self.route,
            "root_surface_id": self.root_surface_id,
            "surface_kind": self.surface_kind,
            "page_owner": self.page_owner,
            "read_write_posture": self.read_write_posture,
            "tool_id": self.tool_id,
            "launchable": bool(self.launchable),
            "default_surface": bool(self.default_surface),
        }


# Phase 12a (Phase 12 plan: drift remediation): PortalToolRegistryEntry was
# duplicated here and in shell.py — every phase that touched the dataclass
# had to edit both copies. The canonical definition now lives in shell.py
# only; shell_registry.py imports it from there.


@dataclass(frozen=True)
class PortalShellResolution:
    requested_surface_id: str
    active_surface_id: str
    selection_status: str
    allowed: bool
    reducer_owned: bool
    shell_state: PortalShellState | None = None
    canonical_route: str = ""
    canonical_query: dict[str, str] = field(default_factory=dict)
    canonical_url: str = ""
    reason_code: str = ""
    reason_message: str = ""
