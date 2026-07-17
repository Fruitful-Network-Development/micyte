"""
NIMM mediate handler utilities.

Provides pure component frame builder functions used by tool-specific runtimes
when constructing interface panel component frames from pre-resolved service data.

These builders are dependency-free: they accept already-resolved data dicts and
produce component frame payloads conforming to interface_panel_component_frame_contract.md.
Resolution of service data (datum store access, SAMRAS decode, etc.) is delegated to
the calling tool runtime — not performed here.
"""

from __future__ import annotations

from typing import Any

# Maps each canonical NIMM verb to the component frame it re-engages by default
# when injected from the directive terminal. Empty string = no automatic engagement.
NIMM_VERB_FRAME_ENGAGEMENT: dict[str, str] = {
    "navigate": "",
    "investigate": "",
    "mediate": "administrative_node_profile",
    "manipulate": "",
}


def _maybe_attach_tab_id(frame: dict[str, Any], tab_id: str) -> dict[str, Any]:
    """Attach an optional tab_id to a frame dict so interface panel renderers
    can partition component_frames by active tab.

    Frames without a tab_id render in every tab (legacy / tab-agnostic). Frames
    with a tab_id render only while that tab is active. See
    docs/contracts/interface_panel_component_frame_contract.md.
    """
    if tab_id:
        frame["tab_id"] = str(tab_id)
    return frame


def build_profile_component_frame(
    *,
    attention_node_id: str,
    label: str,
    fields: list[dict[str, str]],
    frame_id: str = "administrative_profile",
    variant: str = "",
    layout_slot: str = "",
    field_groups: list[dict[str, Any]] | None = None,
    collections: list[dict[str, Any]] | None = None,
    children: list[dict[str, Any]] | None = None,
    geospatial_frame: dict[str, Any] | None = None,
    lens_key: str = "",
    initializer_intent: str = "resolve_profile_for_attention",
    datum_address: str = "1-1-2",
    tab_id: str = "",
) -> dict[str, Any]:
    """Build a profile component frame from pre-resolved service data.

    Args:
        attention_node_id: The SAMRAS node id this profile represents (e.g. "3-2-3-17").
        label: Human-readable entity name (e.g. "Ohio").
        fields: Ordered list of {"label": str, "value": str} field rows.
        geospatial_frame: Optional geospatial_projection component frame for the subject_slot.
        lens_key: Stable string derived from the lens/intention state; combined with
                  attention_node_id to form the render_key.

    Returns:
        Component frame dict conforming to interface_panel_component_frame_contract.md.
    """
    render_key = f"{attention_node_id}::profile::{lens_key}"
    payload: dict[str, Any] = {
        "label": label,
        "msn_id": attention_node_id,
        "fields": fields,
    }
    if variant:
        payload["variant"] = variant
    if layout_slot:
        payload["layout_slot"] = layout_slot
    if field_groups is not None:
        payload["field_groups"] = list(field_groups)
    if collections is not None:
        payload["collections"] = list(collections)
    if geospatial_frame:
        payload["subject_slot"] = geospatial_frame
    if children is not None:
        payload["children"] = list(children)
    return _maybe_attach_tab_id({
        "frame_id": frame_id,
        "component_type": "profile",
        "label": label,
        "initializer": {
            "verb": "mediate",
            "target_authority": "cts_gis",
            "datum_address": datum_address,
            "intent": initializer_intent,
        },
        "payload": payload,
        "frozen": True,
        "render_key": render_key,
    }, tab_id)


def build_geospatial_component_frame(
    *,
    attention_node_id: str,
    geospatial_projection: dict[str, Any],
    parent_frame_id: str = "administrative_profile",
    lens_key: str = "",
    tab_id: str = "",
) -> dict[str, Any]:
    """Build a geospatial projection component frame from a pre-resolved projection payload.

    The geospatial frame is typically nested as the subject_slot of a profile frame.
    Its initializer carries parent_frame_id so the client can identify the dependency
    chain when re-engaging.

    Args:
        attention_node_id: The SAMRAS node id providing the geometry context.
        geospatial_projection: The geospatial_projection payload (feature_collection, bounds, etc.)
                               conforming to cts_gis_garland_projection_lens.md.
        parent_frame_id: frame_id of the profile frame that produced this geospatial data.
        lens_key: Stable string from lens/intention state; combined with attention_node_id
                  to form the render_key.

    Returns:
        Component frame dict conforming to interface_panel_component_frame_contract.md.
    """
    render_key = f"{attention_node_id}::geospatial::{lens_key}"
    return _maybe_attach_tab_id({
        "frame_id": f"{parent_frame_id}__geospatial",
        "component_type": "geospatial_projection",
        "label": "Spatial Projection",
        "initializer": {
            "verb": "mediate",
            "target_authority": "cts_gis",
            "intent": "resolve_geospatial_for_profile",
            "parent_frame_id": parent_frame_id,
        },
        "payload": geospatial_projection,
        "frozen": True,
        "render_key": render_key,
    }, tab_id)


def build_characteristic_set_component_frame(
    *,
    frame_id: str,
    label: str,
    items: list[dict[str, str]],
    attention_node_id: str,
    lens_key: str = "",
    target_authority: str = "cts_gis",
    tab_id: str = "",
) -> dict[str, Any]:
    """Build a characteristic set component frame from a list of labeled items.

    Args:
        frame_id: Unique frame identifier within the surface.
        label: Human-readable label for the characteristic set.
        items: List of {"label": str, "value": str, "detail"?: str} rows.
        attention_node_id: Node id providing context for the render_key.
        lens_key: Stable lens/intention string for render_key construction.

    Returns:
        Component frame dict conforming to interface_panel_component_frame_contract.md.
    """
    render_key = f"{attention_node_id}::characteristic_set::{frame_id}::{lens_key}"
    return _maybe_attach_tab_id({
        "frame_id": frame_id,
        "component_type": "characteristic_set",
        "label": label,
        "initializer": {
            "verb": "mediate",
            "target_authority": target_authority,
            "intent": "resolve_characteristic_set",
            "characteristic_set_id": frame_id,
        },
        "payload": {
            "label": label,
            "items": items,
        },
        "frozen": True,
        "render_key": render_key,
    }, tab_id)


def build_component_group_frame(
    *,
    frame_id: str,
    label: str,
    children: list[dict[str, Any]],
    attention_node_id: str,
    lens_key: str = "",
    layout: str = "",
    layout_slot: str = "",
    initializer_intent: str = "compose_component_group",
    datum_address: str = "1-1-2",
    target_authority: str = "cts_gis",
    tab_id: str = "",
) -> dict[str, Any]:
    """Build a nested component group frame for interface panel compositions."""
    render_key = f"{attention_node_id}::component_group::{frame_id}::{lens_key}"
    payload: dict[str, Any] = {
        "label": label,
        "children": list(children),
    }
    if layout:
        payload["layout"] = layout
    if layout_slot:
        payload["layout_slot"] = layout_slot
    return _maybe_attach_tab_id({
        "frame_id": frame_id,
        "component_type": "component_group",
        "label": label,
        "initializer": {
            "verb": "mediate",
            "target_authority": target_authority,
            "datum_address": datum_address,
            "intent": initializer_intent,
        },
        "payload": payload,
        "frozen": False,
        "render_key": render_key,
    }, tab_id)


def build_listing_component_frame(
    *,
    frame_id: str,
    label: str,
    columns: list[dict[str, str]],
    rows: list[dict[str, Any]],
    attention_node_id: str,
    lens_key: str = "",
    layout_slot: str = "",
    source_kind: str = "",
    empty_message: str = "No entries available.",
    placeholder_row_count: int = 0,
    initializer_intent: str = "resolve_listing",
    datum_address: str = "1-1-2",
    target_authority: str = "cts_gis",
    tab_id: str = "",
) -> dict[str, Any]:
    """Build a reusable tabular/listing component frame.

    placeholder_row_count: when greater than zero AND rows is empty, the
    frontend renderer paints that many numbered wireframe placeholder rows
    instead of the empty_message paragraph. Defaults to 0 so existing
    callers keep their current empty-state behavior.
    """
    render_key = f"{attention_node_id}::listing::{frame_id}::{lens_key}"
    payload: dict[str, Any] = {
        "label": label,
        "columns": list(columns),
        "rows": list(rows),
        "empty_message": empty_message,
    }
    if layout_slot:
        payload["layout_slot"] = layout_slot
    if source_kind:
        payload["source_kind"] = source_kind
    if placeholder_row_count and int(placeholder_row_count) > 0:
        payload["placeholder_row_count"] = int(placeholder_row_count)
    return _maybe_attach_tab_id({
        "frame_id": frame_id,
        "component_type": "listing",
        "label": label,
        "initializer": {
            "verb": "mediate",
            "target_authority": target_authority,
            "datum_address": datum_address,
            "intent": initializer_intent,
            "source_kind": source_kind,
        },
        "payload": payload,
        "frozen": True,
        "render_key": render_key,
    }, tab_id)


def build_chronology_matrix_component_frame(
    *,
    frame_id: str,
    label: str,
    row_headers: list[dict[str, str]],
    column_headers: list[str],
    events: list[dict[str, Any]],
    attention_node_id: str,
    lens_key: str = "",
    layout_slot: str = "",
    empty_message: str = "No chronological events available.",
    initializer_intent: str = "resolve_chronology_matrix",
    datum_address: str = "1-1-2",
    tab_id: str = "",
) -> dict[str, Any]:
    """Build a reusable chronology matrix component frame."""
    render_key = f"{attention_node_id}::chronology_matrix::{frame_id}::{lens_key}"
    payload: dict[str, Any] = {
        "label": label,
        "row_headers": list(row_headers),
        "column_headers": list(column_headers),
        "events": list(events),
        "empty_message": empty_message,
    }
    if layout_slot:
        payload["layout_slot"] = layout_slot
    return _maybe_attach_tab_id({
        "frame_id": frame_id,
        "component_type": "chronology_matrix",
        "label": label,
        "initializer": {
            "verb": "mediate",
            "target_authority": "cts_gis",
            "datum_address": datum_address,
            "intent": initializer_intent,
        },
        "payload": payload,
        "frozen": True,
        "render_key": render_key,
    }, tab_id)


# Phase 7 (portal_tool_surface_contract.md) — generic form-frame builder.
# Lets any extension or palette tool surface an editable form whose submit
# action posts back through buildComponentActionDispatch. The client-side
# renderer lives in v2_portal_component_library.js (renderFormComponent).

FORM_FIELD_TYPES: frozenset[str] = frozenset(
    {
        "text",
        "email",
        "url",
        "password",
        "boolean",
        "select",
        "string_list",
        "multiline",
    }
)


def _normalize_form_field(field: dict[str, Any]) -> dict[str, Any]:
    """Validate and shape one field descriptor. Pure; raises ValueError on bad input."""
    if not isinstance(field, dict):
        raise ValueError("form field must be a dict")
    key = str(field.get("key") or "").strip()
    if not key:
        raise ValueError("form field requires a non-empty 'key'")
    field_type = str(field.get("type") or "").strip()
    if field_type not in FORM_FIELD_TYPES:
        raise ValueError(
            f"form field {key!r} has unsupported type {field_type!r}; "
            f"allowed: {sorted(FORM_FIELD_TYPES)}"
        )
    normalized: dict[str, Any] = {
        "key": key,
        "label": str(field.get("label") or key),
        "type": field_type,
        "value": field.get("value"),
        "required": bool(field.get("required", False)),
    }
    if field.get("placeholder"):
        normalized["placeholder"] = str(field["placeholder"])
    if field.get("help_text"):
        normalized["help_text"] = str(field["help_text"])
    if field_type == "select":
        options = field.get("options") or []
        if not isinstance(options, (list, tuple)) or not options:
            raise ValueError(f"select field {key!r} requires a non-empty 'options' list")
        normalized["options"] = [
            {"value": str(o["value"]), "label": str(o.get("label") or o["value"])}
            if isinstance(o, dict)
            else {"value": str(o), "label": str(o)}
            for o in options
        ]
    if field_type == "string_list":
        # value should be a list of strings; normalize defensively.
        normalized["value"] = [str(v) for v in (field.get("value") or [])]
    if field_type == "boolean":
        normalized["value"] = bool(field.get("value", False))
    if field_type in {"text", "email", "url", "password", "multiline"} and field.get("value") is not None:
        normalized["value"] = str(field["value"])
    return normalized


def build_form_component_frame(
    *,
    frame_id: str,
    label: str,
    fields: list[dict[str, Any]],
    submit_action: dict[str, Any],
    attention_node_id: str = "",
    lens_key: str = "",
    submit_label: str = "Save",
    intro: str = "",
    target_authority: str = "utilities",
    tab_id: str = "",
) -> dict[str, Any]:
    """Build a form component frame for editable JSON-file surfaces.

    Args:
        frame_id: Unique frame identifier within the surface.
        label: Human-readable header above the form.
        fields: List of field descriptors. Each: {key, label?, type, value?,
                required?, placeholder?, help_text?, options? (select only)}.
                Allowed types: text, email, url, password, boolean, select,
                string_list, multiline.
        submit_action: {"route": str, "schema": str, "payload": dict}. The
                client-side renderer merges the form's collected values into
                payload before POSTing to route.
        attention_node_id / lens_key: optional context for render_key (mirrors
                other builders). Defaults produce a stable utility key.
        submit_label / intro: optional UI copy.

    Returns:
        Component frame dict; component_type="form". The JS dispatcher
        (renderComponentFrame in v2_portal_component_library.js) recognises
        this type and renders editable inputs.

    Raises:
        ValueError when fields list is empty, a field type is unknown, or a
        select field has no options.
    """
    if not fields:
        raise ValueError(f"form frame {frame_id!r} requires at least one field")
    if not isinstance(submit_action, dict) or not submit_action.get("route"):
        raise ValueError(f"form frame {frame_id!r} requires submit_action.route")

    normalized_fields = [_normalize_form_field(f) for f in fields]
    keys_seen: set[str] = set()
    for f in normalized_fields:
        if f["key"] in keys_seen:
            raise ValueError(f"form frame {frame_id!r} has duplicate field key {f['key']!r}")
        keys_seen.add(f["key"])

    render_key = f"{attention_node_id or 'utility'}::form::{frame_id}::{lens_key}"
    payload: dict[str, Any] = {
        "label": label,
        "fields": normalized_fields,
        "submit_label": submit_label,
        "submit_action": {
            "route": str(submit_action["route"]),
            "schema": str(submit_action.get("schema") or ""),
            "payload": dict(submit_action.get("payload") or {}),
        },
    }
    if intro:
        payload["intro"] = intro
    return _maybe_attach_tab_id({
        "frame_id": frame_id,
        "component_type": "form",
        "label": label,
        "initializer": {
            "verb": "mediate",
            "target_authority": target_authority,
            "intent": "resolve_form",
            "form_id": frame_id,
        },
        "payload": payload,
        "frozen": False,
        "render_key": render_key,
    }, tab_id)
