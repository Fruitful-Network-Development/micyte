"""Plot Overview — the agronomics PLAN tab's read-only farm-plot surface.

The viewing counterpart to the Cluster Editor: the same ``geospatial_projection`` base (fields /
clusters / plots), but it shows ONLY what has actually been defined and offers no authoring. Two
differences from the plain projection carry the intent:

* ``preview=False`` — no ``live_preview`` square-pack synthesis. A field with no drawn plots renders
  empty rather than fabricating a grid, so what you see is the authored geometry.
* ``initial_mode="field"`` + ``show_clusters`` — the client opens zoomed to the defined field frame
  (not the parcel envelope) and paints cluster regions, which the farm map otherwise never draws.

Authoring lives on the Delegate sub-tab (``plot_manager``). Rendered by ``renderGeospatialProjection``.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Any

from micyte.state_machine.portal_shell.shell_schemas import (
    WORKBENCH_UI_TOOL_ROUTE,
)

from ._archetype import resolve_tool_sandbox
from ._registry import register
from ._shared.utilities import as_text as _as_text
from .geospatial_projection_viewer import build_geospatial_payload, resolve_farm_scene

_SCHEMA = "mycite.v2.portal.workbench.tool.plot_overview.v1"
_DAY_PARAM = "plan_day"


def parse_day(text: str) -> date:
    """An ISO ``plan_day`` token → date, falling back to today on anything unparseable."""
    try:
        return date.fromisoformat((text or "").strip())
    except ValueError:
        return date.today()


class PlotOverviewViewer:
    tool_id = "plot_overview"
    label = "Plot Overview"
    summary = "The farm's defined fields, clusters and plots — read-only, zoomed to the field."
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
        # The PLAN tab's one viewing date. Geometry a contract depends on is retired, not deleted,
        # so the map shows whichever epoch this day falls in — a reshape only appears once the day
        # moves past the contracts that held the old plots.
        day = parse_day(_as_text((extra_query or {}).get(_DAY_PARAM)))
        return {
            "schema": _SCHEMA,
            "sandbox_id": resolve_tool_sandbox(sandbox_id, doc=doc),
            "document_id": _as_text(doc.document_id),
            "initial_mode": "field",
            "show_clusters": True,
            "day": day.isoformat(),
            "day_param": _DAY_PARAM,
            **build_geospatial_payload(doc, preview=False, as_of=day, authority=authority),
        }


register(PlotOverviewViewer())
