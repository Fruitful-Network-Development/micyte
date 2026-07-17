"""Planting Map — the PLAN > Planting map: the Plot overview plus contract creation.

The same read-only geometry the Plot tab shows (defined-only, as of ``plan_day``), with two things
layered on:

* **Occupancy** — every plot mid-planting on the viewing day carries the span occupying it, so the
  map answers "is this plot busy right now" directly. A contract on a cluster occupies every plot
  beneath it, which is why occupancy is computed per plot rather than per referent.
* **Contract creation** — clicking a cluster zooms to it and opens an anchored popup: scope the
  calendar to that cluster, or open the contract form. The form's product options are the batches
  with stock left, oldest first, so consuming the oldest inventory entry is the default.

Rendered by ``renderGeospatialProjection`` (same map), which reads the extra keys only when set.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from micyte.state_machine.portal_shell.shell_schemas import WORKBENCH_UI_TOOL_ROUTE

from ._archetype import find_named_document, read_sandbox_catalog, resolve_tool_sandbox
from ._consumption import available_batches, contract_spans, occupancy_on
from ._hops_dates import chrono_authority
from ._registry import register
from ._shared.utilities import as_text as _as_text
from .geospatial_projection_viewer import build_geospatial_payload
from .plot_overview_viewer import _DAY_PARAM, parse_day

_TENANT_DEFAULT = "fnd"
_SCHEMA = "mycite.v2.portal.workbench.tool.planting_map.v1"
_CLUSTER_PARAM = "plan_cluster"
_CONTRACT_ROUTE = "/portal/api/v2/agro/save_contract"


class PlantingMapViewer:
    """The Planting map: defined geometry as of plan_day + occupancy + contract creation."""

    tool_id = "planting_map"
    label = "Planting Map"
    summary = "The farm's plots on a given day, with what occupies them and a way to contract them."
    route = WORKBENCH_UI_TOOL_ROUTE
    # Embedded-only pane (composed into PLAN > Planting).
    applies_to_archetype: tuple[str, ...] = ()
    applies_to_source_kind: tuple[str, ...] = ()
    wants_surface_query = True

    def build_panel_payload(
        self, *, authority_db_file: Path | None, sandbox_id: str, document_id: str,
        datum_address: str, extra_query: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        eq = extra_query or {}
        docs, err = read_sandbox_catalog(authority_db_file, tenant_id=_TENANT_DEFAULT)
        if err:
            return {"schema": _SCHEMA, "error": err,
                    "feature_collection": {"type": "FeatureCollection", "features": []},
                    "feature_count": 0}
        sandbox = resolve_tool_sandbox(sandbox_id, docs=docs)
        if not sandbox:
            return {"schema": _SCHEMA, "error": "no sandbox specified",
                    "feature_collection": {"type": "FeatureCollection", "features": []},
                    "feature_count": 0}
        fp = find_named_document(docs, sandbox=sandbox, name="farm_profile")
        if fp is None:
            return {"schema": _SCHEMA, "error": "farm_profile document not found",
                    "feature_collection": {"type": "FeatureCollection", "features": []},
                    "feature_count": 0}

        day = parse_day(_as_text(eq.get(_DAY_PARAM)))
        authority = chrono_authority(find_named_document(docs, sandbox=sandbox, name="anchor"))
        geo = build_geospatial_payload(fp, preview=False, as_of=day, authority=authority)

        plot_nodes = {_as_text(f["properties"].get("lcl_node"))
                      for f in geo["feature_collection"]["features"]
                      if f["properties"].get("kind") == "plot" and f["properties"].get("lcl_node")}
        busy = occupancy_on(contract_spans(docs, sandbox), day, plot_nodes)
        # COPY-ON-WRITE. build_geospatial_payload's result is memoised and SHARED, so annotating a
        # feature in place would poison every other reader of that projection (and persist across
        # requests). Only the occupied features are rebuilt — usually a handful out of thousands —
        # and the rest are passed through by reference.
        feats = []
        for f in geo["feature_collection"]["features"]:
            p = f.get("properties", {})
            span = busy.get(_as_text(p.get("lcl_node"))) if p.get("kind") == "plot" else None
            if span is None:
                feats.append(f)
                continue
            feats.append({**f, "properties": {**p, "occupied_by": {
                "product_name": span["product_name"], "batch": span["batch"],
                "start": span["start"].isoformat(), "end": span["end"].isoformat(),
                "contract_addr": span["datum_address"],
            }}})
        geo = {**geo, "feature_collection": {**geo["feature_collection"], "features": feats}}

        batches = available_batches(docs, sandbox)
        return {
            "schema": _SCHEMA,
            "sandbox_id": sandbox,
            "document_id": _as_text(getattr(fp, "document_id", "")),
            "initial_mode": "field",
            "show_clusters": True,
            "day": day.isoformat(),
            "day_param": _DAY_PARAM,
            "cluster_param": _CLUSTER_PARAM,
            "cluster_focus": _as_text(eq.get(_CLUSTER_PARAM)),
            # Turns the map into the contract-creation surface: plots become selectable and a
            # cluster click opens the anchored popup.
            "selectable": True,
            "contract_popup": True,
            "contract_route": _CONTRACT_ROUTE,
            "batches": batches,
            "occupied_count": len(busy),
            **geo,
        }


register(PlantingMapViewer())
