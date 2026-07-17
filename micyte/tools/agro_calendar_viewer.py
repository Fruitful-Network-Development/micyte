"""Agro Calendar — the NETWORK tab's bottom subtool.

A calendar of the network's cyclical events with two views: **Calendar** (a month grid,
weekday-cadence events marked on their day cells, seasonal events shown as in-season chips)
and **Week** (a day × hour grid placing in-season weekly events on their weekday and hour).
Selecting an event opens a detail view of the event and its host entity (with a ← back
arrow); events can be filtered by county and by event type.

Pure builder over ``build_network_map_payload`` (events + host→region join), so the map,
the entity table and the calendar all read one classification; read-only, no MOS writes.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from micyte.state_machine.portal_shell.shell_schemas import WORKBENCH_UI_TOOL_ROUTE

from ._archetype import read_sandbox_catalog, resolve_tool_sandbox
from ._registry import register
from ._shared.utilities import as_text as _as_text
from .network_map_viewer import ENTITY_CLASS_STYLES, build_network_map_payload

_TENANT_DEFAULT = "fnd"
_SCHEMA = "mycite.v2.portal.workbench.tool.agro_calendar.v1"
_EVENT_TYPE_LABELS = {"market": "Markets", "csa": "CSAs", "stand": "Farm stands",
                      "store": "Stores", "other": "Other"}


def _notice(msg: str) -> dict[str, Any]:
    return {"schema": _SCHEMA, "container": "agro_calendar", "notice": msg,
            "events": [], "counties": [], "event_types": [], "styles": ENTITY_CLASS_STYLES}


class AgroCalendarViewer:
    """Month + week calendar of network events (NETWORK tab bottom subtool)."""

    tool_id = "agro_calendar"
    label = "Calendar"
    summary = "Month and week calendar of network events, filterable by county and type."
    route = WORKBENCH_UI_TOOL_ROUTE
    # Embedded-only pane (composed into the NETWORK tab) — out of the menubar palette.
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
        sandbox = resolve_tool_sandbox(sandbox_id, docs=docs)
        if not sandbox:
            return _notice("no sandbox specified")
        net = build_network_map_payload(docs, sandbox_id=sandbox)
        if net.get("error"):
            return _notice(_as_text(net["error"]))

        # host msn node → (county_node, county_label) from the entity profiles. The
        # calendar filters/pages by COUNTY (not the deeper municipality region).
        county_by_host: dict[str, tuple[str, str]] = {}
        for p in net.get("profiles", []):
            node = _as_text(p.get("msn_node"))
            if node and node not in county_by_host and _as_text(p.get("county")):
                county_by_host[node] = (_as_text(p.get("county_node")), _as_text(p.get("county")))

        events = []
        counties: dict[str, str] = {}
        types: set[str] = set()
        for e in net.get("events", []):
            cn, cl = county_by_host.get(_as_text(e.get("host_node")), ("", ""))
            if cn:
                counties[cn] = cl
            types.add(_as_text(e.get("event_group")) or "other")
            # region_node kept as the county node so existing filters keep working; venue +
            # host_node carry through for the calendar→map "Locate on map" cross-link.
            events.append({**e, "region_node": cn, "region": cl,
                           "county_node": cn, "county": cl})

        return {
            "schema": _SCHEMA,
            "container": "agro_calendar",
            "sandbox_id": sandbox,
            "title": "Calendar",
            "event_count": len(events),
            "events": events,
            "counties": [{"node": n, "label": lbl}
                         for n, lbl in sorted(counties.items(), key=lambda kv: kv[1])],
            "event_types": [{"key": k, "label": _EVENT_TYPE_LABELS.get(k, k.title())}
                            for k in sorted(types)],
            "styles": ENTITY_CLASS_STYLES,
        }


# Self-register on import.
register(AgroCalendarViewer())
