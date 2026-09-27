"""Network Map — the agronomics NETWORK tab: resources published by mycelium_network.

This is the CONSUMER side of the mycelium_network source-binary pipeline. mycelium_network
*produces* a ``network_sources`` manifest (see ``fnd_app/scripts/produce_mycelium_network_sources.py``)
— the index of resources it contributes to the network, each bound to its produced MSS
source-binary identity (``rf.3-1-12``) and a resource kind (``rf.3-1-14``). This tool reads
that manifest cross-sandbox (via the shared tenant catalog) and assembles the NETWORK map v1
payload:

* ``boundary`` resources → polygon backdrop features (as before);
* the ``profiles`` resource (``fnd_ag_profiles``) → point features: one per (entity ×
  ag-profile type), category-styled with the FND network legend, region-tagged from the
  ``administrative`` gazetteer labels, joined by the entity msn node;
* the ``events`` resources (the per-chronology event-log docs ``qc_log`` / ``hc_log`` /
  ``lc_log``; legacy unified ``calendar`` docs parse identically) → the upcoming-events
  list. Event entries are ic-hops cyclical: each ``open_hours`` entry carries a stamp
  per recurrence in exactly ONE cyclical structure (hc hops ``day-hh-mm`` weekly, or
  qc hops ``day[-hh-mm]`` seasonal/dated) plus a (time-unit, magnitude) span;
  ``off_season`` entries (qc day stamp + day span, label ``<parent>.off_season_N``)
  are that event's closures — cadence is derived from WHICH structure the stamp is in,
  and windows from the closure complement. Because closures are qc-addressed even when
  their parent event is weekly, the parent may live in ``hc_log`` while its closures
  live in ``qc_log``: parsing runs over the UNION of all event docs and re-joins by
  label. Joined to hosts by msn node.

Rendered by the ``network_map`` tool renderer (filter bar + SVG map + events list).
A manifest row with no ``rf.3-1-14`` kind is treated as ``boundary`` (back-compat with a
manifest produced before the kind marker existed).
"""
from __future__ import annotations

import json
import threading
import weakref
from collections import OrderedDict
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

from micyte.core.datum_ops import field_registry as _fr
from micyte.core.datum_ops import local_domain as _ld
from micyte.core.datum_ops.event_vocabulary import (
    KIND_OFF_SEASON,
    LEGACY,
    STRUCTURE_HC,
    STRUCTURE_QC,
    EventVocabulary,
    ordinal,
)
from micyte.core.document_naming import parse_canonical_document_id
from micyte.core.instance_baseline import LOCAL_DOMAIN_NAMES
from micyte.core.sources import resolve_sources
from micyte.core.structures.hops import (
    current_open_window,
    cycle_start_year_of,
    date_of_qc_day,
    decode_hops_coordinate_token,
    next_hc_occurrences,
    parse_ic_stamp,
)
from micyte.state_machine.portal_shell.shell_schemas import WORKBENCH_UI_TOOL_ROUTE

from ._archetype import read_sandbox_catalog
from ._registry import register
from ._requirements import REGISTRAR
from ._shared.utilities import as_text as _as_text
from ._shared.utilities import row_head as _row_head

_TENANT_DEFAULT = "fnd"
_SCHEMA = "mycite.v2.portal.workbench.tool.network_map.v1"
SOURCE_SANDBOX = "registrar"
MANIFEST_NAME = "network_sources"
_COORD = _fr.marker(_fr.REGISTRAR, "coordinate")       # rf.3-1-1
_NODE = _fr.marker(_fr.REGISTRAR, "msn_id")            # rf.3-1-2
_NAME = _fr.marker(_fr.REGISTRAR, "title")             # rf.3-1-3
_UTC_M = _fr.marker(_fr.REGISTRAR, "utc")              # rf.3-1-6
_SB = _fr.marker(_fr.REGISTRAR, "mss_source_binary")   # rf.3-1-12
_LCL = _fr.marker(_fr.REGISTRAR, "lcl_id")             # rf.3-1-13
_KIND = _fr.marker(_fr.REGISTRAR, "resource_kind")     # rf.3-1-14
_JURISDICTION = _fr.marker(_fr.REGISTRAR, "jurisdiction_type")   # rf.3-1-10
_REGION_REF = _fr.marker(_fr.REGISTRAR, "region_polygon_ref")    # rf.3-1-11
_STAMP = _fr.marker(_fr.REGISTRAR, "ic_stamp")         # rf.3-1-15 (ic-hops cyclical stamp)
_SPAN = _fr.marker(_fr.REGISTRAR, "tiu_magnitude")     # rf.3-1-16 (tiu span magnitude)
# Event kinds, structures, units, classes and ag categories are named by LEAF ORDINAL —
# the local domain's 2026-09-09 re-rooting kept the numbering and changed every prefix.
# See micyte/core/datum_ops/event_vocabulary.py.

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
# producer subtype (the producer's N-th child) → a more specific substance glyph.
_PRODUCER_SUBTYPE_ICON = {2: "orchard", 4: "farm_stand", 5: "apiary", 6: "vineyard"}
# event class ordinal → substance glyph (the venue the recurrence markets).
EVENT_CLASS_ICON = {1: "farmers_market", 2: "csa", 3: "farm_stand", 4: "grocery", 5: "basket", 6: "ticket"}
# event class ordinal → the events-list toggle group (the card viewer's type filter).
EVENT_CLASS_GROUP = {1: "market", 2: "csa", 3: "stand", 4: "store"}
# ag_profile child ordinal → ag category. 2 = farmers market host, 4 = market (a grocery /
# "food hub" is just a market — no separate category).
_CATEGORY_BY_ORDINAL = {1: "producer", 2: "farmers_market", 3: "csa", 4: "market",
                        5: "seed_supplier", 6: "organization", 7: "administrative"}

# NETWORK sub-tab sectioning (operator taxonomy). Every entity profile falls in exactly
# ONE section so the NETWORK tab's Operation / Peer / Logistic sub-tabs partition the
# map + table with no overlap and no drop:
#   operation — public food-access points the community patronizes, exactly the four
#     market-facing types: CSAs, farmers markets, markets (groceries), farm stands. Decided
#     by market-facing SUBSTANCE (category / glyph), NOT entity class — an administration- or
#     co-op-run farmers market still belongs here (its colour stays who-drives-it). Producers
#     (farms) are NOT shown here; a producer that hosts a farm-stand recurrence stays a
#     peer NODE — the stand itself is an operation EVENT (entities are nodes; farm stands
#     are events). Only an entity-level farmstand profile (lcl 1-2-1-4) sections here.
#   logistic  — upstream input suppliers (seed & input suppliers).
#   peer      — everything else: other farms (producers), organizations, administrative
#     bodies, co-ops and informal entities (the "who" that supports operations).
NETWORK_SECTIONS = ("operation", "peer", "logistic")
_OPERATION_CATEGORIES = frozenset({"csa", "farmers_market", "market", "farm_stand"})
_LOGISTIC_CATEGORIES = frozenset({"seed_supplier"})


def _section_for(category: str, icon: str) -> str:
    """The NETWORK sub-tab a profile belongs to. ``icon`` is the substance glyph — an
    entity-level farmstand profile (lcl 1-2-1-4 subtype) sections as an operation even
    though its category is producer."""
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


def _substance_for_profile(lcl_node: str, vocabulary: EventVocabulary = LEGACY) -> str:
    return (_producer_subtype_icon(lcl_node, vocabulary)
            or _SUBSTANCE_BY_CATEGORY.get(_category_for(lcl_node, vocabulary), "building"))


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


def _ring_rows(document: Any) -> list[list]:
    """Every ring in a boundary node-document, decoded from its ``4-K-N`` ring rows.

    The rows are the authority; ``document_metadata.reference_geojson`` is a derived cache and
    is not always built. akron_city holds 23 ring rows and 4,501 vertices with no cache, so a
    reader that only consulted the cache left the largest city in the service area as a hole in
    the map. Reading the rows first means a boundary is drawable as soon as it is stored.
    """
    rings: list[list] = []
    for row in getattr(document, "rows", ()) or ():
        if not _as_text(getattr(row, "datum_address", "")).startswith("4-"):
            continue
        ring: list[list[float]] = []
        for token in _pairs(_row_head(row)).get(_COORD) or []:
            point = _lonlat(token)
            if point:
                ring.append([point[0], point[1]])
        if len(ring) >= 3:
            rings.append(ring)
    return rings


#: Decoded rings memoized PER DOCUMENT OBJECT: ``id(document) -> (weakref, rings)``.
#:
#: Worth having because one agronomics panel build reads the same boundary documents for three
#: NETWORK sub-tabs. At 466 boundary documents a naive reader did 2,796 ring decodes and 427,584
#: HOPS coordinate tokens per request — ~17 s, against a 15 s client timeout. Decoding each
#: document once takes it to ~3 s.
#:
#: Keyed on the OBJECT and not on ``document_id``, because a document id is not a content
#: identity on the write path that matters here: ``replace_authoritative_document`` REQUIRES
#: ``updated_document.document_id == document_id``, and that is the path the portal Datum
#: Workbench's row editor takes. An edited boundary therefore keeps its id, and an id-keyed
#: cache would serve the pre-edit outline for the life of the worker. A replaced document is
#: always a NEW object — the write drops the catalog cache and the next read rebuilds it — so
#: object identity is the honest key.
#:
#: The weakref is what makes ``id()`` safe, and is also the eviction policy: its callback drops
#: the entry as the document is collected (before CPython can recycle the address), so an id can
#: never be reused onto a live entry and the cache cannot outgrow the documents it describes.
#: Nothing is pinned: the entry holds no strong reference to the document.
_RINGS_BY_DOCUMENT: dict[int, tuple[Any, list[list]]] = {}


def _boundary_rings(document: Any) -> list[list]:
    key = id(document)
    entry = _RINGS_BY_DOCUMENT.get(key)
    if entry is not None and entry[0]() is document:
        return entry[1]
    rings = _ring_rows(document) or _outer_rings(
        (getattr(document, "document_metadata", {}) or {}).get("reference_geojson"))

    def evict(reference: Any) -> None:
        held = _RINGS_BY_DOCUMENT.get(key)
        if held is not None and held[0] is reference:
            _RINGS_BY_DOCUMENT.pop(key, None)

    try:
        _RINGS_BY_DOCUMENT[key] = (weakref.ref(document, evict), rings)
    except TypeError:
        pass  # not weak-referenceable: correctness over the memo
    return rings


#: Region layers, outermost first. `county` is the regional frame; `community` is the
#: municipal layer — cities, townships and villages, which OVERLAP each other by design because
#: an Ohio village is carved out of the township that still surrounds it.
REGION_LEVELS = ("county", "community")
_LEVEL_LABEL = {"county": "Counties", "community": "Municipalities"}


def _region_layers(features: list[dict[str, Any]], node_label: dict[str, str]) -> list[dict[str, Any]]:
    """One entry per drawable region layer: what it holds and which counties it covers."""
    out: list[dict[str, Any]] = []
    for level in REGION_LEVELS:
        nodes = {f["properties"]["node"] for f in features
                 if f["properties"].get("kind") == "parcel"
                 and f["properties"].get("level") == level}
        covers = sorted({"-".join(n.split("-")[:5]) for n in nodes})
        out.append({
            "level": level,
            "label": _LEVEL_LABEL.get(level, level),
            "count": len(nodes),
            "covers": [{"node": n, "label": node_label.get(n, n)} for n in covers],
        })
    return out


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


def _category_for(lcl_node: str, vocabulary: EventVocabulary = LEGACY) -> str:
    """The ag category of a profile's lcl reference: the ordinal of the ag_profile child it
    sits under (``1-3-1-2-1-4`` and ``1-2-1-4`` are both producer/farmstand)."""
    below = vocabulary.below("category", lcl_node)
    return _CATEGORY_BY_ORDINAL.get(below[0] if below else 0, "organization")


def _producer_subtype_icon(lcl_node: str, vocabulary: EventVocabulary = LEGACY) -> str:
    """The producer subtype's glyph, or ``""``: the second ordinal under the ag_profile root
    when the first is the producer (1)."""
    below = vocabulary.below("category", lcl_node)
    return _PRODUCER_SUBTYPE_ICON.get(below[1], "") if below[:1] == (1,) and len(below) >= 2 else ""


def _time_range_text(hour: int, minute: int, span_minutes: int) -> str:
    """``HH:MM–HH:MM`` from an open stamp time + minute span (clamped to the day)."""
    start_m = hour * 60 + minute
    end_m = min(start_m + max(0, int(span_minutes)), 23 * 60 + 59)
    return f"{hour:02d}:{minute:02d}–{end_m // 60:02d}:{end_m % 60:02d}"


# per-chronology event-log docs (system_log family): doc name → its structure lcl leaf.
_LOG_DOC_STRUCTURE_ORDINAL = {"qc_log": STRUCTURE_QC, "hc_log": STRUCTURE_HC, "lc_log": 4}


def iter_event_log_entries(doc: Any, vocabulary: EventVocabulary = LEGACY) -> list[dict[str, Any]]:
    """Parsed event entries of one event-log document, tolerant of both shapes:

    * ``7-3-N`` entries (the per-chronology ``qc_log``/``hc_log``/``lc_log`` docs,
      system_log-family grammar): the event class arrives as the typed pair
      ``"6-1-1", K`` resolved through the doc's own ``4-2-K`` scaffold row → lcl
      ``1-3-K``;
    * legacy ``4-1-N`` calendar rows: the class is the direct non-kind ``1-3-*`` ref.

    Structure prefers the entry's own ``1-5-*`` ref (rows stay self-describing when
    copied out of their doc), falling back to the owning doc's structure by name.
    ``event_class`` may be empty on closure entries. Reused by the micyte.com offering
    exporter — keep it dependency-light and pure.

    ``vocabulary`` says where kinds, structures and units live in the tree the log belongs
    to (``EventVocabulary.from_log``); the default is the pre-2026-09-09 shape.
    """
    type_lcl: dict[str, str] = {}
    for r in getattr(doc, "rows", ()) or ():
        addr = _as_text(getattr(r, "datum_address", ""))
        if addr.startswith("4-2-"):
            pairs = _pairs(_row_head(r))
            lcl = next((c for c in pairs.get(_LCL, []) if vocabulary.is_("class", c)), "")
            if lcl:
                type_lcl[addr.rsplit("-", 1)[-1]] = lcl
    doc_structure_ordinal = _LOG_DOC_STRUCTURE_ORDINAL.get(_doc_name(doc), 0)
    doc_structure = vocabulary.node("structure", doc_structure_ordinal) if doc_structure_ordinal else ""
    entries: list[dict[str, Any]] = []
    for r in getattr(doc, "rows", ()) or ():
        addr = _as_text(getattr(r, "datum_address", ""))
        if not (addr.startswith("7-3-") or addr.startswith("4-1-")):
            continue
        pairs = _pairs(_row_head(r))
        node = pairs.get(_NODE, [""])[0]
        lcls = pairs.get(_LCL, [])
        kind_ref = pairs.get("6-1-1", [""])[0]
        if not node or not (lcls or kind_ref):
            continue
        event_class = (type_lcl.get(kind_ref, vocabulary.node("class", int(kind_ref)) if kind_ref.isdigit() else "")
                       or next((c for c in lcls if vocabulary.is_("class", c)), ""))
        try:
            span = int(pairs.get(_SPAN, ["0"])[0] or 0)
        except ValueError:
            span = 0
        entries.append({
            "label": _row_label(r),
            # An entry that cannot name its own address cannot be edited in place. Carried here
            # rather than re-derived by each caller so the reader stays the single parse.
            "datum_address": addr,
            "node": node,
            "event_class": event_class,
            "event_kind": next((c for c in lcls if vocabulary.is_("kind", c)), ""),
            "structure": next((c for c in lcls if vocabulary.is_("structure", c)), "") or doc_structure,
            "stamps": pairs.get(_STAMP, []),
            "span": span,
            "span_unit": next((c for c in lcls if vocabulary.is_("unit", c)), ""),
            "coord": pairs.get(_COORD, [""])[0],
            "title": pairs.get(_NAME, [""])[0],
        })
    return entries


def build_network_map_base(docs: list[Any], *, sandbox_id: str,
                           now: datetime | None = None) -> dict[str, Any]:
    """Pure: the section-INDEPENDENT half of the NETWORK map v1 payload, built once.

    Separated from the db read so it is unit-testable, and separated from the section filter
    so one request can serve several sub-tabs from a single build. Everything costly lives
    here: the manifest walk, the gazetteer labels, the decoded boundary geometry, ``features``
    and ``region_layers``. ``profiles`` and ``events`` come back fully TAGGED with their
    section but unfiltered — :func:`section_view` does the filtering and recomputes the facets
    that depend on it.
    """
    now = now or datetime.now(UTC)
    by_name: dict[str, Any] = {}
    for doc in docs:
        if _as_text(getattr(doc, "document_id", "")).find(f".{SOURCE_SANDBOX}.") == -1:
            continue
        by_name[_doc_name(doc)] = doc
    manifest = by_name.get(MANIFEST_NAME)
    if manifest is None:
        return _error(f"{SOURCE_SANDBOX} source-binary manifest ({MANIFEST_NAME}) not found")
    # Read the manifest through the sources resolver rather than parsing it here, so
    # this surface reports a stale or missing pin instead of rendering it as though
    # nothing were wrong. verify=False: the map is a hot path and the bitstream
    # family costs a closure encode per resource — the Sources panel and the
    # coherence gate are where pins are actually checked.
    resolution = resolve_sources(docs, sandbox=SOURCE_SANDBOX, manifest_name=MANIFEST_NAME)
    resources = [{"name": r.row.declared_name, "node": r.row.node,
                  "source_binary": r.row.recorded_hash, "kind": r.row.kind or "boundary"}
                 for r in resolution.sources]

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
    jurisdiction_of: dict[str, str] = {}
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
                # region_polygon_ref IS the gazetteer node the boundary document is named for,
                # so this join is what lets an outline say whether it is a city, a township or
                # a village without the map hardcoding a list.
                region_ref = pairs.get(_REGION_REF, [""])[0]
                if region_ref:
                    jurisdiction_of.setdefault(region_ref, pairs.get(_JURISDICTION, [""])[0])
            elif _LCL in pairs:
                entity_class.setdefault(node, pairs[_LCL][0])
    host_profile_cats: dict[str, list[str]] = {}
    # Where the event vocabulary and the ag categories live in THIS tree (by label); the
    # legacy shape for a corpus whose tree predates the labels. Built before anything
    # categorizes a profile or an event.
    lcl_doc = next((by_name[n] for n in LOCAL_DOMAIN_NAMES if n in by_name), None)
    vocabulary = EventVocabulary.from_log(_ld.read_log(lcl_doc)) if lcl_doc is not None else LEGACY
    profiles_doc = by_name.get("fnd_ag_profiles")
    if profiles_doc is None:
        # The ag profiles moved to agnet/member_ag_profiles (2026-08-05); the
        # registrar name above stays as the first lookup for a still/cached corpus
        # that predates the move. Without this the map lost its ag-profile colour
        # classes silently — `profiles_doc is None` renders, just wrong.
        profiles_doc = next(
            (d for d in docs
             if ".agnet.member_ag_profiles." in _as_text(getattr(d, "document_id", ""))),
            None)
    for r in (getattr(profiles_doc, "rows", ()) or ()) if profiles_doc is not None else ():
        pairs = _pairs(_row_head(r))
        node, lcl_node = pairs.get(_NODE, [""])[0], pairs.get(_LCL, [""])[0]
        if node and lcl_node:
            host_profile_cats.setdefault(node, []).append(_category_for(lcl_node, vocabulary))

    def entity_kind_of(node: str) -> str:
        """The marker GLYPH class: administrative / community / cooperative by entity
        class; hub when the entity IS a market/grocery storefront (1-2-4 — fresh_fork,
        purple_brown_farm_store); farm when the entity works the land (producer or
        csa profile); else a legal organization."""
        if node in admin_nodes:
            return "administrative"
        cls = vocabulary.below("entity", entity_class.get(node, ""))
        if cls[:1] == (2,):            # informal
            return "community"
        if cls[:2] == (1, 4):          # legal / cooperative
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
    for r in (getattr(lcl_doc, "rows", ()) or ()) if lcl_doc is not None else ():
        pairs = _pairs(_row_head(r))
        node = pairs.get(_LCL, [""])[0]
        if node:
            lcl_label[node] = _row_label(r)

    features: list[dict[str, Any]] = []
    profiles: list[dict[str, Any]] = []
    events: list[dict[str, Any]] = []
    event_docs: list[Any] = []
    rendered = 0
    for res in resources:
        doc = resolution.document(res["name"])
        if doc is None:
            continue
        if res["kind"] == "boundary":
            rings = _boundary_rings(doc)
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
                                   # What KIND of jurisdiction this outline is. A township and
                                   # the village carved out of it overlap by design, so the
                                   # reader needs to know which is which to read the overlap.
                                   "jurisdiction": jurisdiction_of.get(res["name"], ""),
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
                category = _category_for(lcl_node, vocabulary)
                icon = _substance_for_profile(lcl_node, vocabulary)   # WHAT it markets → glyph
                if icon == "farm_stand" and category == "producer":
                    # Entity-LEVEL farm-stand profiles (lcl 1-2-1-4 subtype)
                    # present as farm stands EVERYWHERE — TYPE facet, chip and
                    # section must all read "Farm stand", never "Producer" —
                    # so the category follows the glyph coercion.
                    category = "farm_stand"
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
                    "icon": icon,
                    "dns": pairs.get("rf.3-1-9", [""])[0],
                })
        elif res["kind"] == "events":
            rendered += 1
            event_docs.append(doc)

    # events: parsed AFTER the resource loop over the UNION of all event-log docs
    # (qc_log / hc_log / lc_log — legacy `calendar` parses identically). Closures are
    # qc-addressed even when their parent event is weekly (hc), so the parent may live
    # in hc_log while its closures live in qc_log — pass 1 must see every doc before
    # pass 2 re-joins them by label.
    today = now.date()
    # pass 1 — parse every event entry; off_season entries become their
    # parent event's closure runs (qc day stamp + day-unit span)
    open_rows: list[dict[str, Any]] = []
    closures_by_parent: dict[str, list[tuple[int, int]]] = {}
    # Counted HERE, where the parse already happens, so a caller can state what the schedule
    # covers without parsing a log a second time. `closures` are not losses: an off_season entry
    # becomes a gap in its parent's window, which is why parsed != open + rendered.
    log_coverage: list[dict[str, Any]] = []
    for doc in event_docs:
        parsed = iter_event_log_entries(doc, vocabulary)
        closures = sum(1 for e in parsed if ordinal(e["event_kind"]) == KIND_OFF_SEASON)
        log_coverage.append({
            "document": _doc_name(doc),
            "parsed": len(parsed),
            "closures": closures,
            "events": len(parsed) - closures,
        })
        for entry in parsed:
            if ordinal(entry["event_kind"]) == KIND_OFF_SEASON:
                if not entry["stamps"]:
                    continue
                try:
                    day, _h, _m = parse_ic_stamp(entry["stamps"][0], structure=STRUCTURE_QC)
                except ValueError:
                    continue
                parent = entry["label"].rsplit(".off_season", 1)[0]
                closures_by_parent.setdefault(parent, []).append((day, max(1, entry["span"])))
                continue
            open_rows.append(entry)
    # pass 2 — cadence, window, time range and occurrences derive from
    # the stamp's STRUCTURE (hc = weekly, qc = seasonal/dated)
    for item in open_rows:
        node = item["node"]
        closures = closures_by_parent.get(item["label"], [])
        if ordinal(item["structure"]) == STRUCTURE_HC and item["stamps"]:
            hc_days: list[int] = []
            hh = mm = 0
            try:
                for s in item["stamps"]:
                    d, hh, mm = parse_ic_stamp(s, structure=STRUCTURE_HC)
                    hc_days.append(d)
            except ValueError:
                continue
            if closures:
                win_start, win_end = current_open_window(closures, now=today)
            else:  # open all cycle: present the current calendar year
                win_start = date(today.year, 1, 1)
                win_end = date(today.year, 12, 31)
            cadence_nodes = ([vocabulary.node("cadence", 3)] if len(set(hc_days)) == 7
                             else [vocabulary.node("cadence", 1, d) for d in sorted(set(hc_days))])
            occurrences = [d.isoformat() for d in
                           next_hc_occurrences(hc_days, closures, now=today)]
            time_range = _time_range_text(hh, mm, item["span"])
            # weekly-view geometry: JS weekday (Sun=0) + minute-of-day window.
            weekdays = sorted({d % 7 for d in hc_days})  # hc day 1 = Monday → js 1
            start_min = hh * 60 + mm
            end_min = min(start_min + max(0, int(item["span"])), 24 * 60 - 1)
        elif ordinal(item["structure"]) == STRUCTURE_QC and item["stamps"]:
            try:
                day, _h, _m = parse_ic_stamp(item["stamps"][0], structure=STRUCTURE_QC)
            except ValueError:
                continue
            win_start = date_of_qc_day(day, cycle_start_year=cycle_start_year_of(today))
            win_end = win_start + timedelta(days=max(1, item["span"]) - 1)
            cadence_nodes = [vocabulary.node("cadence", 2)]
            occurrences = ([max(today, win_start).isoformat()]
                           if today <= win_end else [])
            time_range = "00:00–23:59"
            weekdays, start_min, end_min = [], 0, 24 * 60 - 1  # all-day, in season
        else:
            continue  # lc hops reserved; malformed rows degrade silently
        event_class = item["event_class"]
        lonlat = _lonlat(item["coord"])
        host_cls = color_class(node, item["label"])
        host_style = ENTITY_CLASS_STYLES.get(host_cls, ENTITY_CLASS_STYLES["legal"])
        events.append({
            "label": item["label"],
            "title": item["title"] or item["label"],
            "host_node": node,
            "host_name": entity_name.get(node, ""),
            "host_category": host_cls,
            "host_category_label": host_style["label"],
            "color": host_style["color"],
            "icon": EVENT_CLASS_ICON.get(ordinal(event_class), "ticket"),
            "event_group": EVENT_CLASS_GROUP.get(ordinal(event_class), "other"),
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

    # NB: no farm-stand override here any more. Doctrine: entities are nodes; farm stands
    # are EVENTS. A producer that hosts a 1-3-3 recurrence stays a producer node (farm
    # glyph, peer section) — the farm-stand fact is carried by the event. Entity-LEVEL
    # farmstand profiles (lcl 1-2-1-4 subtype) are coerced to category "farm_stand" at
    # profile build, so TYPE facet, chip and section all agree ("Farm stand" on the
    # operation tab — never a "Producer" chip on an operation profile).

    # NETWORK sub-tab sectioning: TAG each profile and each event here, in the base. The
    # filtering itself is `section_view`'s job, because three sub-tabs want three different
    # slices of this one build.
    for p in profiles:
        p["section"] = _section_for(p["category"], p["icon"])
    for e in events:
        e["section"] = "operation"  # every cyclical event is a public food-access recurrence

    return {
        "schema": _SCHEMA,
        "tool_id": "network_map",
        "sandbox_id": sandbox_id,
        "source_sandbox": SOURCE_SANDBOX,
        "manifest_document_id": _as_text(manifest.document_id),
        "resource_count": len(resources),
        "rendered_resource_count": rendered,
        # What the manifest declares and how far it can be trusted. Stated rather
        # than assumed: before this, a pin that had drifted rendered identically to
        # one that had not, so nothing anywhere said the map was reading documents
        # its own manifest no longer describes.
        "source_coverage": resolution.coverage(),
        "feature_collection": {"type": "FeatureCollection", "features": features},
        "feature_count": len(features),
        "profiles": profiles,
        "events": events,
        # Per-log entry accounting, so a schedule view can say what it read rather than leave
        # "55 events" to be taken on trust. An empty log still appears with zeros: a document
        # that vanishes from the list reads as one that was never consulted.
        "event_log_coverage": log_coverage,
        "styles": ENTITY_CLASS_STYLES,
        # The geospatial-browsing layer control. Toggling a layer changes which outlines paint
        # and how the view fits; it never filters pins or re-resolves a node. `covers` names the
        # counties whose municipalities are actually drawn, so a client can say WHY the
        # municipality layer looks empty over a county instead of showing a blank.
        "region_layers": _region_layers(features, node_label),
        "plots_source": f"{SOURCE_SANDBOX} source binaries",
    }


def section_view(base: dict[str, Any], section: str | None = None) -> dict[str, Any]:
    """One NETWORK sub-tab's view of an already-built base. Pure dict work, no geometry.

    Everything expensive in :func:`build_network_map_base` — the manifest walk, the gazetteer,
    the decoded boundary geometry, ``features``, ``region_layers`` — is section-INDEPENDENT.
    Only the profile/event lists and the facets derived from them vary, so this is the whole of
    what a second sub-tab actually needs recomputed.

    Returns a NEW dict and never mutates ``base``: one request hands the same base to three
    sub-tabs, so filtering in place would let the first sub-tab decide what the other two see.
    """
    if base.get("error"):
        return dict(base)
    profiles = list(base.get("profiles") or ())
    events = list(base.get("events") or ())
    if section:
        profiles = [p for p in profiles if p.get("section") == section]
        events = [e for e in events if e.get("section") == section]

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
        **base,
        "profiles": profiles,
        "profile_count": len(profiles),
        "events": events,
        "event_count": len(events),
        "csa_widgets": csa_widgets,
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
    }


def build_network_map_payload(docs: list[Any], *, sandbox_id: str,
                              now: datetime | None = None,
                              section: str | None = None) -> dict[str, Any]:
    """Pure: assemble the NETWORK map v1 payload from the mycelium_network manifest.

    Kept as the one-shot composition of :func:`build_network_map_base` and
    :func:`section_view` so every caller that wants a single payload — the menubar's
    ``network_map`` tool, micyte.com's export, the tests — reads exactly as it always did. A
    caller that wants SEVERAL sections of the same corpus should build the base itself and call
    ``section_view`` per section; that is what the agronomics NETWORK tab does, and it is the
    difference between one build per request and six.
    """
    return section_view(
        build_network_map_base(docs, sandbox_id=sandbox_id, now=now), section)


#: The section-independent base, remembered per store version, sandbox and DAY. The base
#: is the expensive half — the manifest walk, the gazetteer, the decoded boundary geometry
#: (518 features, 3.2 MB) — and it depends on the store and on ``now`` only through
#: ``now.date()`` (the open windows and next occurrences). So the key is the store's
#: identity, the sandbox, the instance scope and today's date; a write or a new day is a
#: new key. Two entries. `section_view` never mutates the base it is handed.
_BASE_LOCK = threading.Lock()
_BASE: OrderedDict[tuple[str, int, str, str, str], dict[str, Any]] = OrderedDict()
_BASE_MAX = 2


def remembered_network_map_base(
    authority_db_file: Any, *, sandbox_id: str, now: datetime | None = None
) -> dict[str, Any]:
    """`build_network_map_base` over the registrar sandbox, once per (store, day)."""
    from micyte.core.instance_scope import active_instance_msn

    now = now or datetime.now(UTC)
    path = Path(str(authority_db_file)) if authority_db_file is not None else None
    try:
        identity = (str(path.resolve()), int(path.stat().st_mtime_ns)) if path else ("", 0)
    except OSError:
        identity = (str(path), 0)
    key = (identity[0], identity[1], _as_text(sandbox_id), active_instance_msn() or "",
           now.date().isoformat())
    with _BASE_LOCK:
        hit = _BASE.get(key)
        if hit is not None:
            _BASE.move_to_end(key)
    if hit is not None:
        return hit
    docs, err = read_sandbox_catalog(
        authority_db_file, tenant_id=_TENANT_DEFAULT, sandbox=SOURCE_SANDBOX)
    if err:
        return _error(err)
    base = build_network_map_base(docs, sandbox_id=sandbox_id, now=now)
    # An error base (no manifest in this store) is remembered too: the store has not
    # changed, so neither has the answer, and a write that adds the manifest is a new key.
    with _BASE_LOCK:
        for stale in [k for k in _BASE if k[0] == key[0] and k[2:] == key[2:] and k[1] != key[1]]:
            _BASE.pop(stale, None)
        _BASE[key] = base
        _BASE.move_to_end(key)
        while len(_BASE) > _BASE_MAX:
            _BASE.popitem(last=False)
    return base


class NetworkMapViewer:
    """Renders the Registrar-published resources on the agro NETWORK tab."""

    tool_id = "network_map"
    label = "Network Map"
    summary = "Profiles, events and boundaries published by the Registrar via its source-binary manifest."
    route = WORKBENCH_UI_TOOL_ROUTE
    #: Scoped to the instance kind this belongs to — see tools/_requirements.
    requires = REGISTRAR

    applies_to_archetype: tuple[str, ...] = ()
    applies_to_source_kind: tuple[str, ...] = ()

    def build_panel_payload(
        self, *, authority_db_file: Path | None, sandbox_id: str, document_id: str,
        datum_address: str, extra_query: dict[str, Any] | None = None,
        network_base: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """``network_base`` is an already-built base to take a section view of.

        A composer rendering several NETWORK sub-tabs (the agronomics tab) builds it once and
        passes it to each; the registry/menubar path passes nothing and builds its own, exactly
        as before.
        """
        section = _as_text((extra_query or {}).get("network_section")) or None
        if network_base is not None:
            return section_view(network_base, section)
        return section_view(
            remembered_network_map_base(authority_db_file, sandbox_id=sandbox_id), section)


register(NetworkMapViewer())
