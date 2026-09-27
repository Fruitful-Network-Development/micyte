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
from ._requirements import FARM
from ._shared.utilities import as_text as _as_text
from ._viewscope import build_viewscope_payload
from .geospatial_projection_viewer import build_geospatial_payload, resolve_farm_profile

_SCHEMA = "mycite.v2.portal.workbench.tool.farm_profile.v1"
_PROFILE_CARD_SCHEMA = "mycite.v2.portal.workbench.tool.profile_card.v1"
_GEO_SCHEMA = "mycite.v2.portal.workbench.tool.geospatial_projection.v1"


class FarmProfileViewer:
    """profile_card identity + geospatial_projection map, composed."""

    tool_id = "farm_profile"
    label = "Farm Profile"
    summary = "Property fields and equal-square plots — profile card + geospatial projection."
    route = WORKBENCH_UI_TOOL_ROUTE
    #: Scoped to the instance kind this belongs to — see tools/_requirements.
    requires = FARM

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
        geo = build_geospatial_payload(doc)
        # IDENTITY comes from the document, through its `farm_identity` archetype — who the
        # farm is and the boundary collection its geometry hangs off are stored rows, and a
        # Python class that reads them positionally is exactly what the archetype library
        # exists to retire. `profile_card` used to build this half.
        identity_pane = build_viewscope_payload(
            authority_db_file=Path(authority_db_file),
            document_id=doc_id,
            archetype="farm_identity",
        )
        # The COUNTS stay a tool's output, because they are not in the document: parcels,
        # fields and plots are derived by walking the HOPS filament. Deriving is what a
        # tool is for; representing is not.
        #
        # `plots_source` is NOT here. A stat tile is for a figure, and a tile holding
        # "live_preview" clips; the map pane's own header already says
        # "N features · plots: live_preview", so it was duplicated as well as misplaced.
        derived_pane = {
            "schema": _PROFILE_CARD_SCHEMA,
            "container": "stat_tiles",
            "title": "Derived",
            "tiles": [
                {"label": "Parcels", "value": geo["parcel_count"]},
                {"label": "Fields", "value": geo["field_count"]},
                {"label": "Plots", "value": geo["plot_count"]},
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
                {"tool_id": "viewscope", "label": "Identity", "panel_payload": identity_pane},
                {"tool_id": "farm_derived", "label": "Derived", "panel_payload": derived_pane},
                {"tool_id": "geospatial_projection", "label": "Map", "panel_payload": geo_pane},
            ],
        }


# Self-register on import.
register(FarmProfileViewer())
