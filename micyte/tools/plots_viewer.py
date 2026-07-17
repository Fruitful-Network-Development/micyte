"""Plots viewer — a tabular inventory of the farm plots (Phase 3).

Phase 0 finding F2: there is no standalone ``plots`` doc; the plot geometry was migrated
INTO ``farm_profile`` as family-7 features (``7-(3+i)-1``, an lcl land-node ref + polygon).
This :class:`DatumDocTool` subclass lists those plot features as a ``record_table`` (the
complement to the farm_profile map view), resolving each plot's lcl node to its name.
"""

from __future__ import annotations

import re
from typing import Any

from micyte.core.datum_ops.datum_resolve import (
    Markers,
    cached_index,
    iter_marker_pairs,
)

from ._archetype import find_named_document
from ._contract import DatumDocTool
from ._registry import register
from ._shared.utilities import as_text as _as_text
from ._shared.utilities import row_head as _row_head
from ._shared.utilities import row_tail_label as _row_tail_label

_PLOT_FEAT_RE = re.compile(r"^7-(\d+)-1$")
_BOUNDARY_FEATURE_MAX = 3  # 7-3-1 is the property feature; plots are 7-4-1+


class PlotsViewer(DatumDocTool):
    tool_id = "plots"
    label = "Plots"
    summary = "Tabular inventory of farm plots (lcl node + polygon) migrated into farm_profile."
    schema = "mycite.v2.portal.workbench.tool.plots.v1"
    canonical_name = "farm_profile"
    container = "record_table"
    applies_to_archetype: tuple[str, ...] = ("hops_geospatial_filament",)

    def empty_body(self) -> dict[str, Any]:
        return {"container": self.container, "columns": [], "rows": [], "row_count": 0}

    def shape_payload(self, *, doc: Any, docs: list[Any], sandbox: str, datum_address: str) -> dict[str, Any]:
        lcl = cached_index(find_named_document(docs, sandbox=sandbox, name="lcl"))
        rows: list[dict[str, Any]] = []
        for row in getattr(doc, "rows", ()) or ():
            addr = _as_text(row.datum_address)
            m = _PLOT_FEAT_RE.match(addr)
            if not m or int(m.group(1)) <= _BOUNDARY_FEATURE_MAX:
                continue
            head = _row_head(row)
            node = next((_as_text(v) for marker, v in iter_marker_pairs(head) if marker == Markers.LCL_ID), "")
            polygon = next((_as_text(t) for t in head[1:] if _as_text(t).startswith(("5-", "6-"))), "")
            label = _row_tail_label(row)
            rows.append({
                "plot": label or node,
                "lcl_node": node,
                "node_name": lcl.resolve(node) or node,
                "polygon": polygon,
            })
        return {
            "container": self.container,
            "title": "Plots",
            "count_label": f"{len(rows)} plot{'' if len(rows) == 1 else 's'}",
            "columns": ["plot", "lcl_node", "node_name", "polygon"],
            "rows": rows,
            "row_count": len(rows),
            "empty_text": "No plots (geometry lives in the farm_profile map).",
        }


register(PlotsViewer())
