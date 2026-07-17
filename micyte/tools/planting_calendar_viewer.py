"""Planting Calendar — the PLAN > Planting navigator: PLOTS (rows) x DAYS (columns).

A swimlane calendar, not a month grid. Each row is a plot; each contract draws a bar spanning the
days it occupies that plot — from its own day through ``+ gestation``, the product-profile field
that until now was stored on every product and read by nothing. A contract written against a
CLUSTER draws on every plot beneath it (``plots_of_referent``), which is what lets one row model
serve both referent kinds.

Distinct from ``agro_calendar`` (the NETWORK tab's month/week grid of public recurring events) —
different data, different axes; they share nothing but the word calendar.

Row selection matters: a farm can carry thousands of plots (trapp has 3650), so rendering one row
each would be unusable. Occupied plots always appear; free plots fill the remainder up to a cap and
the payload reports exactly what was withheld (``hidden_row_count``) rather than truncating quietly.
"""

from __future__ import annotations

from datetime import timedelta
from pathlib import Path
from typing import Any

from micyte.state_machine.portal_shell.shell_schemas import WORKBENCH_UI_TOOL_ROUTE

from ._archetype import find_named_document, read_sandbox_catalog, resolve_tool_sandbox
from ._consumption import contract_spans, plots_of_referent
from ._hops_dates import chrono_authority
from ._registry import register
from ._shared.utilities import as_text as _as_text
from .geospatial_projection_viewer import build_geospatial_payload
from .plot_overview_viewer import parse_day

_TENANT_DEFAULT = "fnd"
_SCHEMA = "mycite.v2.portal.workbench.tool.planting_calendar.v1"
_DAY_PARAM = "plan_day"
_SPAN_PARAM = "plan_span"
_CLUSTER_PARAM = "plan_cluster"
# Day bands the client can switch between; the window always starts a little before plan_day so a
# planting already under way is visible rather than clipped off the left edge.
_SPANS = {"14": 14, "35": 35, "91": 91}
_DEFAULT_SPAN = "35"
_LEAD_DAYS = 7
# Free (uncontracted) plots shown alongside the occupied ones. Enough to see spare capacity next to
# what is committed, small enough to stay legible at ~3650 plots.
_FREE_ROW_CAP = 40
# Stable per-product bar colours (index by a hash of the product node — same product, same colour
# across renders, no palette state to keep).
_BAR_COLORS = ("#2ea043", "#1f6feb", "#8957e5", "#d69e2e", "#bc4c00", "#0f7c8a", "#a32023", "#6e7781")


def _notice(msg: str) -> dict[str, Any]:
    return {"schema": _SCHEMA, "container": "planting_calendar", "notice": msg,
            "rows": [], "bars": [], "days": []}


def _color_for(node: str) -> str:
    return _BAR_COLORS[sum(ord(c) for c in node) % len(_BAR_COLORS)] if node else _BAR_COLORS[-1]


class PlantingCalendarViewer:
    """Contracts as dated bars over a plot-per-row swimlane grid."""

    tool_id = "planting_calendar"
    label = "Planting Calendar"
    summary = "Contracts as bars across days, one row per plot."
    route = WORKBENCH_UI_TOOL_ROUTE
    # Embedded-only pane (composed into the PLAN > Planting sub-tab).
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
            return _notice(err)
        sandbox = resolve_tool_sandbox(sandbox_id, docs=docs)
        if not sandbox:
            return _notice("no sandbox specified")

        fp = find_named_document(docs, sandbox=sandbox, name="farm_profile")
        if fp is None:
            return _notice("farm_profile document not found")
        day = parse_day(_as_text(eq.get(_DAY_PARAM)))
        span_key = _as_text(eq.get(_SPAN_PARAM)) or _DEFAULT_SPAN
        span = _SPANS.get(span_key, _SPANS[_DEFAULT_SPAN])
        focus = _as_text(eq.get(_CLUSTER_PARAM))

        # Rows come from the geometry IN FORCE on the viewing day — the same as_of the map uses, so
        # the two panes always agree about which plots exist.
        authority = chrono_authority(find_named_document(docs, sandbox=sandbox, name="anchor"))
        geo = build_geospatial_payload(fp, preview=False, as_of=day, authority=authority)
        plots: dict[str, dict[str, Any]] = {}
        cluster_label: dict[str, str] = {}
        for f in geo["feature_collection"]["features"]:
            p = f.get("properties", {})
            node = _as_text(p.get("lcl_node"))
            if not node:
                continue
            if p.get("kind") == "cluster":
                cluster_label[node] = _as_text(p.get("label"))
            elif p.get("kind") == "plot":
                plots[node] = {"plot_node": node, "label": _as_text(p.get("label")) or node}
        plot_nodes = set(plots)

        start = day - timedelta(days=_LEAD_DAYS)
        end = start + timedelta(days=span)
        spans = contract_spans(docs, sandbox)

        # Expand each contract onto the plots it occupies; a cluster contract lands on every plot
        # beneath it. Only spans overlapping the window draw.
        bars: list[dict[str, Any]] = []
        occupied: set[str] = set()
        for s in spans:
            covered = plots_of_referent(s["referent_node"], plot_nodes)
            occupied |= covered
            if not (s["start"] < end and s["end"] > start):
                continue
            for node in sorted(covered):
                bars.append({
                    "plot_node": node,
                    "contract_addr": s["datum_address"],
                    "start": s["start"].isoformat(),
                    "end": s["end"].isoformat(),
                    "product_name": s["product_name"],
                    "product_node": s["product_node"],
                    "batch": s["batch"],
                    "referent": s["referent"],
                    "gestation_days": s["gestation_days"],
                    "color": _color_for(s["product_node"]),
                    "whole_cluster": s["referent_node"] != node,
                })

        # Row selection. A focused cluster shows exactly its plots; otherwise the occupied plots
        # always appear and free plots fill up to the cap.
        if focus:
            chosen = sorted(plots_of_referent(focus, plot_nodes))
            hidden = 0
        else:
            in_window = {b["plot_node"] for b in bars}
            free = sorted(plot_nodes - in_window)
            chosen = sorted(in_window) + free[:_FREE_ROW_CAP]
            hidden = max(0, len(free) - _FREE_ROW_CAP)

        rows = [{**plots[n], "occupied": n in occupied,
                 "cluster_node": _parent_cluster(n, cluster_label)}
                for n in chosen if n in plots]
        shown = {r["plot_node"] for r in rows}
        bars = [b for b in bars if b["plot_node"] in shown]

        days = [(start + timedelta(days=i)).isoformat() for i in range(span)]
        data_range = ({"start": min(s["start"] for s in spans).isoformat(),
                       "end": max(s["end"] for s in spans).isoformat()} if spans else {})
        return {
            "schema": _SCHEMA,
            "container": "planting_calendar",
            "sandbox_id": sandbox,
            "title": "Planting",
            "day": day.isoformat(),
            "days": days,
            "span": str(span_key if span_key in _SPANS else _DEFAULT_SPAN),
            "span_options": [{"value": k, "label": f"{v} days"} for k, v in _SPANS.items()],
            "rows": rows,
            "bars": bars,
            "row_count": len(rows),
            "plot_count": len(plots),
            "hidden_row_count": hidden,
            "contract_count": len(spans),
            "in_window_count": len({b["contract_addr"] for b in bars}),
            "data_range": data_range,
            "cluster_focus": focus,
            "cluster_label": cluster_label.get(focus, ""),
            "day_param": _DAY_PARAM,
            "span_param": _SPAN_PARAM,
            "cluster_param": _CLUSTER_PARAM,
            "empty_text": ("No plots defined on this day — draw a cluster on the Delegate tab."
                           if not plots else ""),
        }


def _parent_cluster(plot_node: str, cluster_label: dict[str, str]) -> str:
    """The cluster a plot sits under, when there is one.

    Plots minted by save_cluster live under their cluster; the legacy migrated plots sit in a flat
    ``1-2-4-*`` container with no cluster at all, so this is genuinely optional.
    """
    for node in cluster_label:
        if plot_node.startswith(node + "-"):
            return node
    return ""


register(PlantingCalendarViewer())
