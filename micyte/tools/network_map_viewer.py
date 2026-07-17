"""Network Map — the agronomics NETWORK tab: resources published by mycelium_network.

This is the CONSUMER side of the mycelium_network source-binary pipeline. mycelium_network
*produces* a ``network_sources`` manifest (see ``scripts/produce_mycelium_network_sources.py``)
— the index of resources it contributes to the network, each bound to its produced MSS
source-binary identity (``rf.3-1-12``) and a resource kind (``rf.3-1-14``). This tool reads
that manifest cross-sandbox (via the shared tenant catalog) and assembles the NETWORK map v1
payload:

* ``boundary`` resources → polygon backdrop features (as before);
* the ``profiles`` resource (``fnd_ag_profiles``) → point features: one per (entity ×
  ag-profile type), category-styled with the FND network legend, region-tagged from the
  ``administrative`` gazetteer labels, joined by the entity msn node;
* the ``events`` resource (the ``calendar`` doc) → the upcoming-events list. Calendar
  rows are ic-hops cyclical: each ``open_hours`` row carries a stamp per recurrence in
  exactly ONE cyclical structure (hc hops ``day-hh-mm`` weekly, or qc hops
  ``day[-hh-mm]`` seasonal/dated) plus a (time-unit, magnitude) span; ``off_season``
  rows (qc day stamp + day span, label ``<parent>.off_season_N``) are that event's
  closures — cadence is derived from WHICH structure the stamp is in, and windows
  from the closure complement. Joined to hosts by msn node.

Rendered by the ``network_map`` tool renderer (filter bar + SVG map + events list).
A manifest row with no ``rf.3-1-14`` kind is treated as ``boundary`` (back-compat with a
manifest produced before the kind marker existed).
"""
from __future__ import annotations

import json
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

from micyte.core.document_naming import parse_canonical_document_id
from micyte.core.structures.hops import (
    current_open_window,
    cycle_start_year_of,
    date_of_qc_day,
    decode_hops_coordinate_token,
    next_hc_occurrences,
    parse_ic_stamp,
)
from micyte.core.structures.hops.cyclical import LCL_HC, LCL_QC
from micyte.state_machine.portal_shell.shell_schemas import WORKBENCH_UI_TOOL_ROUTE

from ._archetype import read_sandbox_catalog
from ._registry import register
from ._shared.utilities import as_text as _as_text
from ._shared.utilities import row_head as _row_head

_TENANT_DEFAULT = "fnd"
_SCHEMA = "mycite.v2.portal.workbench.tool.network_map.v1"
SOURCE_SANDBOX = "registrar"
MANIFEST_NAME = "network_sources"
_COORD, _NODE, _NAME = "rf.3-1-1", "rf.3-1-2", "rf.3-1-3"
_UTC_M, _SB, _LCL, _KIND = "rf.3-1-6", "rf.3-1-12", "rf.3-1-13", "rf.3-1-14"
_STAMP, _SPAN = "rf.3-1-15", "rf.3-1-16"  # ic-hops cyclical stamp / tiu span magnitude
_KIND_OPEN_HOURS, _KIND_OFF_SEASON = "1-3-8-1", "1-3-8-2"

# Entity-class colour palette (the FND brand mark). The operator's rule: a marker's
# COLOUR encodes WHO hosts / supports / drives that location — its ENTITY CLASS — while
# the glyph ICON encodes the SUBSTANCE (what it markets: farmers market / grocery / farm
# stand / farm …). So a farmers market run by the city is gold (administrative); the same
# venue run by a church is purple (informal); Haymaker's (a legal entity) is red.
ENTITY_CLASS_STYLES: dict[str, dict[str, str]] = {
    "legal":          {"color": "#A32023", "label": "Legal entities"},
    "administrative": {"color": "#D89C1F", "label": "Administrative"},
    "farm":           {"color": "#115F45", "label": "Farms"},
    "cooperative":    {"color": "#1D3A65", "label": "Co-operatives"},
    "informal":       {"color": "#3F1F4A", "label": "Informal"},
}
_CLASS_ORDER = ("farm", "legal", "administrative", "cooperative", "informal")

# ag-profile category → human label (subtype context; NOT a colour source anymore).
# The four market-facing (Operation) types are CSA / farmers market / farm stand / market;
# "food hub" is NOT a distinct type — a grocery/hub is just a "market" (1-2-4).
_CATEGORY_LABEL = {
    "producer": "Producer", "farmers_market": "Farmers market", "csa": "CSA",
    "farm_stand": "Farm stand", "market": "Market", "seed_supplier": "Seed supplier",
    "organization": "Organization", "administrative": "Administrative",
}
# ag-profile category → SUBSTANCE glyph (nm-ic-*): what the location markets.
_SUBSTANCE_BY_CATEGORY = {
    "producer": "farm", "farmers_market": "farmers_market", "csa": "csa",
    "farm_stand": "farm_stand", "market": "grocery", "seed_supplier": "store",
    "organization": "building", "administrative": "landmark",
}
# producer subtype (lcl 1-2-1-N) → a more specific substance glyph.
_PRODUCER_SUBTYPE_ICON = {
    "1-2-1-2": "orchard", "1-2-1-4": "farm_stand", "1-2-1-5": "apiary", "1-2-1-6": "vineyard",
}
# event class → substance glyph (the venue the recurrence markets).
EVENT_CLASS_ICON = {"1-3-1": "farmers_market", "1-3-2": "csa", "1-3-3": "farm_stand",
                    "1-3-4": "grocery", "1-3-5": "basket", "1-3-6": "ticket"}
# event class → the events-list toggle group (the card viewer's type filter).
EVENT_CLASS_GROUP = {"1-3-1": "market", "1-3-2": "csa", "1-3-3": "stand", "1-3-4": "store"}
# lcl ag_profile branch → ag category (longest prefix wins). 1-2-2 = farmers market,
# 1-2-4 = market (a grocery / "food hub" is just a market — no separate category).
_CATEGORY_BY_LCL = (
    ("1-2-1", "producer"), ("1-2-2", "farmers_market"), ("1-2-3", "csa"), ("1-2-4", "market"),
    ("1-2-5", "seed_supplier"), ("1-2-6", "organization"), ("1-2-7", "administrative"),
)

# NETWORK sub-tab sectioning (operator taxonomy). Every entity profile falls in exactly
# ONE section so the NETWORK tab's Operation / Peer / Logistic sub-tabs partition the
# map + table with no overlap and no drop:
#   operation — public food-access points the community patronizes, exactly the four
#     market-facing types: CSAs, farmers markets, markets (groceries), farm stands. Decided
#     by market-facing SUBSTANCE (category / glyph), NOT entity class — an administration- or
#     co-op-run farmers market still belongs here (its colour stays who-drives-it). Producers
#     (farms) are NOT shown here unless they market as a farm stand (then they ARE a stand).
#   logistic  — upstream input suppliers (seed & input suppliers).
#   peer      — everything else: other farms (producers), organizations, administrative
#     bodies, co-ops and informal entities (the "who" that supports operations).
NETWORK_SECTIONS = ("operation", "peer", "logistic")
_OPERATION_CATEGORIES = frozenset({"csa", "farmers_market", "market", "farm_stand"})
_LOGISTIC_CATEGORIES = frozenset({"seed_supplier"})


def _section_for(category: str, icon: str) -> str:
    """The NETWORK sub-tab a profile belongs to. ``icon`` is the FINAL substance glyph
    (evaluate after the farm-stand override) so a producer that markets as a farm stand
    is sectioned as an operation, not a peer."""
    if category in _LOGISTIC_CATEGORIES:
        return "logistic"
    if category in _OPERATION_CATEGORIES or icon == "farm_stand":
        return "operation"
    return "peer"
# entity_kind_of() nature → the 5-class colour bucket. A food hub / store that is a
# legal entity (purple_brown_farm_store) colours as legal (red) but keeps a store glyph.
_KIND_TO_CLASS = {"farm": "farm", "legal": "legal", "hub": "legal",
                  "administrative": "administrative", "community": "informal",
                  "cooperative": "cooperative"}

# Operator-curated host-class overrides (same pattern as rectify_fnd_profile_coordinates):
# a farmers market is coloured by WHO drives it, which is not always the market's own
# standalone entity class. Keyed by the owner slug (label prefix). Extend as hosts are
# confirmed; the default falls through to the entity's own class.
_HOST_CLASS_OVERRIDE: dict[str, str] = {
    "hudson_farmers_market": "administrative",   # City of Hudson–run
    "oberlin_farmers_market": "informal",        # community/church-run
}


def _owner_slug(label: str) -> str:
    return _as_text(label).split(".", 1)[0]


def _substance_for_profile(lcl_node: str) -> str:
    for pref, gid in _PRODUCER_SUBTYPE_ICON.items():
        if lcl_node == pref or lcl_node.startswith(pref + "-"):
            return gid
    return _SUBSTANCE_BY_CATEGORY.get(_category_for(lcl_node), "building")


def _doc_name(doc: Any) -> str:
    try:
        return parse_canonical_document_id(_as_text(doc.document_id)).name
    except Exception:
        return _as_text(getattr(doc, "canonical_name", ""))


def _pairs(head: list[Any]) -> dict[str, list[str]]:
    out: dict[str, list[str]] = {}
    i = 1
    while i < len(head) - 1:
        out.setdefault(_as_text(head[i]), []).append(_as_text(head[i + 1]))
        i += 2
    return out


def _decode_bits(value: str) -> str:
    text = _as_text(value)
    if not text or len(text) % 8 or set(text) - {"0", "1"}:
        return text
    chars = []
    for i in range(0, len(text), 8):
        c = int(text[i:i + 8], 2)
        if c == 0:
            break
        if 32 <= c < 127:
            chars.append(chr(c))
    return "".join(chars)


def _row_label(r: Any) -> str:
    raw = getattr(r, "raw", None)
    if isinstance(raw, list) and len(raw) > 1 and isinstance(raw[-1], list) and raw[-1]:
        return _as_text(raw[-1][0])
    return ""


def _manifest_resources(manifest: Any) -> list[dict[str, str]]:
    """Parse the network_sources manifest rows into resource descriptors."""
    out: list[dict[str, str]] = []
    for r in getattr(manifest, "rows", ()) or ():
        pairs = _pairs(_row_head(r))
        name = pairs.get(_NAME, [""])[0]
        node = pairs.get(_NODE, [""])[0]
        if not name or not node:
            continue  # skip the manifest's own identity row (no geo node)
        out.append({"name": name, "node": node,
                    "source_binary": pairs.get(_SB, [""])[0],
                    "kind": pairs.get(_KIND, ["boundary"])[0] or "boundary"})
    return out


def _outer_rings(reference_geojson: Any) -> list[list]:
    """Every polygon outer ring ([lon,lat] lists) in a reference_geojson (FC / Feature /
    Polygon / MultiPolygon). MultiPolygons are flattened to one ring per polygon so each maps
    to a GeoJSON Polygon the renderer can draw (it reads geometry.coordinates[0])."""
    if isinstance(reference_geojson, str):
        try:
            reference_geojson = json.loads(reference_geojson)
        except Exception:
            return []
    polygons: list[list] = []

    def collect(obj: Any) -> None:
        if not isinstance(obj, dict):
            return
        kind = obj.get("type")
        if kind == "FeatureCollection":
            for feat in obj.get("features") or []:
                collect(feat)
        elif kind == "Feature":
            collect(obj.get("geometry"))
        elif kind == "Polygon":
            polygons.append(obj.get("coordinates") or [])
        elif kind == "MultiPolygon":
            for poly in obj.get("coordinates") or []:
                polygons.append(poly)

    collect(reference_geojson)
    rings: list[list] = []
    for poly in polygons:  # poly == [outer_ring, hole1, ...]
        if poly and isinstance(poly[0], list):
            rings.append(poly[0])
    return rings


def _error(message: str) -> dict[str, Any]:
    return {"schema": _SCHEMA, "tool_id": "network_map", "error": message,
            "feature_collection": {"type": "FeatureCollection", "features": []},
            "feature_count": 0, "profiles": [], "events": []}


def _lonlat(coord_token: str) -> tuple[float, float] | None:
    decoded = decode_hops_coordinate_token(_as_text(coord_token))
    if not isinstance(decoded, dict):
        return None
    lon = ((decoded.get("longitude") or {}).get("value"))
    lat = ((decoded.get("latitude") or {}).get("value"))
    if lon is None or lat is None:
        return None
    return float(lon), float(lat)


def _category_for(lcl_node: str) -> str:
    for prefix, key in _CATEGORY_BY_LCL:
        if lcl_node == prefix or lcl_node.startswith(prefix + "-"):
            return key
    return "organization"


def _time_range_text(hour: int, minute: int, span_minutes: int) -> str:
    """``HH:MM–HH:MM`` from an open stamp time + minute span (clamped to the day)."""
    start_m = hour * 60 + minute
    end_m = min(start_m + max(0, int(span_minutes)), 23 * 60 + 59)
    return f"{hour:02d}:{minute:02d}–{end_m // 60:02d}:{end_m % 60:02d}"


def build_network_map_payload(docs: list[Any], *, sandbox_id: str,
                              now: datetime | None = None,
                              section: str | None = None) -> dict[str, Any]:
    """Pure: assemble the NETWORK map v1 payload from the mycelium_network manifest.
    Separated from the db read so it is unit-testable.

    ``section`` (one of :data:`NETWORK_SECTIONS`) narrows the payload to a single NETWORK
    sub-tab: profiles + events are filtered to that section, and all derived facets
    (csa_widgets, region / county / class / type counts, header counts) reflect the slice."""
    now = now or datetime.now(UTC)
    by_name: dict[str, Any] = {}
    for doc in docs:
        if _as_text(getattr(doc, "document_id", "")).find(f".{SOURCE_SANDBOX}.") == -1:
            continue
        by_name[_doc_name(doc)] = doc
    manifest = by_name.get(MANIFEST_NAME)
    if manifest is None:
        return _error(f"{SOURCE_SANDBOX} source-binary manifest ({MANIFEST_NAME}) not found")
    resources = _manifest_resources(manifest)

    # gazetteer labels (administrative doc) → region tags for entity nodes
    node_label: dict[str, str] = {}
    admin = by_name.get("administrative")
    for r in (getattr(admin, "rows", ()) or ()) if admin is not None else ():
        pairs = _pairs(_row_head(r))
        node = pairs.get(_NODE, [""])[0]
        if node:
            node_label.setdefault(node, _decode_bits(pairs.get(_NAME, [_row_label(r)])[0]))

    def region_of(entity_node: str) -> tuple[str, str]:
        segs = entity_node.split("-")
        for depth in range(min(len(segs), 7), 4, -1):  # muni (7) down to county (5)
            prefix = "-".join(segs[:depth])
            if prefix in node_label:
                return prefix, node_label[prefix]
        return "", ""

    def county_of(entity_node: str) -> tuple[str, str]:
        """The COUNTY (depth-5 gazetteer node) an entity sits under — distinct from
        region_of, which returns the deepest match (may be a municipality). County is
        the unit the map/calendar filter and page by."""
        segs = entity_node.split("-")
        if len(segs) >= 5:
            prefix = "-".join(segs[:5])
            if prefix in node_label:
                return prefix, node_label[prefix]
        return "", ""

    # entity names (legal + administrative entities) → host display for events, plus the
    # host COLOR-CLASS inputs: administrative nodes, informal entity classes (lcl 1-1-2*),
    # and each host's ag-profile categories (fnd_ag_profiles).
    entity_name: dict[str, str] = {}
    admin_nodes: set[str] = set()
    entity_class: dict[str, str] = {}
    for doc_name in ("legal_entity", "administrative_entity"):
        d = by_name.get(doc_name)
        for r in (getattr(d, "rows", ()) or ()) if d is not None else ():
            pairs = _pairs(_row_head(r))
            node = pairs.get(_NODE, [""])[0]
            if not node:
                continue
            entity_name.setdefault(node, _decode_bits(pairs.get(_NAME, [_row_label(r)])[0]))
            if doc_name == "administrative_entity":
                admin_nodes.add(node)
            elif _LCL in pairs:
                entity_class.setdefault(node, pairs[_LCL][0])
    host_profile_cats: dict[str, list[str]] = {}
    profiles_doc = by_name.get("fnd_ag_profiles")
    for r in (getattr(profiles_doc, "rows", ()) or ()) if profiles_doc is not None else ():
        pairs = _pairs(_row_head(r))
        node, lcl_node = pairs.get(_NODE, [""])[0], pairs.get(_LCL, [""])[0]
        if node and lcl_node:
            host_profile_cats.setdefault(node, []).append(_category_for(lcl_node))

    def entity_kind_of(node: str) -> str:
        """The marker GLYPH class: administrative / community / cooperative by entity
        class; hub when the entity IS a market/grocery storefront (1-2-4 — fresh_fork,
        purple_brown_farm_store); farm when the entity works the land (producer or
        csa profile); else a legal organization."""
        if node in admin_nodes:
            return "administrative"
        cls = entity_class.get(node, "")
        if cls.startswith("1-1-2"):
            return "community"
        if cls.startswith("1-1-1-4"):
            return "cooperative"
        cats = host_profile_cats.get(node, [])
        if "market" in cats:
            return "hub"
        if "producer" in cats or "csa" in cats:
            return "farm"
        return "legal"

    def color_class(node: str, label: str = "") -> str:
        """The 5-class colour bucket a marker wears — WHO drives the location.
        An operator-curated override (keyed by owner slug) wins where a market's
        driving host differs from its own standalone entity class."""
        override = _HOST_CLASS_OVERRIDE.get(_owner_slug(label))
        return override or _KIND_TO_CLASS.get(entity_kind_of(node), "legal")

    # lcl labels for profile subtypes / event classes / cadence
    lcl_label: dict[str, str] = {}
    lcl_doc = by_name.get("lcl")
    for r in (getattr(lcl_doc, "rows", ()) or ()) if lcl_doc is not None else ():
        pairs = _pairs(_row_head(r))
        node = pairs.get(_LCL, [""])[0]
        if node:
            lcl_label[node] = _row_label(r)

    features: list[dict[str, Any]] = []
    profiles: list[dict[str, Any]] = []
    events: list[dict[str, Any]] = []
    rendered = 0
    for res in resources:
        doc = by_name.get(res["name"])
        if doc is None:
            continue
        if res["kind"] == "boundary":
            rings = _outer_rings((getattr(doc, "document_metadata", {}) or {}).get("reference_geojson"))
            if not rings:
                continue
            rendered += 1
            level = "county" if len(res["name"].split("-")) == 5 else "community"
            for j, ring in enumerate(rings):
                clean = [[c[0], c[1]] for c in ring if isinstance(c, (list, tuple)) and len(c) >= 2]
                if len(clean) < 3:
                    continue
                if clean[0] != clean[-1]:
                    clean.append(clean[0])
                features.append({
                    "type": "Feature",
                    "id": f"{res['name']}:{j}",
                    "geometry": {"type": "Polygon", "coordinates": [clean]},
                    "properties": {"kind": "parcel", "level": level,
                                   "label": node_label.get(res["name"], res["name"]),
                                   # gazetteer node (county boundaries are depth-5) so the
                                   # client can bounds-fit the view to selected counties.
                                   "node": res["name"],
                                   "region_node": res["name"] if level == "county" else "",
                                   "source_binary": res["source_binary"]},
                })
        elif res["kind"] == "profiles":
            rendered += 1
            for r in getattr(doc, "rows", ()) or ():
                pairs = _pairs(_row_head(r))
                node = pairs.get(_NODE, [""])[0]
                lcl_node = pairs.get(_LCL, [""])[0]
                lonlat = _lonlat(pairs.get(_COORD, [""])[0])
                if not node or not lcl_node or lonlat is None:
                    continue
                category = _category_for(lcl_node)
                region_node, region_label = region_of(node)
                county_node, county_label = county_of(node)
                kind = entity_kind_of(node)
                cls = color_class(node, _row_label(r))  # WHO drives it → colour
                cls_style = ENTITY_CLASS_STYLES.get(cls, ENTITY_CLASS_STYLES["legal"])
                profiles.append({
                    "label": _row_label(r),
                    "name": pairs.get(_NAME, [_row_label(r)])[0],
                    "msn_node": node,
                    # unique row address within fnd_ag_profiles — lets the registrar
                    # tool address this exact profile for detail + edit (msn is NOT unique).
                    "datum_address": _as_text(getattr(r, "datum_address", "")),
                    "lcl_node": lcl_node,
                    "category": category,
                    "category_label": _CATEGORY_LABEL.get(category, category),
                    "color_class": cls,
                    "color_class_label": cls_style["label"],
                    "subtype": lcl_label.get(lcl_node, ""),
                    "entity_kind": kind,
                    "region_node": region_node,
                    "region": region_label,
                    "county_node": county_node,
                    "county": county_label,
                    "lon": lonlat[0], "lat": lonlat[1],
                    "color": cls_style["color"],      # brand class colour
                    "icon": _substance_for_profile(lcl_node),  # WHAT it markets → glyph
                    "dns": pairs.get("rf.3-1-9", [""])[0],
                })
        elif res["kind"] == "events":
            rendered += 1
            today = now.date()
            # pass 1 — parse every calendar row; off_season rows become their
            # parent event's closure runs (qc day stamp + day-unit span)
            open_rows: list[dict[str, Any]] = []
            closures_by_parent: dict[str, list[tuple[int, int]]] = {}
            for r in getattr(doc, "rows", ()) or ():
                if not _as_text(getattr(r, "datum_address", "")).startswith("4-1-"):
                    continue
                pairs = _pairs(_row_head(r))
                node = pairs.get(_NODE, [""])[0]
                lcls = pairs.get(_LCL, [])
                stamps = pairs.get(_STAMP, [])
                if not node or not lcls:
                    continue
                kind = next((c for c in lcls if c.startswith("1-3-8")), "")
                try:
                    span = int(pairs.get(_SPAN, ["0"])[0] or 0)
                except ValueError:
                    span = 0
                label = _row_label(r)
                if kind == _KIND_OFF_SEASON:
                    if not stamps:
                        continue
                    try:
                        day, _h, _m = parse_ic_stamp(stamps[0], structure=LCL_QC)
                    except ValueError:
                        continue
                    parent = label.rsplit(".off_season", 1)[0]
                    closures_by_parent.setdefault(parent, []).append((day, max(1, span)))
                    continue
                open_rows.append({
                    "pairs": pairs, "label": label, "node": node, "span": span,
                    "op_class": next((c for c in lcls
                                      if c.startswith("1-3-") and not c.startswith("1-3-8")), ""),
                    "structure": next((c for c in lcls if c.startswith("1-5-")), ""),
                    "stamps": stamps,
                })
            # pass 2 — cadence, window, time range and occurrences derive from
            # the stamp's STRUCTURE (hc = weekly, qc = seasonal/dated)
            for item in open_rows:
                pairs, node = item["pairs"], item["node"]
                closures = closures_by_parent.get(item["label"], [])
                if item["structure"] == LCL_HC and item["stamps"]:
                    hc_days: list[int] = []
                    hh = mm = 0
                    try:
                        for s in item["stamps"]:
                            d, hh, mm = parse_ic_stamp(s, structure=LCL_HC)
                            hc_days.append(d)
                    except ValueError:
                        continue
                    if closures:
                        win_start, win_end = current_open_window(closures, now=today)
                    else:  # open all cycle: present the current calendar year
                        win_start = date(today.year, 1, 1)
                        win_end = date(today.year, 12, 31)
                    cadence_nodes = (["1-4-3"] if len(set(hc_days)) == 7
                                     else [f"1-4-1-{d}" for d in sorted(set(hc_days))])
                    occurrences = [d.isoformat() for d in
                                   next_hc_occurrences(hc_days, closures, now=today)]
                    time_range = _time_range_text(hh, mm, item["span"])
                    # weekly-view geometry: JS weekday (Sun=0) + minute-of-day window.
                    weekdays = sorted({d % 7 for d in hc_days})  # hc day 1 = Monday → js 1
                    start_min = hh * 60 + mm
                    end_min = min(start_min + max(0, int(item["span"])), 24 * 60 - 1)
                elif item["structure"] == LCL_QC and item["stamps"]:
                    try:
                        day, _h, _m = parse_ic_stamp(item["stamps"][0], structure=LCL_QC)
                    except ValueError:
                        continue
                    win_start = date_of_qc_day(day, cycle_start_year=cycle_start_year_of(today))
                    win_end = win_start + timedelta(days=max(1, item["span"]) - 1)
                    cadence_nodes = ["1-4-2"]
                    occurrences = ([max(today, win_start).isoformat()]
                                   if today <= win_end else [])
                    time_range = "00:00–23:59"
                    weekdays, start_min, end_min = [], 0, 24 * 60 - 1  # all-day, in season
                else:
                    continue  # lc hops reserved; malformed rows degrade silently
                event_class = item["op_class"]
                lonlat = _lonlat(pairs.get(_COORD, [""])[0])
                host_cls = color_class(node, item["label"])
                host_style = ENTITY_CLASS_STYLES.get(host_cls, ENTITY_CLASS_STYLES["legal"])
                events.append({
                    "label": item["label"],
                    "title": pairs.get(_NAME, [item["label"]])[0],
                    "host_node": node,
                    "host_name": entity_name.get(node, ""),
                    "host_category": host_cls,
                    "host_category_label": host_style["label"],
                    "color": host_style["color"],
                    "icon": EVENT_CLASS_ICON.get(event_class, "ticket"),
                    "event_group": EVENT_CLASS_GROUP.get(event_class, "other"),
                    "event_class": event_class,
                    "event_class_label": lcl_label.get(event_class, event_class),
                    "cadence": [lcl_label.get(c, c) for c in cadence_nodes],
                    "window": {"start": win_start.isoformat(), "end": win_end.isoformat()},
                    "time_range": time_range,
                    "weekdays": weekdays,        # JS weekday ints (Sun=0); [] = all-day/seasonal
                    "start_min": start_min,      # minute-of-day window for the week grid
                    "end_min": end_min,
                    "venue": list(lonlat) if lonlat else None,
                    "next_occurrences": occurrences,
                })
    events.sort(key=lambda e: (not e["next_occurrences"],
                               e["next_occurrences"][0] if e["next_occurrences"] else "9999",
                               e["title"]))

    # Farm-stand override: a producer whose location also hosts a farm_stand_hours
    # (1-3-3) recurrence markets AS a farm stand → swap its farm glyph for the stand.
    stand_hosts = {e["host_node"] for e in events if e["event_class"] == "1-3-3"}
    for p in profiles:
        if p["msn_node"] in stand_hosts and p["icon"] in {"farm", "orchard", "vineyard", "apiary"}:
            p["icon"] = "farm_stand"

    # A location that markets AS a farm stand is a farm-stand TYPE, not a producer — so the
    # Operation TYPE facet reads "Farm stand", never "Producer" (producers' farms are not on
    # the operation map at all). Category follows the FINAL farm_stand glyph.
    for p in profiles:
        if p["icon"] == "farm_stand":
            p["category"] = "farm_stand"
            p["category_label"] = _CATEGORY_LABEL["farm_stand"]

    # NETWORK sub-tab sectioning: tag each profile (after the farm-stand override so the
    # icon is final) and each event, then filter to the requested section. Facets + widgets
    # below are computed from the filtered lists, so each sub-tab's counts are self-consistent.
    for p in profiles:
        p["section"] = _section_for(p["category"], p["icon"])
    for e in events:
        e["section"] = "operation"  # every cyclical event is a public food-access recurrence
    if section:
        profiles = [p for p in profiles if p["section"] == section]
        events = [e for e in events if e["section"] == section]

    # per-CSA widget: each csa_operator profile + its csa_pickup (lcl 1-3-2) events,
    # joined by the host msn node. Rendered as a card strip below the map + events list.
    # Accent = the host entity's class colour (same rule as the map).
    csa_widgets = [
        {"label": p["label"], "name": p["name"], "msn_node": p["msn_node"],
         "region": p["region"], "region_node": p["region_node"], "dns": p["dns"],
         "color": p["color"], "light": p["color"],
         "pickups": [e for e in events
                     if e["host_node"] == p["msn_node"] and e["event_class"] == "1-3-2"]}
        for p in sorted(profiles, key=lambda x: x["name"])
        if p["category"] == "csa"
    ]

    region_counts: dict[tuple[str, str], int] = {}
    county_counts: dict[tuple[str, str], int] = {}
    class_counts: dict[str, int] = {}
    type_counts: dict[str, int] = {}
    for p in profiles:
        if p["region_node"]:
            key = (p["region_node"], p["region"])
            region_counts[key] = region_counts.get(key, 0) + 1
        if p["county_node"]:
            ckey = (p["county_node"], p["county"])
            county_counts[ckey] = county_counts.get(ckey, 0) + 1
        class_counts[p["color_class"]] = class_counts.get(p["color_class"], 0) + 1
        if p["category"]:
            type_counts[p["category"]] = type_counts.get(p["category"], 0) + 1

    return {
        "schema": _SCHEMA,
        "tool_id": "network_map",
        "sandbox_id": sandbox_id,
        "source_sandbox": SOURCE_SANDBOX,
        "manifest_document_id": _as_text(manifest.document_id),
        "resource_count": len(resources),
        "rendered_resource_count": rendered,
        "feature_collection": {"type": "FeatureCollection", "features": features},
        "feature_count": len(features),
        "profiles": profiles,
        "profile_count": len(profiles),
        "events": events,
        "event_count": len(events),
        "csa_widgets": csa_widgets,
        "styles": ENTITY_CLASS_STYLES,
        # Chips are the 5 entity classes (the colour legend), fixed order, hosts counted.
        "categories": [
            {"key": key, "label": ENTITY_CLASS_STYLES[key]["label"],
             "color": ENTITY_CLASS_STYLES[key]["color"], "count": class_counts.get(key, 0)}
            for key in _CLASS_ORDER if class_counts.get(key, 0)],
        "regions": [
            {"node": node, "label": label, "count": count}
            for (node, label), count in sorted(region_counts.items(), key=lambda kv: (-kv[1], kv[0][1]))],
        # County-level filter facet (multi-select on the map; the view auto-fits to selection).
        "counties": [
            {"node": node, "label": label, "count": count}
            for (node, label), count in sorted(county_counts.items(), key=lambda kv: kv[0][1])],
        # Farm-profile TYPE facet (ag category / substance) — the "what it is" filter.
        "profile_types": [
            {"key": key, "label": _CATEGORY_LABEL.get(key, key), "count": count}
            for key, count in sorted(type_counts.items(), key=lambda kv: (-kv[1], kv[0]))],
        "plots_source": f"{SOURCE_SANDBOX} source binaries",
    }


class NetworkMapViewer:
    """Renders the Registrar-published resources on the agro NETWORK tab."""

    tool_id = "network_map"
    label = "Network Map"
    summary = "Profiles, events and boundaries published by the Registrar via its source-binary manifest."
    route = WORKBENCH_UI_TOOL_ROUTE
    applies_to_archetype: tuple[str, ...] = ()
    applies_to_source_kind: tuple[str, ...] = ()

    def build_panel_payload(
        self, *, authority_db_file: Path | None, sandbox_id: str, document_id: str,
        datum_address: str, extra_query: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        docs, err = read_sandbox_catalog(authority_db_file, tenant_id=_TENANT_DEFAULT)
        if err:
            return _error(err)
        section = _as_text((extra_query or {}).get("network_section")) or None
        return build_network_map_payload(docs, sandbox_id=sandbox_id, section=section)


register(NetworkMapViewer())
