"""Delegate — the agronomics PLAN tab's authoring surface (all geometry writes live here).

Built ON the ``geospatial_projection`` base (the field/plots map): the client
(``renderClusterEditor``) renders the same feature_collection as context and lets the operator draw
a cluster region inside the field, drag / rotate / vertex-edit it, set a plot layout (grid angle
[0,90) + real-world cell size + per-side spacing) and preview the plots locally — then POST
``{field_node, region, layout}`` to ``save_cluster``, where the server packs the authoritative plots
(``pack_plots``). It also draws fields (``save_field``) and edits individual plots
(``save_plots`` / ``delete_plots``).

Every write is EFFECTIVE-DATED: geometry a contract depends on is retired rather than destroyed, so
the payload carries the viewing day and an ``effective_day`` route the save bar defaults to. The
editor reads the geometry in force on that day — you cannot reshape what you are not looking at.

Keeps ``tool_id = "plot_manager"`` so the existing wiring/registration is unchanged.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from micyte.core.datum_ops import field_registry as _fr
from micyte.core.structures.hops import decode_hops_coordinate_token
from micyte.state_machine.portal_shell.shell_schemas import (
    WORKBENCH_UI_TOOL_ROUTE,
)

from ._archetype import find_named_document, read_sandbox_catalog, resolve_tool_sandbox
from ._registry import register
from ._shared.utilities import as_text as _as_text
from ._shared.utilities import row_head as _row_head
from .geospatial_projection_viewer import build_geospatial_payload, resolve_farm_scene
from .plot_overview_viewer import _DAY_PARAM, parse_day

_SCHEMA = "mycite.v2.portal.workbench.tool.plot_manager.v1"
_TENANT_DEFAULT = "fnd"
# The registrar's own literal markers (NOT the agro_erp RF_* set): rf.3-1-2 is the entity msn node,
# rf.3-1-1 the HOPS coordinate.
_REGISTRAR = "registrar"
_REG_PROFILES = "fnd_ag_profiles"
_REG_MSN = _fr.marker(_fr.REGISTRAR, "msn_id")        # rf.3-1-2 — entity msn node
_REG_COORD = _fr.marker(_fr.REGISTRAR, "coordinate")  # rf.3-1-1 — HOPS coordinate
# The frame an empty farm opens on, in metres across — big enough to place a field inside.
_BOOTSTRAP_SPAN_M = 600.0


def _farm_center(authority_db_file: Path | None, doc: Any) -> tuple[float, float] | None:
    """The farm's own (lon, lat) from its registrar ag-profile row, or None.

    A farm_profile's document id is ``lv.<msn>.<sandbox>.<name>.<hash>`` — the farm's registrar msn
    node is right there, and `create_farm` mints the farm against exactly that node, so an onboarded
    farm can be located even before it has any geometry.

    Reads the registrar row DIRECTLY rather than going through build_network_map_payload: that
    builder needs the registrar's ``network_sources`` manifest and projects the whole network, none
    of which is wanted here. Registrar rows use their own literal markers — ``rf.3-1-2`` is the
    entity msn (not a title) and ``rf.3-1-1`` the HOPS coordinate — so this must not reuse the
    agro_erp ``RF_*`` set. Only called on the empty-farm path, and None when the farm has no
    registrar profile (some older sandboxes do not).
    """
    parts = _as_text(getattr(doc, "document_id", "")).split(".")
    if len(parts) < 2 or not parts[1]:
        return None
    msn = parts[1]
    docs, err = read_sandbox_catalog(authority_db_file, tenant_id=_TENANT_DEFAULT)
    if err:
        return None
    profiles = find_named_document(docs, sandbox=_REGISTRAR, name=_REG_PROFILES)
    for row in getattr(profiles, "rows", ()) or ():
        head = _row_head(row)
        pairs = {_as_text(head[i]).lower(): _as_text(head[i + 1])
                 for i in range(1, len(head) - 1, 2)}
        if pairs.get(_REG_MSN) != msn or not pairs.get(_REG_COORD):
            continue
        try:
            d = decode_hops_coordinate_token(pairs[_REG_COORD])
            return float(d["longitude"]["value"]), float(d["latitude"]["value"])
        except Exception:
            return None
    return None


class PlotManagerViewer:
    tool_id = "plot_manager"
    label = "Delegate"
    summary = "Draw fields and clusters, edit plots, and save the changes on an effective day."
    route = WORKBENCH_UI_TOOL_ROUTE
    applies_to_archetype: tuple[str, ...] = ("hops_geospatial_filament",)
    applies_to_source_kind: tuple[str, ...] = ()
    wants_surface_query = True

    def build_panel_payload(
        self, *, authority_db_file: Path | None, sandbox_id: str, document_id: str,
        datum_address: str, extra_query: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        doc, authority, err = resolve_farm_scene(authority_db_file, sandbox_id, document_id, tool=self)
        if err:
            return {**err, "schema": _SCHEMA}
        # The authoring surface edits the geometry in force on the PLAN tab's viewing day, the same
        # as_of every other sub-tab reads — you cannot reshape what you are not looking at. Unlike
        # the Plot overview it keeps preview=True, so a field with no drawn plots still shows the
        # grid it would get.
        day = parse_day(_as_text((extra_query or {}).get(_DAY_PARAM)))
        geo = build_geospatial_payload(doc, as_of=day, authority=authority)
        extra: dict[str, Any] = {}
        # Bootstrap case: a farm onboarded without parcels (create_farm's `parcels` is optional) has
        # NO geometry at all, so the editor's fit-to-content frame has nothing to fit — and Field
        # mode, whose whole job is to draw the first field, had no surface to draw on. Fall back to
        # the farm's own registrar coordinate so the operator can start from somewhere real.
        if not geo["feature_count"]:
            center = _farm_center(authority_db_file, doc)
            if center:
                extra["default_center"] = list(center)
                extra["default_span_m"] = _BOOTSTRAP_SPAN_M
        return {
            "schema": _SCHEMA,
            "sandbox_id": resolve_tool_sandbox(sandbox_id, doc=doc),
            "document_id": _as_text(doc.document_id),
            "day": day.isoformat(),
            "day_param": _DAY_PARAM,
            **extra,
            # Every write the editor can make. save_cluster packs the authoritative plots
            # (pack_plots) inside the drawn region; effective_day is a READ — the first day a
            # reshape lands without stranding a contract, which the save bar defaults to.
            "cluster_route": "/portal/api/v2/agro/save_cluster",
            "field_route": "/portal/api/v2/agro/save_field",
            "plots_route": "/portal/api/v2/agro/save_plots",
            "delete_plots_route": "/portal/api/v2/agro/delete_plots",
            "delete_cluster_route": "/portal/api/v2/agro/delete_cluster",
            "effective_day_route": "/portal/api/v2/agro/effective_day",
            **geo,
        }


register(PlotManagerViewer())
