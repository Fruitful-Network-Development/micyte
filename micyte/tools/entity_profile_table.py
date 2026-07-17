"""Entity Profile Table — the NETWORK tab's right pane.

A grouped, filterable table of the network's entity profiles, grouped by entity CLASS
(the same 5-class colour buckets the map uses — farms / legal / administrative /
co-operatives / informal) with per-class collapse, facet filters (class, county/region,
profile type) and free-text search. Reuses the ``taxa_product_table`` client renderer via
the shared ``entity_profile_table`` container: groups = classes, rows = entities.

Pure builder over ``build_network_map_payload`` (so map + table never drift); read-only.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from micyte.state_machine.portal_shell.shell_schemas import WORKBENCH_UI_TOOL_ROUTE

from ._archetype import read_sandbox_catalog, resolve_tool_sandbox
from ._registry import register
from ._shared.utilities import as_text as _as_text
from .network_map_viewer import (
    _CLASS_ORDER,
    ENTITY_CLASS_STYLES,
    build_network_map_payload,
)

_TENANT_DEFAULT = "fnd"
_SCHEMA = "mycite.v2.portal.workbench.tool.entity_profile_table.v1"

# map SUBSTANCE glyph id (from the map payload's profile.icon) → served leaflet stem for
# the table's <img> icon (renderTypeIcon uses icon_ref, not the inline map symbol).
_GLYPH_TO_LEAFLET = {
    "farm": "mycite.farm", "grocery": "mycite.market", "store": "mycite.market",
    "farmers_market": "mycite.farmers_market", "farm_stand": "mycite.market_farm",
    "csa": "mycite.csa", "orchard": "mycite.orchard", "vineyard": "mycite.vineyard",
    "apiary": "mycite.apiary", "building": "mycite.legal_entity",
    "landmark": "mycite.administrative_entity", "community": "mycite.informal_entity",
    "coop": "mycite.cooperative",
}
_FACETS = ("color_class", "region", "category")


def _leaflet(glyph: str) -> str:
    stem = _GLYPH_TO_LEAFLET.get(glyph, "mycite.legal_entity")
    return f"0000-00-00.artifact-icon.{stem}"


def _notice(msg: str) -> dict[str, Any]:
    return {"schema": _SCHEMA, "container": "entity_profile_table", "notice": msg,
            "groups": [], "products": [], "facets": {}, "icon_url_prefix": "/assets/icons/"}


def build_entity_table_from_net(
    net: dict[str, Any], *, sandbox_id: str, detail_param: str = "",
    new_action: bool = False, entities: list[dict[str, Any]] | None = None,
    create_route: str = "",
) -> dict[str, Any]:
    """Project a ``build_network_map_payload`` result into the grouped entity-profile
    table payload (groups = entity classes, rows = profiles). Pure — no I/O — so the
    NETWORK-tab pane and the standalone Registrar tool render an identical table from a
    single catalog read.

    ``detail_param`` (a surface-query key), ``new_action``, ``entities`` and
    ``create_route`` are echoed onto the payload only when set, so the client can wire a
    row-click → open-detail and a "+ New profile" affordance. They default off, so the
    NETWORK tab's table payload is byte-for-byte unchanged.
    """
    if net.get("error"):
        return _notice(_as_text(net["error"]))
    profiles = net.get("profiles", [])

    rows: list[dict[str, Any]] = []
    class_counts: dict[str, int] = {}
    for p in profiles:
        cls = _as_text(p.get("color_class")) or "legal"
        class_counts[cls] = class_counts.get(cls, 0) + 1
        name = _as_text(p.get("name") or p.get("label"))
        region = _as_text(p.get("region"))
        category = _as_text(p.get("category_label") or p.get("category"))
        rows.append({
            "taxon": cls,                       # groups the row under its class
            "name": name,
            "subtitle": region,
            "slug": _as_text(p.get("label")).split(".", 1)[0],
            # unique per-profile identity (msn is NOT unique — one entity can host
            # several profiles) so a row-click opens exactly this profile's detail page.
            "label": _as_text(p.get("label")),
            "msn_node": _as_text(p.get("msn_node")),
            "icon_ref": _leaflet(_as_text(p.get("icon"))),
            "color_class": cls,
            "region": region,
            "category": category,
            "meta": [{"label": "", "value": category},
                     {"label": "", "value": _as_text(p.get("subtype"))},
                     {"label": "", "value": _as_text(p.get("dns"))}],
            "search": " ".join([name, region, category, cls,
                                _as_text(p.get("dns"))]).lower(),
        })

    groups = [
        {"addr": cls, "parent": "", "depth": 0,
         "label": ENTITY_CLASS_STYLES[cls]["label"], "scientific": "",
         "icon_ref": "", "product_count": class_counts.get(cls, 0)}
        for cls in _CLASS_ORDER if class_counts.get(cls, 0)
    ]
    facets = {
        "color_class": [ENTITY_CLASS_STYLES[c]["label"] for c in _CLASS_ORDER if class_counts.get(c)],
        "region": sorted({r["region"] for r in rows if r["region"]}),
        "category": sorted({r["category"] for r in rows if r["category"]}),
    }
    # The color_class facet <select> shows class LABELS, so carry the label on the row
    # for matching (the group key stays the class KEY via `taxon`, set above).
    for r in rows:
        r["color_class"] = ENTITY_CLASS_STYLES[r["color_class"]]["label"]
    rows.sort(key=lambda r: (r["color_class"], r["name"].lower()))
    payload: dict[str, Any] = {
        "schema": _SCHEMA,
        "container": "entity_profile_table",
        "sandbox_id": sandbox_id,
        "title": "Entity profiles",
        "count_label": f"{len(rows)} entities · {len(groups)} classes",
        "icon_url_prefix": "/assets/icons/",
        "groups": groups,
        "products": rows,
        "facets": facets,
        "facet_fields": list(_FACETS),
    }
    if detail_param:
        payload["detail_param"] = detail_param
    if new_action:
        payload["new_action"] = True
    if entities is not None:
        payload["entities"] = entities
    if create_route:
        payload["create_route"] = create_route
    return payload


class EntityProfileTable:
    """Grouped entity-profile table keyed by entity class (NETWORK tab right pane)."""

    tool_id = "entity_profile_table"
    label = "Entity Profiles"
    summary = "Network entity profiles grouped by class, with facet filters and search."
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
        section = _as_text((extra_query or {}).get("network_section")) or None
        net = build_network_map_payload(
            docs, sandbox_id=sandbox, section=section)
        return build_entity_table_from_net(net, sandbox_id=sandbox)


# Self-register on import.
register(EntityProfileTable())
