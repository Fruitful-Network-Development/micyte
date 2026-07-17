"""Farm Profile — the consolidated agro_erp geospatial tool.

farm_profile is now a CONSOLIDATION of two base tools: ``profile_card`` (identity: title +
SAMRAS id + visual) and ``geospatial_projection`` (the field/plots map). It resolves the
farm_profile HOPS filament once and lays the two out as a ``composite``. The map logic lives
in :mod:`geospatial_projection_viewer` (reused by ``plot_manager``); the identity comes from
:func:`profile_projection.build_profile_projection`.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from micyte.state_machine.portal_shell.shell_schemas import (
    WORKBENCH_UI_TOOL_ROUTE,
)

from ._archetype import resolve_tool_sandbox
from ._registry import register
from ._shared.utilities import as_text as _as_text
from .geospatial_projection_viewer import build_geospatial_payload, resolve_farm_profile
from .profile_projection import build_profile_projection

_SCHEMA = "mycite.v2.portal.workbench.tool.farm_profile.v1"
_PROFILE_CARD_SCHEMA = "mycite.v2.portal.workbench.tool.profile_card.v1"
_GEO_SCHEMA = "mycite.v2.portal.workbench.tool.geospatial_projection.v1"


class FarmProfileViewer:
    """profile_card identity + geospatial_projection map, composed."""

    tool_id = "farm_profile"
    label = "Farm Profile"
    summary = "Property fields and equal-square plots — profile card + geospatial projection."
    route = WORKBENCH_UI_TOOL_ROUTE
    applies_to_archetype: tuple[str, ...] = ("hops_geospatial_filament",)
    applies_to_source_kind: tuple[str, ...] = ()

    def build_panel_payload(
        self, *, authority_db_file: Path | None, sandbox_id: str, document_id: str, datum_address: str,
    ) -> dict[str, Any]:
        doc, err = resolve_farm_profile(authority_db_file, sandbox_id, document_id, tool=self)
        if err:
            return {**err, "schema": _SCHEMA}
        sandbox = resolve_tool_sandbox(sandbox_id, doc=doc)
        doc_id = _as_text(doc.document_id)
        profile = build_profile_projection(doc)
        geo = build_geospatial_payload(doc)
        profile_pane = {
            "schema": _PROFILE_CARD_SCHEMA,
            "container": "profile_card",
            "profile": profile,
            "fields": [
                {"label": "title", "value": profile["title"] or doc.canonical_name},
                {"label": "samras_node", "value": profile["samras_node"]},
                {"label": "parcels", "value": str(geo["parcel_count"])},
                {"label": "field", "value": str(geo["field_count"])},
                {"label": "plots", "value": str(geo["plot_count"])},
                {"label": "plots_source", "value": geo["plots_source"]},
            ],
        }
        geo_pane = {
            "schema": _GEO_SCHEMA, "sandbox_id": sandbox, "document_id": doc_id,
            "selected_row_address": _as_text(datum_address), **geo,
        }
        return {
            "schema": _SCHEMA,
            "container": "composite",
            "title": "Farm Profile",
            "sandbox_id": sandbox,
            "document_id": doc_id,
            "panes": [
                {"tool_id": "profile_card", "label": "Profile", "panel_payload": profile_pane},
                {"tool_id": "geospatial_projection", "label": "Map", "panel_payload": geo_pane},
            ],
        }


# Self-register on import.
register(FarmProfileViewer())
