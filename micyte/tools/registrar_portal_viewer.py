"""MSN Node Manager (tool_id ``registrar_portal``) — a first-class tool for the ``registrar`` sandbox.

The registrar sandbox holds every network entity profile (the ``fnd_ag_profiles`` rows
plus the legal / administrative / natural entity docs). Until now it had no tool of its
own — its data was only ever rendered read-only, cross-sandbox, by the farm-scoped
Agronomics NETWORK tab. This tool gives it a dedicated surface to **search / view, edit
and create** entity profiles.

It is a *composition*, not a re-implementation:

* BROWSE (no ``registrar_profile`` param): the existing ``network_map`` pane beside the
  existing ``entity_profile_table`` pane, both projected from a single
  :func:`network_map_viewer.build_network_map_payload` read over ``registrar`` (via the
  pure :func:`entity_profile_table.build_entity_table_from_net`). A "+ New profile"
  toolbar button opens the create modal.
* DETAIL (``registrar_profile=<label>``): the selected profile's identity card + inline
  fields, its events (joined by msn node, each shown with a type glyph + the written
  type), and a back-out affordance — the generic select→detail→back mechanic.

Selection is keyed on the profile's UNIQUE ``label`` (an entity's msn node is NOT unique
— one entity can host several profiles). Writes round-trip through the MOS domain-write
actions (``/portal/api/v2/agro/{create,save}_ag_profile``); the profiles are MOS datum
documents, never YAML leaflets.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from micyte.core.datum_ops import field_registry as _fr
from micyte.state_machine.portal_shell.shell_schemas import (
    REGISTRAR_SANDBOX_TOKEN as _REGISTRAR,
)
from micyte.state_machine.portal_shell.shell_schemas import (
    WORKBENCH_UI_TOOL_ROUTE,
)

from ._archetype import document_sandbox, read_sandbox_catalog
from ._registry import register
from ._shared.utilities import as_text as _as_text
from ._shared.utilities import row_head as _row_head
from .entity_profile_table import build_entity_table_from_net
from .network_map_viewer import (
    _NAME,
    _NODE,
    _doc_name,
    _pairs,
    _row_label,
    build_network_map_payload,
)

_TENANT_DEFAULT = "fnd"
_SCHEMA = "mycite.v2.portal.workbench.tool.registrar_portal.v1"
_FOCUS_PARAM = "registrar_profile"
_CREATE_ROUTE = "/portal/api/v2/agro/create_ag_profile"
_SAVE_ROUTE = "/portal/api/v2/agro/save_ag_profile"
_ENTITY_DOC_NAMES = ("legal_entity", "administrative_entity", "natural_entity")
_NAME_PART = _fr.marker(_fr.REGISTRAR, "ruiqi_id")  # rf.3-1-4 — natural_entity given/family name parts

# ag-profile TYPE options (lcl 1-2-N) offered when creating / editing a profile. Value is
# the lcl node written to rf.3-1-13; the map derives the substance glyph + section from it.
_TYPE_OPTIONS: list[dict[str, str]] = [
    {"value": "1-2-1", "label": "Producer — farm"},
    {"value": "1-2-1-2", "label": "Producer — orchard"},
    {"value": "1-2-1-4", "label": "Producer — farm stand"},
    {"value": "1-2-1-5", "label": "Producer — apiary"},
    {"value": "1-2-1-6", "label": "Producer — vineyard"},
    {"value": "1-2-2", "label": "Farmers market"},
    {"value": "1-2-3", "label": "CSA"},
    {"value": "1-2-4", "label": "Food hub"},
    {"value": "1-2-5", "label": "Seed / input supplier"},
    {"value": "1-2-6", "label": "Organization"},
    {"value": "1-2-7", "label": "Administrative"},
]


def _notice(msg: str) -> dict[str, Any]:
    return {"schema": _SCHEMA, "tool_id": "registrar_portal", "mode": "browse",
            "notice": msg}


def _registrar_entities(docs: list[Any]) -> list[dict[str, str]]:
    """The registrar's entities (legal / administrative / natural), deduped by msn node,
    for the create picker: adding a profile reuses an existing entity's msn node."""
    seen: dict[str, str] = {}
    for doc in docs:
        if document_sandbox(doc) != _REGISTRAR or _doc_name(doc) not in _ENTITY_DOC_NAMES:
            continue
        for r in getattr(doc, "rows", ()) or ():
            pairs = _pairs(_row_head(r))
            msn = pairs.get(_NODE, [""])[0]
            if not msn:
                continue  # the doc's own identity row (no entity node)
            name = pairs.get(_NAME, [""])[0]
            if not name:  # natural_entity: given + family name parts
                name = " ".join(pairs.get(_NAME_PART, [])).strip()
            seen.setdefault(msn, name or _row_label(r) or msn)
    return [{"msn_node": m, "name": n}
            for m, n in sorted(seen.items(), key=lambda kv: kv[1].lower())]


def _browse_payload(net: dict[str, Any], docs: list[Any]) -> dict[str, Any]:
    # hide_csa suppresses the map's "CSA pickups" widget strip (not wanted in the node
    # manager); hide_events suppresses the events aside (the entity table owns the surface).
    map_payload = {**net, "hide_events": True, "hide_csa": True, "detail_param": _FOCUS_PARAM}
    table_payload = build_entity_table_from_net(
        net, sandbox_id=_REGISTRAR, detail_param=_FOCUS_PARAM)
    return {
        "schema": _SCHEMA,
        "tool_id": "registrar_portal",
        "mode": "browse",
        "sandbox_id": _REGISTRAR,
        "create_route": _CREATE_ROUTE,
        "save_route": _SAVE_ROUTE,
        "type_options": _TYPE_OPTIONS,
        "entities": _registrar_entities(docs),
        "profile_count": net.get("profile_count", 0),
        "composite": {
            "schema": _SCHEMA,
            "container": "composite",
            "direction": "row",
            "sandbox_id": _REGISTRAR,
            "panes": [
                {"tool_id": "network_map", "label": "Map", "panel_payload": map_payload},
                {"tool_id": "entity_profile_table", "label": "Entity Profiles",
                 "panel_payload": table_payload},
            ],
        },
    }


def _detail_payload(net: dict[str, Any], focus: str) -> dict[str, Any]:
    back = {"label": "Back to nodes", "param": _FOCUS_PARAM, "value": ""}
    p = next((x for x in net.get("profiles", []) if x.get("label") == focus), None)
    if p is None:
        return {"schema": _SCHEMA, "tool_id": "registrar_portal", "mode": "detail",
                "sandbox_id": _REGISTRAR, "back": back,
                "notice": f"profile {focus!r} not found"}
    msn = _as_text(p.get("msn_node"))
    events = [
        {"icon": e.get("icon"), "type_label": e.get("event_class_label"),
         "title": e.get("title"), "cadence": ", ".join(e.get("cadence", []) or []),
         "time_range": e.get("time_range"),
         "next": (e.get("next_occurrences") or [""])[0]}
        for e in net.get("events", []) if e.get("host_node") == msn
    ]
    lat, lon = p.get("lat"), p.get("lon")
    coord = f"{lat:.5f}, {lon:.5f}" if isinstance(lat, (int, float)) and isinstance(lon, (int, float)) else ""
    fields = [
        {"label": "Type", "value": _as_text(p.get("subtype") or p.get("category_label"))},
        {"label": "Class", "value": _as_text(p.get("color_class_label"))},
        {"label": "Region", "value": _as_text(p.get("region"))},
        {"label": "County", "value": _as_text(p.get("county"))},
        {"label": "Website", "value": _as_text(p.get("dns"))},
        {"label": "MSN node", "value": msn},
        {"label": "Coordinate", "value": coord},
    ]
    return {
        "schema": _SCHEMA,
        "tool_id": "registrar_portal",
        "mode": "detail",
        "sandbox_id": _REGISTRAR,
        "back": back,
        "type_options": _TYPE_OPTIONS,
        "profile": {"title": _as_text(p.get("name") or p.get("label")),
                    "samras_node": msn, "has_visual": False},
        "fields": fields,
        "events": events,
        "event_count": len(events),
        "edit": {
            "save_route": _SAVE_ROUTE,
            "sandbox_id": _REGISTRAR,
            "label": _as_text(p.get("label")),
            "datum_address": _as_text(p.get("datum_address")),
            "msn_node": msn,
            "name": _as_text(p.get("name")),
            "dns": _as_text(p.get("dns")),
            "lcl_type": _as_text(p.get("lcl_node")),
            "lon": lon,
            "lat": lat,
        },
    }


class RegistrarPortalViewer:
    """Search / view · edit · create entity profiles in the registrar sandbox."""

    tool_id = "registrar_portal"
    label = "MSN Node Manager"
    summary = "Search, view, edit and create the registrar's entity profiles by MSN node."
    route = WORKBENCH_UI_TOOL_ROUTE
    applies_to_archetype: tuple[str, ...] = ()
    applies_to_source_kind: tuple[str, ...] = ()
    wants_surface_query = True

    def build_panel_payload(
        self, *, authority_db_file: Path | None, sandbox_id: str, document_id: str,
        datum_address: str, extra_query: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        docs, err = read_sandbox_catalog(authority_db_file, tenant_id=_TENANT_DEFAULT)
        if err:
            return _notice(err)
        # One catalog read → one classification, reused for the map, the table and the
        # per-profile detail/event lookups (they can never drift).
        net = build_network_map_payload(docs, sandbox_id=_REGISTRAR)
        if net.get("error"):
            return _notice(_as_text(net["error"]))
        focus = _as_text((extra_query or {}).get(_FOCUS_PARAM))
        if focus:
            return _detail_payload(net, focus)
        return _browse_payload(net, docs)


# Self-register on import.
register(RegistrarPortalViewer())
