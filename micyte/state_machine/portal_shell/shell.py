from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlencode

from micyte.core.document_naming import (
    CanonicalNameError,
    parse_canonical_document_id,
)
from micyte.core.network_root_surface_query import normalize_network_surface_query
from micyte.state_machine.nimm import (
    NimmDirective,
    NimmDirectiveEnvelope,
    NimmTargetAddress,
    normalize_nimm_verb,
)

from . import shell_registry as _shell_registry
from .shell_schemas import *


def _as_text(value: object) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _normalize_slug(value: object) -> str:
    return _as_text(value).lower().replace("-", "_").replace(" ", "_")


def _require_schema(payload: dict[str, Any], *, expected: str, field_name: str) -> None:
    schema = _as_text(payload.get("schema"))
    if schema != expected:
        raise ValueError(f"{field_name} must be {expected}")


def _normalize_surface_query(value: object, *, field_name: str) -> dict[str, str]:
    if value is None:
        return {}
    if not isinstance(value, Mapping):
        raise ValueError(f"{field_name} must be a mapping or null")
    out: dict[str, str] = {}
    for raw_key, raw_value in value.items():
        key = _as_text(raw_key)
        if not key:
            raise ValueError(f"{field_name} keys must be non-empty")
        token = _as_text(raw_value)
        if token:
            out[key] = token
    return out


def _normalize_capabilities(value: object, *, field_name: str) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, str) and not _as_text(value):
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
        scope_id = _as_text(self.scope_id) or PORTAL_SCOPE_DEFAULT_ID
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
        token = _as_text(self.id)
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
        active_surface_id = _as_text(self.active_surface_id) or SYSTEM_ROOT_SURFACE_ID
        verb = normalize_nimm_verb(self.verb, field_name="portal_shell_state.verb")
        chrome = self.chrome if isinstance(self.chrome, PortalShellChrome) else PortalShellChrome.from_value(self.chrome)
        scope_id = PORTAL_SCOPE_DEFAULT_ID
        if self.focus_path:
            first_segment = self.focus_path[0]
            if isinstance(first_segment, PortalFocusSegment):
                scope_id = first_segment.id or PORTAL_SCOPE_DEFAULT_ID
            elif isinstance(first_segment, dict):
                scope_id = _as_text(first_segment.get("id")) or PORTAL_SCOPE_DEFAULT_ID
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
            return initial_portal_shell_state(surface_id=fallback_surface_id, portal_scope=portal_scope or PortalScope())
        if not isinstance(payload, dict):
            raise ValueError("portal_shell_state must be a dict or null")
        if _as_text(payload.get("schema")) not in {"", PORTAL_SHELL_STATE_SCHEMA}:
            raise ValueError(f"portal_shell_state.schema must be {PORTAL_SHELL_STATE_SCHEMA}")
        scope_id = (portal_scope or PortalScope()).scope_id
        focus_path = _normalize_focus_path(payload.get("focus_path"), scope_id=scope_id)
        return cls(
            active_surface_id=payload.get("active_surface_id") or fallback_surface_id,
            focus_path=focus_path,
            focus_subject=_normalize_subject(payload.get("focus_subject")) or _subject_from_segment(focus_path[-1]),
            mediation_subject=_normalize_subject(payload.get("mediation_subject")),
            verb=_as_text(payload.get("verb")) or VERB_NAVIGATE,
            chrome=PortalShellChrome.from_value(payload.get("chrome")),
        )


@dataclass(frozen=True)
class PortalShellTransition:
    kind: str
    surface_id: str = ""
    sandbox_id: str = ""
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
        object.__setattr__(self, "surface_id", _as_text(self.surface_id))
        object.__setattr__(self, "sandbox_id", _as_text(self.sandbox_id))
        object.__setattr__(self, "file_key", _as_text(self.file_key))
        object.__setattr__(self, "datum_id", _as_text(self.datum_id))
        object.__setattr__(self, "object_id", _as_text(self.object_id))
        object.__setattr__(self, "verb", verb)

    def to_dict(self) -> dict[str, Any]:
        payload = {"kind": self.kind}
        if self.surface_id:
            payload["surface_id"] = self.surface_id
        if self.sandbox_id:
            payload["sandbox_id"] = self.sandbox_id
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
            sandbox_id=payload.get("sandbox_id") or "",
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
        requested_surface_id = _as_text(self.requested_surface_id) or SYSTEM_ROOT_SURFACE_ID
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
        if not _as_text(self.surface_id):
            raise ValueError("surface_catalog.surface_id is required")
        if not _as_text(self.label):
            raise ValueError("surface_catalog.label is required")
        if not _as_text(self.route):
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


@dataclass(frozen=True)
class PortalToolRegistryEntry:
    tool_id: str
    label: str
    surface_id: str
    entrypoint_id: str
    route: str
    tool_kind: str
    surface_posture: str
    read_write_posture: str
    required_capabilities: tuple[str, ...] = ()
    default_enabled: bool = True
    default_workbench_visible: bool = False
    summary: str = ""
    applies_to_archetype: tuple[str, ...] = ()
    applies_to_source_kind: tuple[str, ...] = ()
    # Canonical hyphae values (sha256 tokens from core.datum_semantics.
    # compile_hyphae_value) this tool binds to — content-derived eligibility,
    # parallel to applies_to_archetype/source_kind. Stored verbatim (NOT slugged,
    # so the token matches). The palette unions tools whose value intersects the
    # selected datum's compiled hyphae value(s).
    applies_to_hyphae_value: tuple[str, ...] = ()
    is_extension: bool = False
    # Phase 11 (datum_catalog_phase_e4_migration.md): tools that mutate the
    # MOS datum store declare which AuthoritativeDatumDocument.source_kind
    # they may write. The palette eligibility predicate does not consume
    # this field yet — it's reserved for future tool→datum applicability
    # checks and locked in here so the contract is in place when datum
    # work begins.
    manipulates_datum_kinds: tuple[str, ...] = ()
    schema: str = field(default=PORTAL_TOOL_REGISTRY_ENTRY_SCHEMA, init=False)

    def __post_init__(self) -> None:
        if not _as_text(self.tool_id):
            raise ValueError("tool_registry.tool_id is required")
        if self.is_extension:
            # Phase 14b: extensions now live across two Utilities surfaces:
            # ``utilities.extensions`` (operational: Email, Analytics,
            # Newsletter, PayPal) and ``utilities.grantee_profile`` (the
            # ext_grantee_profile form). The legacy ``utilities.tool_exposure``
            # surface_id remains accepted so external bookmarks resolve until
            # 14e drops it entirely.
            if self.surface_id not in {
                UTILITIES_EXTENSIONS_SURFACE_ID,
                UTILITIES_GRANTEE_PROFILE_SURFACE_ID,
                UTILITIES_TOOL_EXPOSURE_SURFACE_ID,
            }:
                raise ValueError(
                    "tool_registry.surface_id must be a Utilities extension surface "
                    "(utilities.extensions, utilities.grantee_profile, or the legacy "
                    "utilities.tool_exposure) when is_extension=True"
                )
        else:
            if self.surface_id not in TOOL_SURFACE_IDS:
                raise ValueError("tool_registry.surface_id must be a known tool surface")
        if self.tool_kind not in {TOOL_KIND_GENERAL, TOOL_KIND_SERVICE, TOOL_KIND_HOST_ALIAS}:
            raise ValueError("tool_registry.tool_kind is invalid")
        if self.surface_posture != SURFACE_POSTURE_PALETTE_TARGET:
            raise ValueError("tool_registry.surface_posture must be SURFACE_POSTURE_PALETTE_TARGET")
        if self.read_write_posture not in {"read-only", "write"}:
            raise ValueError("tool_registry.read_write_posture must be read-only or write")
        object.__setattr__(
            self,
            "required_capabilities",
            _normalize_capabilities(self.required_capabilities, field_name="tool_registry.required_capabilities"),
        )
        object.__setattr__(self, "default_workbench_visible", bool(self.default_workbench_visible))
        object.__setattr__(
            self,
            "applies_to_archetype",
            _normalize_capabilities(self.applies_to_archetype, field_name="tool_registry.applies_to_archetype"),
        )
        object.__setattr__(
            self,
            "applies_to_source_kind",
            _normalize_capabilities(self.applies_to_source_kind, field_name="tool_registry.applies_to_source_kind"),
        )
        # Hyphae values are opaque sha256 tokens — store verbatim (dedup + drop
        # empties), never slugified, or they'd never match a compiled value.
        object.__setattr__(
            self,
            "applies_to_hyphae_value",
            tuple(dict.fromkeys(v for v in (_as_text(t) for t in self.applies_to_hyphae_value) if v)),
        )
        object.__setattr__(self, "is_extension", bool(self.is_extension))
        object.__setattr__(
            self,
            "manipulates_datum_kinds",
            _normalize_capabilities(self.manipulates_datum_kinds, field_name="tool_registry.manipulates_datum_kinds"),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "tool_id": self.tool_id,
            "label": self.label,
            "surface_id": self.surface_id,
            "entrypoint_id": self.entrypoint_id,
            "route": self.route,
            "tool_kind": self.tool_kind,
            "surface_posture": self.surface_posture,
            "read_write_posture": self.read_write_posture,
            "required_capabilities": list(self.required_capabilities),
            "default_enabled": bool(self.default_enabled),
            "default_workbench_visible": self.default_workbench_visible,
            "summary": self.summary,
            "applies_to_archetype": list(self.applies_to_archetype),
            "applies_to_source_kind": list(self.applies_to_source_kind),
            "is_extension": self.is_extension,
            "manipulates_datum_kinds": list(self.manipulates_datum_kinds),
        }


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


def build_portal_surface_catalog() -> tuple[PortalSurfaceCatalogEntry, ...]:
    return _shell_registry.build_portal_surface_catalog()


def build_portal_tool_registry_entries() -> tuple[PortalToolRegistryEntry, ...]:
    return _shell_registry.build_portal_tool_registry_entries()


def resolve_portal_surface(surface_id: object) -> PortalSurfaceCatalogEntry | None:
    normalized_surface_id = _as_text(surface_id)
    for entry in build_portal_surface_catalog():
        if entry.surface_id == normalized_surface_id:
            return entry
    return None


def resolve_portal_tool_registry_entry(tool_id: object = "", *, surface_id: object = "") -> PortalToolRegistryEntry | None:
    normalized_tool_id = _as_text(tool_id)
    normalized_surface_id = _as_text(surface_id)
    for entry in build_portal_tool_registry_entries():
        if normalized_tool_id and entry.tool_id == normalized_tool_id:
            return entry
        if normalized_surface_id and entry.surface_id == normalized_surface_id:
            return entry
    return None


def canonical_route_for_surface(surface_id: object) -> str:
    entry = resolve_portal_surface(surface_id)
    return entry.route if entry is not None else SYSTEM_ROOT_ROUTE


def surface_root_id(surface_id: object) -> str:
    entry = resolve_portal_surface(surface_id)
    return entry.root_surface_id if entry is not None else SYSTEM_ROOT_SURFACE_ID


def is_tool_surface(surface_id: object) -> bool:
    return _as_text(surface_id) in TOOL_SURFACE_IDS


def requires_shell_state_machine(surface_id: object) -> bool:
    return _as_text(surface_id) in REDUCER_OWNED_SURFACE_IDS


_TOOL_SURFACE_TO_SANDBOX_ID: dict[str, str] = {
    WORKBENCH_UI_TOOL_SURFACE_ID: "workbench_ui",
    TRAPP_FAMILY_FARM_TOOL_SURFACE_ID: "trapp_family_farm",
}


def sandbox_id_for_surface(surface_id: object) -> str:
    """Return the canonical sandbox token for a surface.

    SYSTEM and non-tool surfaces map to ``"system"``. Tool surfaces map
    to their canonical underscore sandbox token (``"cts_gis"``,
    ``"grantee_legacy"``, …) used in canonical document ids
    (``lv.<msn>.<sandbox>.<name>.<hash>``).
    URL route slugs (``/tools/cts-gis``) are separate and remain hyphenated.
    """

    surface_token = _as_text(surface_id)
    if surface_token in _TOOL_SURFACE_TO_SANDBOX_ID:
        return _TOOL_SURFACE_TO_SANDBOX_ID[surface_token]
    return "system"


def anchor_file_key_for_sandbox(sandbox_id: object) -> str:
    sandbox_token = _as_text(sandbox_id) or "system"
    return SYSTEM_ANCHOR_FILE_KEY if sandbox_token == "system" else TOOL_ANCHOR_FILE_KEY


# Operational file keys address the OPERATIONAL subsystem (system/tool anchors,
# activity log, profile basics) — they are NOT datum documents. Phase B keeps
# them out of the datum file-key parser so the workbench's datum addressing and
# the instance's operational state stay separate. Operational config itself
# (grantee/extension) lives in the runtime's OperationalStore, not the state
# machine.
OPERATIONAL_FILE_KEYS = frozenset(
    {
        SYSTEM_ANCHOR_FILE_KEY,
        TOOL_ANCHOR_FILE_KEY,
        SYSTEM_ACTIVITY_FILE_KEY,
        SYSTEM_PROFILE_BASICS_FILE_KEY,
    }
)


def is_operational_file_key(file_key: object) -> bool:
    """True for operational-subsystem anchors (not datum documents)."""
    return _as_text(file_key) in OPERATIONAL_FILE_KEYS


def sandbox_id_for_file_key(file_key: object) -> str:
    """Sandbox token for a DATUM document file key.

    Datum-only: handles canonical ``lv.<msn>.<sandbox>.<name>.<hash>`` and the
    legacy ``system:`` / ``sandbox:`` datum forms. Operational file keys
    (``is_operational_file_key``) are not datum documents and return ""; they
    are recognized by the operational subsystem, not by this parser.
    """
    token = _as_text(file_key)
    if token.startswith("lv."):
        parts = token.split(".")
        return parts[2] if len(parts) >= 4 else ""
    if token.startswith("system:"):
        return "system"
    if token.startswith("sandbox:"):
        rest = token[len("sandbox:"):]
        sandbox_token = rest.split(":", 1)[0]
        return sandbox_token.replace("_", "-")
    return ""


def _normalize_active_sandbox_id(
    *,
    active_surface_id: str,
    portal_scope: PortalScope,
    requested_sandbox_id: object = "",
) -> str:
    requested = _as_text(requested_sandbox_id)
    surface_sandbox = sandbox_id_for_surface(active_surface_id)
    if not requested or requested == portal_scope.scope_id:
        return surface_sandbox
    if is_tool_surface(active_surface_id) and requested != surface_sandbox:
        return surface_sandbox
    if active_surface_id == SYSTEM_ROOT_SURFACE_ID and requested != "system":
        return "system"
    return requested


def _file_key_allowed_for_sandbox(file_key: object, *, sandbox_id: str) -> bool:
    token = _as_text(file_key)
    if not token:
        return False
    if token == SYSTEM_SANDBOX_QUERY_FILE_TOKEN:
        return True
    if token == anchor_file_key_for_sandbox(sandbox_id):
        return True
    parsed_sandbox = sandbox_id_for_file_key(token)
    if parsed_sandbox:
        return parsed_sandbox == sandbox_id
    return sandbox_id == "system"


def _normalize_file_key_for_sandbox(file_key: object, *, sandbox_id: str) -> str:
    token = _as_text(file_key)
    if not token:
        return anchor_file_key_for_sandbox(sandbox_id)
    if token == SYSTEM_SANDBOX_QUERY_FILE_TOKEN:
        return SYSTEM_SANDBOX_QUERY_FILE_TOKEN
    if _file_key_allowed_for_sandbox(token, sandbox_id=sandbox_id):
        return token
    return anchor_file_key_for_sandbox(sandbox_id)


def _clamp_focus_path_to_sandbox(
    focus_path: tuple[PortalFocusSegment, ...],
    *,
    active_surface_id: str,
    portal_scope: PortalScope,
) -> tuple[PortalFocusSegment, ...]:
    requested_sandbox = focus_path[0].id if focus_path else ""
    sandbox_id = _normalize_active_sandbox_id(
        active_surface_id=active_surface_id,
        portal_scope=portal_scope,
        requested_sandbox_id=requested_sandbox,
    )
    if not focus_path:
        return default_focus_path(sandbox_id=sandbox_id, include_anchor_file=False)
    clamped: list[PortalFocusSegment] = [PortalFocusSegment(level=FOCUS_LEVEL_SANDBOX, id=sandbox_id)]
    if len(focus_path) == 1:
        return tuple(clamped)
    file_key = _normalize_file_key_for_sandbox(focus_path[1].id, sandbox_id=sandbox_id)
    if file_key == SYSTEM_SANDBOX_QUERY_FILE_TOKEN:
        return tuple(clamped)
    clamped.append(PortalFocusSegment(level=FOCUS_LEVEL_FILE, id=file_key))
    for segment in focus_path[2:]:
        clamped.append(segment)
    return tuple(clamped)


def default_focus_path(
    *,
    scope_id: str = "",
    sandbox_id: str = "",
    include_anchor_file: bool,
) -> tuple[PortalFocusSegment, ...]:
    active_sandbox_id = _as_text(sandbox_id) or _as_text(scope_id) or "system"
    segments = [PortalFocusSegment(level=FOCUS_LEVEL_SANDBOX, id=active_sandbox_id)]
    if include_anchor_file:
        segments.append(PortalFocusSegment(level=FOCUS_LEVEL_FILE, id=anchor_file_key_for_sandbox(active_sandbox_id)))
    return tuple(segments)


def initial_portal_shell_state(
    *,
    surface_id: str,
    portal_scope: PortalScope | dict[str, Any],
) -> PortalShellState:
    normalized_scope = portal_scope if isinstance(portal_scope, PortalScope) else PortalScope.from_value(portal_scope)
    sandbox_id = sandbox_id_for_surface(surface_id)
    focus_path = default_focus_path(
        sandbox_id=sandbox_id,
        include_anchor_file=requires_shell_state_machine(surface_id),
    )
    base_state = PortalShellState(
        active_surface_id=surface_id,
        focus_path=focus_path,
        focus_subject=_subject_from_segment(focus_path[-1]),
        mediation_subject=None,
        verb=VERB_NAVIGATE,
        chrome=PortalShellChrome(control_panel_collapsed=False),
    )
    return canonicalize_portal_shell_state(
        base_state,
        active_surface_id=surface_id,
        portal_scope=normalized_scope,
        seed_anchor_file=True,
    )


def focus_level_for_shell_state(shell_state: PortalShellState | dict[str, Any] | None) -> str:
    if shell_state is None:
        return FOCUS_LEVEL_SANDBOX
    state = shell_state if isinstance(shell_state, PortalShellState) else PortalShellState.from_value(shell_state)
    return state.focus_path[-1].level if state.focus_path else FOCUS_LEVEL_SANDBOX


def segment_id_for_level(shell_state: PortalShellState | dict[str, Any] | None, *, level: str) -> str:
    if shell_state is None:
        return ""
    state = shell_state if isinstance(shell_state, PortalShellState) else PortalShellState.from_value(shell_state)
    for segment in state.focus_path:
        if segment.level == level:
            return segment.id
    return ""


def _focus_path_contains_subject(focus_path: tuple[PortalFocusSegment, ...], subject: dict[str, str] | None) -> bool:
    if not isinstance(subject, dict):
        return False
    subject_level = _normalize_slug(subject.get("level"))
    subject_id = _as_text(subject.get("id"))
    if subject_level not in FOCUS_LEVEL_INDEX or not subject_id:
        return False
    for segment in focus_path:
        if segment.level == subject_level and segment.id == subject_id:
            return True
    return False


def _state_with(
    state: PortalShellState,
    *,
    active_surface_id: str | None = None,
    focus_path: tuple[PortalFocusSegment, ...] | None = None,
    focus_subject: dict[str, str] | None | object = ...,
    mediation_subject: dict[str, str] | None | object = ...,
    verb: str | None = None,
    chrome: PortalShellChrome | None = None,
) -> PortalShellState:
    next_focus_path = focus_path if focus_path is not None else state.focus_path
    next_focus_subject = state.focus_subject if focus_subject is ... else focus_subject
    next_mediation_subject = state.mediation_subject if mediation_subject is ... else mediation_subject
    return PortalShellState(
        active_surface_id=active_surface_id or state.active_surface_id,
        focus_path=next_focus_path,
        focus_subject=next_focus_subject,
        mediation_subject=next_mediation_subject,
        verb=verb or state.verb,
        chrome=chrome or state.chrome,
    )


def _subject_for_level(focus_path: tuple[PortalFocusSegment, ...], *, level: str) -> dict[str, str] | None:
    for segment in focus_path:
        if segment.level == level:
            return segment.to_dict()
    return None


def canonicalize_portal_shell_state(
    shell_state: PortalShellState | dict[str, Any] | None,
    *,
    active_surface_id: str,
    portal_scope: PortalScope,
    seed_anchor_file: bool,
) -> PortalShellState:
    state = PortalShellState.from_value(
        shell_state,
        portal_scope=portal_scope,
        fallback_surface_id=active_surface_id,
    )
    surface_sandbox_id = sandbox_id_for_surface(active_surface_id)
    focus_path = _normalize_focus_path(state.focus_path, scope_id=surface_sandbox_id)
    focus_path = _clamp_focus_path_to_sandbox(
        focus_path,
        active_surface_id=active_surface_id,
        portal_scope=portal_scope,
    )
    if seed_anchor_file and len(focus_path) == 1:
        focus_path = default_focus_path(
            sandbox_id=focus_path[0].id,
            include_anchor_file=True,
        )
    focus_subject = _subject_from_segment(focus_path[-1])
    mediation_subject = state.mediation_subject if _focus_path_contains_subject(focus_path, state.mediation_subject) else None
    verb = state.verb
    chrome = state.chrome

    if is_tool_surface(active_surface_id):
        mediation_subject = mediation_subject or focus_subject
        verb = VERB_MEDIATE
    elif active_surface_id == SYSTEM_ROOT_SURFACE_ID:
        if verb == VERB_MEDIATE:
            if mediation_subject is None:
                verb = VERB_NAVIGATE
        else:
            mediation_subject = None

    return PortalShellState(
        active_surface_id=active_surface_id,
        focus_path=focus_path,
        focus_subject=focus_subject,
        mediation_subject=mediation_subject,
        verb=verb,
        chrome=chrome,
    )


def reduce_portal_shell_state(
    *,
    active_surface_id: str,
    portal_scope: PortalScope | dict[str, Any],
    current_state: PortalShellState | dict[str, Any] | None,
    transition: PortalShellTransition | dict[str, Any] | None,
    seed_anchor_file: bool,
) -> PortalShellState:
    normalized_scope = portal_scope if isinstance(portal_scope, PortalScope) else PortalScope.from_value(portal_scope)
    state = canonicalize_portal_shell_state(
        current_state,
        active_surface_id=active_surface_id,
        portal_scope=normalized_scope,
        seed_anchor_file=seed_anchor_file,
    )
    normalized_transition = PortalShellTransition.from_value(transition)
    if normalized_transition is None:
        return canonicalize_portal_shell_state(
            state,
            active_surface_id=active_surface_id,
            portal_scope=normalized_scope,
            seed_anchor_file=seed_anchor_file,
        )

    focus_path = list(state.focus_path)
    verb = state.verb
    mediation_subject = state.mediation_subject
    chrome = state.chrome

    if normalized_transition.kind == TRANSITION_ENTER_SURFACE:
        return canonicalize_portal_shell_state(
            state,
            active_surface_id=active_surface_id,
            portal_scope=normalized_scope,
            seed_anchor_file=seed_anchor_file,
        )

    if normalized_transition.kind == TRANSITION_FOCUS_SANDBOX:
        next_sandbox_id = _normalize_active_sandbox_id(
            active_surface_id=active_surface_id,
            portal_scope=normalized_scope,
            requested_sandbox_id=normalized_transition.sandbox_id,
        )
        anchor_file_key = _normalize_file_key_for_sandbox(
            normalized_transition.file_key or anchor_file_key_for_sandbox(next_sandbox_id),
            sandbox_id=next_sandbox_id,
        )
        focus_path = [
            PortalFocusSegment(level=FOCUS_LEVEL_SANDBOX, id=next_sandbox_id),
            PortalFocusSegment(level=FOCUS_LEVEL_FILE, id=anchor_file_key),
        ]
    elif normalized_transition.kind == TRANSITION_FOCUS_FILE:
        current_sandbox_id = _normalize_active_sandbox_id(
            active_surface_id=active_surface_id,
            portal_scope=normalized_scope,
            requested_sandbox_id=segment_id_for_level(state, level=FOCUS_LEVEL_SANDBOX),
        )
        next_file_key = _as_text(normalized_transition.file_key)
        if next_file_key == SYSTEM_SANDBOX_QUERY_FILE_TOKEN:
            focus_path = [PortalFocusSegment(level=FOCUS_LEVEL_SANDBOX, id=current_sandbox_id)]
        else:
            next_file_key = _normalize_file_key_for_sandbox(next_file_key, sandbox_id=current_sandbox_id)
            focus_path = [
                PortalFocusSegment(level=FOCUS_LEVEL_SANDBOX, id=current_sandbox_id),
                PortalFocusSegment(level=FOCUS_LEVEL_FILE, id=next_file_key),
            ]
    elif normalized_transition.kind == TRANSITION_FOCUS_DATUM:
        current_sandbox_id = _normalize_active_sandbox_id(
            active_surface_id=active_surface_id,
            portal_scope=normalized_scope,
            requested_sandbox_id=segment_id_for_level(state, level=FOCUS_LEVEL_SANDBOX),
        )
        file_key = _normalize_file_key_for_sandbox(
            normalized_transition.file_key or segment_id_for_level(state, level=FOCUS_LEVEL_FILE),
            sandbox_id=current_sandbox_id,
        )
        focus_path = [
            PortalFocusSegment(level=FOCUS_LEVEL_SANDBOX, id=current_sandbox_id),
            PortalFocusSegment(level=FOCUS_LEVEL_FILE, id=file_key),
        ]
        if normalized_transition.datum_id:
            focus_path.append(PortalFocusSegment(level=FOCUS_LEVEL_DATUM, id=normalized_transition.datum_id))
    elif normalized_transition.kind == TRANSITION_FOCUS_OBJECT:
        current_sandbox_id = _normalize_active_sandbox_id(
            active_surface_id=active_surface_id,
            portal_scope=normalized_scope,
            requested_sandbox_id=segment_id_for_level(state, level=FOCUS_LEVEL_SANDBOX),
        )
        file_key = _normalize_file_key_for_sandbox(
            normalized_transition.file_key or segment_id_for_level(state, level=FOCUS_LEVEL_FILE),
            sandbox_id=current_sandbox_id,
        )
        datum_id = normalized_transition.datum_id or segment_id_for_level(state, level=FOCUS_LEVEL_DATUM)
        focus_path = [
            PortalFocusSegment(level=FOCUS_LEVEL_SANDBOX, id=current_sandbox_id),
            PortalFocusSegment(level=FOCUS_LEVEL_FILE, id=file_key),
        ]
        if datum_id:
            focus_path.append(PortalFocusSegment(level=FOCUS_LEVEL_DATUM, id=datum_id))
        if normalized_transition.object_id:
            focus_path.append(PortalFocusSegment(level=FOCUS_LEVEL_OBJECT, id=normalized_transition.object_id))
    elif normalized_transition.kind == TRANSITION_BACK_OUT:
        if len(focus_path) > 1:
            focus_path = focus_path[:-1]
        else:
            focus_path = focus_path[:]
    elif normalized_transition.kind == TRANSITION_SET_VERB:
        verb = normalized_transition.verb or VERB_NAVIGATE
        if verb == VERB_MEDIATE:
            mediation_subject = _subject_from_segment(focus_path[-1])
        else:
            mediation_subject = None
    # Phase 12c (drift remediation): TRANSITION_OPEN_INTERFACE_PANEL and
    # TRANSITION_CLOSE_INTERFACE_PANEL dispatch arms removed. The interface
    # panel is hidden unconditionally since Phase 3d, so toggling its
    # chrome open/closed flag has no observable effect. No caller has
    # emitted these transitions since Phase 5 retired the NIMM-AITAS UI
    # that produced them.

    next_state = PortalShellState(
        active_surface_id=active_surface_id,
        focus_path=tuple(focus_path),
        focus_subject=_subject_from_segment(focus_path[-1]) if focus_path else _subject_for_level(tuple(focus_path), level=FOCUS_LEVEL_SANDBOX),
        mediation_subject=mediation_subject,
        verb=verb,
        chrome=chrome,
    )
    return canonicalize_portal_shell_state(
        next_state,
        active_surface_id=active_surface_id,
        portal_scope=normalized_scope,
        seed_anchor_file=seed_anchor_file,
    )


def canonical_query_for_shell_state(
    shell_state: PortalShellState | dict[str, Any] | None,
    *,
    surface_id: str,
) -> dict[str, str]:
    if not requires_shell_state_machine(surface_id):
        return {}
    state = shell_state if isinstance(shell_state, PortalShellState) else PortalShellState.from_value(shell_state)
    file_id = segment_id_for_level(state, level=FOCUS_LEVEL_FILE)
    query: dict[str, str] = {
        "file": file_id or SYSTEM_SANDBOX_QUERY_FILE_TOKEN,
        "verb": state.verb,
    }
    datum_id = segment_id_for_level(state, level=FOCUS_LEVEL_DATUM)
    object_id = segment_id_for_level(state, level=FOCUS_LEVEL_OBJECT)
    if datum_id:
        query["datum"] = datum_id
    if object_id:
        query["object"] = object_id
    return query


def _sandbox_filter_from_document_id(document_id: str) -> str:
    """Infer the sandbox token from a canonical ``lv.`` document id.

    Returns ``""`` for non-canonical/legacy ids (``system:``/``sandbox:``) and
    for ``system`` documents — the workbench-ui view intentionally shows the
    whole-corpus when scoped to system, so only tool sandboxes
    (``agro_erp``/``cts_gis``/...) imply a sandbox filter.
    """
    try:
        parsed = parse_canonical_document_id(document_id)
    except CanonicalNameError:
        return ""
    sandbox = _as_text(parsed.sandbox)
    return sandbox if sandbox and sandbox != "system" else ""


def canonical_query_for_surface_query(
    surface_query: Mapping[str, Any] | None,
    *,
    surface_id: str,
) -> dict[str, str]:
    if surface_id == NETWORK_ROOT_SURFACE_ID:
        if surface_query is not None and not isinstance(surface_query, Mapping):
            raise ValueError("portal_shell_request.surface_query must be a mapping or null")
        query, _ = normalize_network_surface_query(surface_query)
        return query
    normalized = _normalize_surface_query(
        surface_query,
        field_name="portal_shell_request.surface_query",
    )
    # system.root hosts the unified workbench, so it shares the workbench
    # query vocabulary. Phase A (function-forward refactor) is collapsing the
    # dual state model so system.root becomes query-native like the workbench;
    # accepting its query here is the additive groundwork for that flip.
    if surface_id in {WORKBENCH_UI_TOOL_SURFACE_ID, SYSTEM_ROOT_SURFACE_ID}:
        query: dict[str, str] = {}
        document_id = _as_text(normalized.get("document"))
        if document_id:
            query["document"] = document_id
        document_filter = _as_text(normalized.get("document_filter"))
        if document_filter:
            query["document_filter"] = document_filter
        document_sort_key = _as_text(normalized.get("document_sort")).lower()
        if document_sort_key in {"document_id", "document_name", "source_kind", "row_count", "version_hash"}:
            query["document_sort"] = document_sort_key
        document_sort_direction = _as_text(normalized.get("document_dir")).lower()
        if document_sort_direction in {"asc", "desc"}:
            query["document_dir"] = document_sort_direction
        text_filter = _as_text(normalized.get("filter"))
        if text_filter:
            query["filter"] = text_filter
        sort_key = _as_text(normalized.get("sort")).lower()
        if sort_key in {
            "datum_address",
            "layer",
            "value_group",
            "iteration",
            "labels",
            "relation",
            "object_ref",
            "hyphae_hash",
        }:
            query["sort"] = sort_key
        sort_direction = _as_text(normalized.get("dir")).lower()
        if sort_direction in {"asc", "desc"}:
            query["dir"] = sort_direction
        group_mode = _as_text(normalized.get("group")).lower()
        if group_mode in {"flat", "layer", "layer_value_group", "layer_value_group_iteration"}:
            query["group"] = group_mode
        workbench_lens = _as_text(normalized.get("workbench_lens")).lower()
        if workbench_lens in {"interpreted", "raw"}:
            query["workbench_lens"] = workbench_lens
        source_visibility = _as_text(normalized.get("source")).lower()
        if source_visibility in {"show", "hide"}:
            query["source"] = source_visibility
        overlay = _as_text(normalized.get("overlay")).lower()
        if overlay in {"show", "hide"}:
            query["overlay"] = overlay
        row_id = _as_text(normalized.get("row"))
        if row_id:
            query["row"] = row_id
        # Plan v2 keys: workbench mode (docs/datums/author), sandbox
        # selection, and the currently-invoked visualization tool. These
        # parameterise the unified workbench but were not yet known when
        # the canonical-query whitelist was first authored.
        mode = _as_text(normalized.get("mode")).lower()
        if mode in {"docs", "datums", "author"}:
            query["mode"] = mode
        # Accept ``sandbox`` as an alias for ``sandbox_filter`` (legacy
        # redirects / bookmarks emitted ``?sandbox=``), and when no sandbox is
        # supplied, infer it from a canonical ``lv.<msn>.<sandbox>.<name>.<hash>``
        # document id so opening an Trapp Family Farm (or other tool-sandbox) document
        # resolves into its sandbox instead of dropping back to the whole-corpus
        # system view.
        sandbox_filter = _as_text(normalized.get("sandbox_filter")) or _as_text(normalized.get("sandbox"))
        if not sandbox_filter and document_id:
            sandbox_filter = _sandbox_filter_from_document_id(document_id)
        if sandbox_filter:
            query["sandbox_filter"] = sandbox_filter
        # Multi-tool visualization panel: `tools` is a comma-joined tool-id list.
        # Accept the legacy scalar `tool` and fold it in for back-compat.
        tools = _as_text(normalized.get("tools")) or _as_text(normalized.get("tool"))
        if tools:
            query["tools"] = tools
        # Per-tool selection: the unified SAMRAS structure viewer picks which anchor
        # structure (txa/msn/lcl) to render. Free-form name; the tool validates it
        # against the structures it discovers (unknown → falls back to the first).
        samras_structure = _as_text(normalized.get("samras_structure"))
        if samras_structure:
            query["samras_structure"] = samras_structure
        return query
    return {}


def canonical_query_for_runtime_request_payload(
    request_payload: Mapping[str, Any] | None,
    *,
    surface_id: str,
    legacy_query_keys: tuple[str, ...] = (),
) -> dict[str, str]:
    payload = dict(request_payload or {})
    raw_surface_query = payload.get("surface_query")
    surface_query: Mapping[str, Any] | None
    if isinstance(raw_surface_query, Mapping):
        surface_query = raw_surface_query
    elif legacy_query_keys:
        legacy_surface_query: dict[str, Any] = {}
        for key in legacy_query_keys:
            token = _as_text(payload.get(key))
            if token:
                legacy_surface_query[key] = token
        surface_query = legacy_surface_query
    else:
        surface_query = None
    return canonical_query_for_surface_query(
        surface_query,
        surface_id=surface_id,
    )


def _normalize_runtime_payload_schema(
    payload: Mapping[str, Any] | None,
    *,
    expected_schema: str,
) -> dict[str, Any]:
    normalized_payload = dict(payload or {})
    if normalized_payload.get("schema") in {None, ""}:
        normalized_payload = {"schema": expected_schema, **normalized_payload}
    if _as_text(normalized_payload.get("schema")) != expected_schema:
        raise ValueError(f"request.schema must be {expected_schema}")
    return normalized_payload


def normalize_runtime_surface_request_payload(
    payload: Mapping[str, Any] | None,
    *,
    expected_schema: str,
    surface_id: str,
    legacy_query_keys: tuple[str, ...] = (),
) -> tuple[PortalScope, dict[str, Any], dict[str, str]]:
    normalized_payload = _normalize_runtime_payload_schema(payload, expected_schema=expected_schema)
    portal_scope = PortalScope.from_value(normalized_payload.get("portal_scope"))
    surface_query = canonical_query_for_runtime_request_payload(
        normalized_payload,
        surface_id=surface_id,
        legacy_query_keys=legacy_query_keys,
    )
    return portal_scope, normalized_payload, surface_query


def normalize_runtime_surface_action_request_payload(
    payload: Mapping[str, Any] | None,
    *,
    expected_schema: str,
    surface_id: str,
    legacy_query_keys: tuple[str, ...] = (),
) -> tuple[PortalScope, dict[str, Any], dict[str, str], dict[str, Any] | None, str, dict[str, Any]]:
    portal_scope, normalized_payload, surface_query = normalize_runtime_surface_request_payload(
        payload,
        expected_schema=expected_schema,
        surface_id=surface_id,
        legacy_query_keys=legacy_query_keys,
    )
    raw_shell_state = normalized_payload.get("shell_state")
    shell_state = dict(raw_shell_state) if isinstance(raw_shell_state, dict) else None
    action_kind = _as_text(normalized_payload.get("action_kind"))
    raw_action_payload = normalized_payload.get("action_payload")
    action_payload = dict(raw_action_payload) if isinstance(raw_action_payload, Mapping) else {}
    return portal_scope, normalized_payload, surface_query, shell_state, action_kind, action_payload


def normalize_runtime_shell_surface_request_payload(
    payload: Mapping[str, Any] | None,
    *,
    expected_schema: str,
    surface_id: str,
) -> tuple[PortalScope, PortalShellState, dict[str, Any]]:
    normalized_payload = _normalize_runtime_payload_schema(payload, expected_schema=expected_schema)
    portal_scope = PortalScope.from_value(normalized_payload.get("portal_scope"))
    shell_state = canonicalize_portal_shell_state(
        normalized_payload.get("shell_state"),
        active_surface_id=surface_id,
        portal_scope=portal_scope,
        seed_anchor_file=normalized_payload.get("shell_state") is None,
    )
    return portal_scope, shell_state, normalized_payload


def normalize_runtime_shell_action_request_payload(
    payload: Mapping[str, Any] | None,
    *,
    expected_schema: str,
    surface_id: str,
) -> tuple[PortalScope, PortalShellState, dict[str, Any], str, dict[str, Any]]:
    portal_scope, shell_state, normalized_payload = normalize_runtime_shell_surface_request_payload(
        payload,
        expected_schema=expected_schema,
        surface_id=surface_id,
    )
    action_kind = _as_text(normalized_payload.get("action_kind"))
    raw_action_payload = normalized_payload.get("action_payload")
    action_payload = dict(raw_action_payload) if isinstance(raw_action_payload, Mapping) else {}
    return portal_scope, shell_state, normalized_payload, action_kind, action_payload


def build_canonical_url(*, surface_id: str, query: Mapping[str, str] | None = None) -> str:
    route = canonical_route_for_surface(surface_id)
    filtered = {key: value for key, value in dict(query or {}).items() if _as_text(value)}
    if not filtered:
        return route
    return f"{route}?{urlencode(filtered)}"


def build_portal_shell_request_payload(
    *,
    requested_surface_id: str,
    portal_scope: PortalScope | dict[str, Any] | None,
    shell_state: PortalShellState | dict[str, Any] | None = None,
    transition: PortalShellTransition | dict[str, Any] | None = None,
    nimm_envelope: NimmDirectiveEnvelope | dict[str, Any] | None = None,
    surface_query: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    scope = portal_scope if isinstance(portal_scope, PortalScope) else PortalScope.from_value(portal_scope)
    state = (
        shell_state
        if isinstance(shell_state, PortalShellState) or shell_state is None
        else PortalShellState.from_value(shell_state, portal_scope=scope, fallback_surface_id=requested_surface_id)
    )
    normalized_transition = (
        transition
        if isinstance(transition, PortalShellTransition) or transition is None
        else PortalShellTransition.from_value(transition)
    )
    normalized_nimm_envelope = (
        nimm_envelope
        if isinstance(nimm_envelope, NimmDirectiveEnvelope) or nimm_envelope is None
        else NimmDirectiveEnvelope.from_dict(nimm_envelope)
    )
    return PortalShellRequest(
        requested_surface_id=requested_surface_id,
        portal_scope=scope,
        shell_state=state,
        transition=normalized_transition,
        nimm_envelope=normalized_nimm_envelope,
        surface_query=_normalize_surface_query(
            surface_query,
            field_name="portal_shell_request.surface_query",
        ),
    ).to_dict()


def build_nimm_envelope_for_shell_state(
    *,
    shell_state: PortalShellState | dict[str, Any],
    target_authority: str,
    document_id: str = "",
    aitas_defaults: dict[str, Any] | None = None,
    aitas_overrides: dict[str, Any] | None = None,
) -> NimmDirectiveEnvelope:
    state = shell_state if isinstance(shell_state, PortalShellState) else PortalShellState.from_value(shell_state)
    focus_targets = [
        NimmTargetAddress(
            file_key=segment_id_for_level(state, level=FOCUS_LEVEL_FILE) or SYSTEM_SANDBOX_QUERY_FILE_TOKEN,
            datum_address=segment_id_for_level(state, level=FOCUS_LEVEL_DATUM),
            object_ref=segment_id_for_level(state, level=FOCUS_LEVEL_OBJECT),
        )
    ]
    directive = NimmDirective(
        verb=state.verb,
        target_authority=target_authority,
        document_id=document_id,
        targets=tuple(focus_targets),
        payload={"source": "portal_shell_state"},
    )
    return NimmDirectiveEnvelope.with_merged_aitas(
        directive=directive,
        defaults=aitas_defaults,
        overrides=aitas_overrides,
    )


def resolve_portal_shell_request(request: PortalShellRequest | dict[str, Any] | None) -> PortalShellResolution:
    normalized_request = request if isinstance(request, PortalShellRequest) else PortalShellRequest.from_dict(request)
    requested_surface_id = normalized_request.requested_surface_id
    surface_entry = resolve_portal_surface(requested_surface_id)
    if surface_entry is None or not surface_entry.launchable:
        # Unknown surfaces fall back to system.root. Since Phase A made
        # system.root query-native, the fallback resolves the same way: no
        # reducer shell_state, an empty (default) workbench query.
        fallback_reducer_owned = requires_shell_state_machine(SYSTEM_ROOT_SURFACE_ID)
        fallback_state = (
            initial_portal_shell_state(surface_id=SYSTEM_ROOT_SURFACE_ID, portal_scope=normalized_request.portal_scope)
            if fallback_reducer_owned
            else None
        )
        fallback_query = (
            canonical_query_for_shell_state(fallback_state, surface_id=SYSTEM_ROOT_SURFACE_ID)
            if fallback_state is not None
            else {}
        )
        return PortalShellResolution(
            requested_surface_id=requested_surface_id,
            active_surface_id=SYSTEM_ROOT_SURFACE_ID,
            selection_status="unknown",
            allowed=False,
            reducer_owned=fallback_reducer_owned,
            shell_state=fallback_state,
            canonical_route=SYSTEM_ROOT_ROUTE,
            canonical_query=fallback_query,
            canonical_url=build_canonical_url(surface_id=SYSTEM_ROOT_SURFACE_ID, query=fallback_query),
            reason_code="surface_unknown",
            reason_message=f"Surface is not approved: {requested_surface_id}",
        )

    # Phase A: the focus-path reducer is retired. Every surface is query-
    # native — selection travels as surface_query (workbench) or tool_state
    # (cts_gis), never through reducer transitions. shell_state, when present
    # on the request, is passed through as a passive value object (the
    # profile-basics / system-workspace paths still read focus_subject; that
    # residue is removed in the operational/datum split).
    reducer_owned = False
    shell_state = normalized_request.shell_state if isinstance(normalized_request.shell_state, PortalShellState) else None
    canonical_query = canonical_query_for_surface_query(
        normalized_request.surface_query,
        surface_id=surface_entry.surface_id,
    )
    canonical_route = canonical_route_for_surface(surface_entry.surface_id)
    return PortalShellResolution(
        requested_surface_id=requested_surface_id,
        active_surface_id=surface_entry.surface_id,
        selection_status="available",
        allowed=True,
        reducer_owned=reducer_owned,
        shell_state=shell_state,
        canonical_route=canonical_route,
        canonical_query=canonical_query,
        canonical_url=build_canonical_url(surface_id=surface_entry.surface_id, query=canonical_query),
    )


def activity_icon_id_for_surface(surface_id: object) -> str:
    normalized_surface_id = _as_text(surface_id)
    if normalized_surface_id == SYSTEM_ROOT_SURFACE_ID:
        return "system"
    if normalized_surface_id == NETWORK_ROOT_SURFACE_ID:
        return "network"
    if normalized_surface_id in {UTILITIES_ROOT_SURFACE_ID, UTILITIES_TOOL_EXPOSURE_SURFACE_ID}:
        return "utilities"
    if normalized_surface_id == WORKBENCH_UI_TOOL_SURFACE_ID:
        return "workbench_ui"
    if normalized_surface_id == TRAPP_FAMILY_FARM_TOOL_SURFACE_ID:
        return "trapp_family_farm"
    return "generic"


def map_surface_to_active_service(active_surface_id: str) -> str:
    root_id = surface_root_id(active_surface_id)
    if root_id == NETWORK_ROOT_SURFACE_ID:
        return "network"
    if root_id == UTILITIES_ROOT_SURFACE_ID:
        return "utilities"
    return "system"


def shell_composition_mode_for_surface(active_surface_id: str) -> str:
    if is_tool_surface(active_surface_id):
        return "tool"
    return "system"


def surface_posture_for_surface(active_surface_id: str) -> str:
    if is_tool_surface(active_surface_id):
        entry = resolve_portal_tool_registry_entry(surface_id=active_surface_id)
        if entry is not None:
            return entry.surface_posture
    return SURFACE_POSTURE_INTERFACE_PANEL_PRIMARY


def default_workbench_visible_for_surface(active_surface_id: str) -> bool:
    if is_tool_surface(active_surface_id):
        entry = resolve_portal_tool_registry_entry(surface_id=active_surface_id)
        if entry is not None:
            return entry.default_workbench_visible
        return False
    return True


def foreground_region_for_surface(active_surface_id: str) -> str:
    # portal-tool-overlay-restructure: the interface-panel sidebar was removed; the workbench is
    # the only foreground region (tools render in the menubar-search overlay). Kept as a function
    # (rather than inlined) so callers/tests retain a single source for the foreground region.
    _ = active_surface_id
    return "center-workbench"


def apply_surface_posture_to_composition(composition: dict[str, Any]) -> None:
    if not isinstance(composition, dict):
        return
    active_surface_id = _as_text(composition.get("active_surface_id"))
    regions = composition.get("regions")
    if not isinstance(regions, dict):
        return
    if not isinstance(regions.get("workbench"), dict):
        return
    composition["foreground_shell_region"] = foreground_region_for_surface(active_surface_id)


def _region_visible(value: object, *, default: bool) -> bool:
    if value is None:
        return default
    return value is not False


def build_shell_composition_payload(
    *,
    active_surface_id: str,
    portal_instance_id: str,
    page_title: str,
    page_subtitle: str,
    activity_items: list[dict[str, Any]],
    control_panel: dict[str, Any],
    workbench: dict[str, Any],
    shell_state: PortalShellState | dict[str, Any] | None = None,
    control_panel_collapsed: bool = False,
    activity_footer: dict[str, Any] | None = None,
) -> dict[str, Any]:
    # portal-tool-overlay-restructure: the interface_panel region was removed — tools render in
    # the menubar-search → full-screen overlay, not a sidebar region.
    state = shell_state if isinstance(shell_state, PortalShellState) else (
        PortalShellState.from_value(shell_state) if isinstance(shell_state, dict) else None
    )
    tool_surface = is_tool_surface(active_surface_id)
    surface_posture_for_surface(active_surface_id)
    workbench_region = dict(workbench or {})
    workbench_region.setdefault("schema", PORTAL_SHELL_REGION_WORKBENCH_SCHEMA)
    workbench_visible = _region_visible(
        workbench_region.get("visible"),
        default=default_workbench_visible_for_surface(active_surface_id),
    )
    force_workbench_visible = workbench_region.get("forced_visible") is True
    if tool_surface:
        workbench_visible = bool(force_workbench_visible or default_workbench_visible_for_surface(active_surface_id))
    workbench_region["visible"] = workbench_visible
    workbench_collapsed = not bool(workbench_visible)
    workbench_region["collapsed"] = workbench_collapsed
    composition = {
        "schema": PORTAL_SHELL_COMPOSITION_SCHEMA,
        "composition_mode": shell_composition_mode_for_surface(active_surface_id),
        "active_service": map_surface_to_active_service(active_surface_id),
        "active_surface_id": _as_text(active_surface_id),
        "active_tool_surface_id": _as_text(active_surface_id) if is_tool_surface(active_surface_id) else None,
        "foreground_shell_region": foreground_region_for_surface(active_surface_id),
        "control_panel_collapsed": bool(control_panel_collapsed),
        "workbench_collapsed": workbench_collapsed,
        "portal_instance_id": _as_text(portal_instance_id) or PORTAL_SCOPE_DEFAULT_ID,
        "page_title": _as_text(page_title) or "MiCyte",
        "page_subtitle": _as_text(page_subtitle),
        "shell_state": None if state is None else state.to_dict(),
        "regions": {
            "activity_bar": {
                "schema": PORTAL_SHELL_REGION_ACTIVITY_BAR_SCHEMA,
                "dispatch": "post_portal_shell",
                "items": list(activity_items),
                # Pinned below the nav list: the instance the operator is viewing
                # as, and the other instances they may switch to. Empty dict when
                # the store cannot be read — the bar still renders its nav.
                "footer": dict(activity_footer or {}),
            },
            "control_panel": dict(control_panel or {}),
            "workbench": workbench_region,
        },
    }
    apply_surface_posture_to_composition(composition)
    return composition




__all__ = [
    "ARCHETYPE_HYPHAE_RUDI",
    "ARCHETYPE_MSS_DOC",
    "ARCHETYPE_SAMRAS_FAMILY",
    "FOCUS_LEVEL_DATUM",
    "FOCUS_LEVEL_FILE",
    "FOCUS_LEVEL_OBJECT",
    "FOCUS_LEVEL_SANDBOX",
    "NETWORK_ROOT_ROUTE",
    "NETWORK_ROOT_SURFACE_ID",
    "OPERATIONAL_FILE_KEYS",
    "PORTAL_SCOPE_DEFAULT_ID",
    "PORTAL_SHELL_ACTIVITY_FOOTER_SCHEMA",
    "PORTAL_SHELL_COMPOSITION_SCHEMA",
    "PORTAL_SHELL_ENTRYPOINT_ID",
    "PORTAL_SHELL_REGION_ACTIVITY_BAR_SCHEMA",
    "PORTAL_SHELL_REGION_CONTROL_PANEL_SCHEMA",
    "PORTAL_SHELL_REGION_WORKBENCH_SCHEMA",
    "PORTAL_SHELL_REQUEST_SCHEMA",
    "PORTAL_SHELL_STATE_SCHEMA",
    "PORTAL_SURFACE_CATALOG_ENTRY_SCHEMA",
    "PORTAL_TOOL_REGISTRY_ENTRY_SCHEMA",
    "SURFACE_POSTURE_INTERFACE_PANEL_PRIMARY",
    "SURFACE_POSTURE_PALETTE_TARGET",
    "SYSTEM_ACTIVITY_FILE_KEY",
    "SYSTEM_ANCHOR_FILE_KEY",
    "SYSTEM_PROFILE_BASICS_FILE_KEY",
    "SYSTEM_ROOT_ROUTE",
    "SYSTEM_ROOT_SURFACE_ID",
    "SYSTEM_SANDBOX_QUERY_FILE_TOKEN",
    "SYSTEM_SURFACE_IDS",
    "TOOL_ANCHOR_FILE_KEY",
    "TOOL_KIND_GENERAL",
    "TOOL_KIND_HOST_ALIAS",
    "TOOL_KIND_SERVICE",
    "TOOL_SURFACE_IDS",
    "TRANSITION_BACK_OUT",
    "TRANSITION_ENTER_SURFACE",
    "TRANSITION_FOCUS_DATUM",
    "TRANSITION_FOCUS_FILE",
    "TRANSITION_FOCUS_OBJECT",
    "TRANSITION_FOCUS_SANDBOX",
    "TRANSITION_SET_VERB",
    "TRAPP_FAMILY_FARM_SANDBOX_TOKEN",
    "TRAPP_FAMILY_FARM_TOOL_ENTRYPOINT_ID",
    "TRAPP_FAMILY_FARM_TOOL_ROUTE",
    "TRAPP_FAMILY_FARM_TOOL_SURFACE_ID",
    "UTILITIES_EXTENSIONS_ROUTE",
    "UTILITIES_EXTENSIONS_SURFACE_ID",
    "UTILITIES_GRANTEE_PROFILE_ROUTE",
    "UTILITIES_GRANTEE_PROFILE_SURFACE_ID",
    "UTILITIES_PERIPHERALS_ROUTE",
    "UTILITIES_PERIPHERALS_SURFACE_ID",
    "UTILITIES_ROOT_ROUTE",
    "UTILITIES_ROOT_SURFACE_ID",
    "UTILITIES_TOOLS_ROUTE",
    "UTILITIES_TOOLS_SURFACE_ID",
    "UTILITIES_TOOL_EXPOSURE_ROUTE",
    "UTILITIES_TOOL_EXPOSURE_SURFACE_ID",
    "VERB_INVESTIGATE",
    "VERB_MANIPULATE",
    "VERB_MEDIATE",
    "VERB_NAVIGATE",
    "WORKBENCH_UI_SANDBOX_TOKEN",
    "WORKBENCH_UI_TOOL_ENTRYPOINT_ID",
    "WORKBENCH_UI_TOOL_ROUTE",
    "WORKBENCH_UI_TOOL_SURFACE_ID",
    "PortalFocusSegment",
    "PortalScope",
    "PortalShellChrome",
    "PortalShellRequest",
    "PortalShellResolution",
    "PortalShellState",
    "PortalShellTransition",
    "PortalSurfaceCatalogEntry",
    "PortalToolRegistryEntry",
    "activity_icon_id_for_surface",
    "anchor_file_key_for_sandbox",
    "apply_surface_posture_to_composition",
    "build_canonical_url",
    "build_nimm_envelope_for_shell_state",
    "build_portal_shell_request_payload",
    "build_portal_surface_catalog",
    "build_portal_tool_registry_entries",
    "build_shell_composition_payload",
    "canonical_query_for_runtime_request_payload",
    "canonical_query_for_shell_state",
    "canonical_query_for_surface_query",
    "canonical_route_for_surface",
    "canonicalize_portal_shell_state",
    "default_focus_path",
    "default_workbench_visible_for_surface",
    "focus_level_for_shell_state",
    "foreground_region_for_surface",
    "initial_portal_shell_state",
    "is_operational_file_key",
    "is_tool_surface",
    "map_surface_to_active_service",
    "normalize_runtime_shell_action_request_payload",
    "normalize_runtime_shell_surface_request_payload",
    "normalize_runtime_surface_action_request_payload",
    "normalize_runtime_surface_request_payload",
    "reduce_portal_shell_state",
    "requires_shell_state_machine",
    "resolve_portal_shell_request",
    "resolve_portal_surface",
    "resolve_portal_tool_registry_entry",
    "sandbox_display_name",
    "sandbox_id_for_file_key",
    "sandbox_id_for_surface",
    "segment_id_for_level",
    "shell_composition_mode_for_surface",
    "surface_posture_for_surface",
    "surface_root_id",
]
