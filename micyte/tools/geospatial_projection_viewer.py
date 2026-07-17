"""Geospatial Projection — the field/plots map base, derived from farm_profile.

The map half of the old farm_profile viewer, extracted so it can be reused: `farm_profile`
is now the CONSOLIDATED tool (profile_card identity + this geospatial projection), and
`plot_manager` builds on this. Resolves the agro_erp ``farm_profile`` HOPS filament (families
4→5→6→7) into a GeoJSON FeatureCollection (parcels / field / plots). Each PLOT feature carries
its lcl node (``properties.lcl_node``) so an interactive client (Plot Manager) can record which
plots a selection covers.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Any

from micyte.core.datum_ops.datum_resolve import decode_label, resolve_coordinate
from micyte.state_machine.portal_shell.shell_schemas import (
    WORKBENCH_UI_TOOL_ROUTE,
)

from ._archetype import (
    find_named_document,
    read_sandbox_catalog,
    resolve_tool_document,
    resolve_tool_sandbox,
)
from ._hops_dates import chrono_authority, hops_token_to_date
from ._registry import register
from ._shared.utilities import as_text as _as_text
from ._shared.utilities import row_head as _row_head
from ._shared.utilities import row_tail_label as _row_tail_label

_TENANT_DEFAULT = "fnd"
_SCHEMA = "mycite.v2.portal.workbench.tool.geospatial_projection.v1"
_LCL_MARKER = "rf.3-1-5"
_TITLE_MARKER = "rf.3-1-2"
_NOMINAL_MARKER = "rf.3-1-7"
_UTC_MARKER = "rf.3-1-6"      # the feature's born-on day (written since save_field/save_cluster)
_RETIRE_MARKER = "rf.3-1-10"  # the day it stops being in force; absent = still effective
_STRUCTURE_KINDS = ("barn", "greenhouse", "tunnel", "custom_area")
PREVIEW_PLOT_EDGE_M = 60.0

_LAYOUT_SHORT = {"a": "angle_deg", "w": "cell_w_m", "h": "cell_h_m",
                 "t": "sp_top", "b": "sp_bottom", "l": "sp_left", "r": "sp_right"}


def _parse_layout(s: str) -> dict[str, float]:
    """Parse the compact cluster layout string 'a=..|w=..|h=..|t=..|b=..|l=..|r=..' (rf.3-1-7)."""
    out: dict[str, float] = {}
    for part in (s or "").split("|"):
        key, sep, val = part.partition("=")
        full = _LAYOUT_SHORT.get(key.strip()) if sep else None
        if not full:
            continue
        try:
            out[full] = float(val)
        except ValueError:
            pass
    return out


def _in_force(start_tok: str, retire_tok: str, as_of: date, authority: Any) -> bool:
    """Is a feature stamped (``start_tok``, ``retire_tok``) in force on ``as_of``?

    ``start <= as_of < retire``; a missing/undecodable retire token means still effective, and a
    missing/undecodable start means "always was" (every feature written before effective dating
    landed carries a start day, but nothing depends on it being decodable). Fails OPEN — an
    undecodable stamp shows the geometry rather than silently hiding a plot someone contracted.
    """
    retire = hops_token_to_date(authority, retire_tok) if retire_tok else None
    if retire is not None and as_of >= retire:
        return False
    start = hops_token_to_date(authority, start_tok) if start_tok else None
    return not (start is not None and as_of < start)


def _feature(coords: list[tuple[float, float]], *, kind: str, label: str, fid: str,
             lcl_node: str = "", extra: dict[str, Any] | None = None) -> dict[str, Any] | None:
    if len(coords) < 3:
        return None
    ring = [[lon, lat] for lon, lat in coords]
    if ring[0] != ring[-1]:
        ring.append(ring[0])  # GeoJSON polygons are closed
    props: dict[str, Any] = {"kind": kind, "label": label}
    if lcl_node:
        props["lcl_node"] = lcl_node
    if extra:
        props.update(extra)
    return {
        "type": "Feature",
        "id": fid,
        "geometry": {"type": "Polygon", "coordinates": [ring]},
        "properties": props,
    }


def build_geospatial_payload(
    doc: Any, *, preview: bool = True, as_of: date | None = None, authority: Any = None,
) -> dict[str, Any]:
    """Project a farm_profile filament doc → {feature_collection, feature_count, plots_source,
    parcel_count, field_count, plot_count}. Pure (no db); reused by farm_profile + plot_manager.

    **Memoised.** This is pure over ``doc``, and a document id embeds the content hash
    (``lv.<msn>.<sandbox>.<name>.<hash>``) — every write mints a new id — so the id + the read
    options are a complete and self-invalidating cache key. That matters because one PLAN render
    projects the same farm_profile up to seven times (Plot, the Planting map, the calendar,
    Delegate, the consumption model, the FARM overview), and each pass decodes a HOPS coordinate
    for every ring: on trapp that is 3650 plots × 7 ≈ 25k decodes, the dominant cost of the tab.
    **The returned payload is SHARED — treat it as read-only.** Deep-copying it costs more than the
    projection did (a 3650-plot collection is ~845k objects), so callers that need to annotate a
    feature must copy just that feature (see ``planting_map_viewer``). Spreading the result into a
    new dict (``{**geo, ...}``) is fine and is what every caller already does — that only rebinds
    the top level.

    ``preview=False`` shows ONLY geometry that has actually been defined: the ``live_preview``
    square-pack synthesis (which fabricates a plot grid over any field that has no migrated plots)
    is skipped, and ``plots_source`` reports ``"none"`` instead. The Plot Overview reads it that
    way — a viewing surface must not invent plots the operator never drew.

    ``as_of`` (with ``authority``, the chronology needed to decode the stored HOPS day tokens)
    filters to the geometry IN FORCE on that day: a feature is kept iff ``start <= as_of < retire``
    (``rf.3-1-6`` = born-on, ``rf.3-1-10`` = retired-on, absent = still effective). Geometry a
    contract depends on is retired rather than deleted, so this is what lets the map show the epoch
    the operator's viewing day falls in.

    ``as_of=None`` (the default) applies NO date filter and yields every feature ever recorded —
    which is what the consumption model needs, since a contract written against a since-retired
    plot must still resolve that plot's geometry to compute what it consumed.
    """
    key = (_as_text(getattr(doc, "document_id", "")), bool(preview),
           as_of.isoformat() if as_of else "")
    # Only memoise when the id is present AND carries its hash segment — a hand-built doc (tests,
    # fixtures) may reuse an id across different content, and caching that would serve stale rows.
    cacheable = len(key[0].split(".")) > 4
    if cacheable and key in _GEO_CACHE:
        return _GEO_CACHE[key]
    out = _build_geospatial_payload(doc, preview=preview, as_of=as_of, authority=authority)
    if cacheable:
        if len(_GEO_CACHE) >= _GEO_CACHE_MAX:
            _GEO_CACHE.clear()   # whole-farm payloads are large; bound the memory, don't LRU it
        _GEO_CACHE[key] = out
    return out


# document_id -> projection. Bounded and cleared wholesale: entries are big (a 3650-plot feature
# collection) and a stale id can never be hit, so eviction order does not matter.
_GEO_CACHE: dict[tuple[str, bool, str], dict[str, Any]] = {}
_GEO_CACHE_MAX = 24


def _build_geospatial_payload(
    doc: Any, *, preview: bool = True, as_of: date | None = None, authority: Any = None,
) -> dict[str, Any]:
    rows = {_as_text(r.datum_address): r for r in (getattr(doc, "rows", ()) or ())}

    # family-7 features: geometry address -> (kind, label, lcl_node) + optional layout (rf.3-1-7).
    feature_meta: dict[str, tuple[str, str, str]] = {}
    feature_layout: dict[str, dict[str, float]] = {}
    # Geometry addresses whose feature is not in force at as_of. Collected here but applied in the
    # POLY loop below: this builder emits from the 5-* rows and only consults feature_meta as a side
    # lookup, so dropping a feature alone would leave its polygon rendering (unlabelled, un-noded)
    # and still counted.
    retired_geoms: set[str] = set()
    for addr, row in rows.items():
        if not addr.startswith("7-"):
            continue
        head = _row_head(row)
        lcl_node = ""
        layout: dict[str, float] | None = None
        label = _row_tail_label(row)
        days: list[str] = []
        retired_day = ""
        # NB: step 1, not 2. A feature head is NOT 2N+1-aligned (a bare "1" sits at index 3), so
        # markers land at both odd and even indices and a step-2 walk misses most of them. This is
        # also why iter_marker_pairs must not be used on these heads.
        for i in range(1, len(head) - 1):
            marker = _as_text(head[i])
            if marker == _LCL_MARKER:
                lcl_node = _as_text(head[i + 1])
            elif marker == _TITLE_MARKER and not label:
                label = decode_label(_as_text(head[i + 1]))
            elif marker == _NOMINAL_MARKER and layout is None:
                # FIRST nominal wins. This branch used to be a plain assignment, so any nominal
                # appended after a cluster's layout would silently clobber it into {}.
                layout = _parse_layout(decode_label(_as_text(head[i + 1])))
            elif marker == _UTC_MARKER:
                days.append(_as_text(head[i + 1]))
            elif marker == _RETIRE_MARKER:
                retired_day = _as_text(head[i + 1])
        geom_addr = next(
            (_as_text(t) for t in head[2:] if _as_text(t).startswith(("5-", "6-"))),
            "",
        )
        if geom_addr:
            if as_of is not None and not _in_force(
                    days[0] if days else "", retired_day, as_of, authority):
                retired_geoms.add(geom_addr)
                continue
            feature_meta[geom_addr] = ("plot" if lcl_node else "property", label or addr, lcl_node)
            if layout:
                feature_layout[geom_addr] = layout

    features: list[dict[str, Any]] = []
    field_polys: list[list[tuple[float, float]]] = []
    parcel_count = field_count = plot_count = cluster_count = structure_count = 0
    for addr, row in sorted(rows.items()):
        if not addr.startswith("5-") or addr in retired_geoms:
            continue
        head = _row_head(row)
        ring_addr = next((_as_text(t) for t in head[1:] if _as_text(t).startswith("4-")), "")
        ring_row = rows.get(ring_addr)
        if ring_row is None:
            continue
        coords = resolve_coordinate(_row_head(ring_row))
        poly_label = _row_tail_label(row)
        meta = feature_meta.get(addr, ("", "", ""))
        lcl_node = meta[2]
        extra: dict[str, Any] = {}
        if poly_label.startswith("parcel"):
            kind, label = "parcel", poly_label
            parcel_count += 1
        elif poly_label == "field":
            kind, label = "field", meta[1] or "field"
            field_count += 1
            field_polys.append(coords)
        elif poly_label.startswith("cluster"):
            kind, label = "cluster", meta[1] or poly_label
            cluster_count += 1
            if feature_layout.get(addr):
                extra["layout"] = feature_layout[addr]
        elif poly_label in _STRUCTURE_KINDS or poly_label.startswith("structure"):
            kind, label = "structure", meta[1] or poly_label
            structure_count += 1
        elif poly_label.startswith("plot"):
            kind, label = "plot", meta[1] or poly_label
            plot_count += 1
        else:
            kind, label = (meta[0] or "field"), (meta[1] or poly_label or addr)
            if kind == "plot":
                plot_count += 1
            else:
                kind = "field"
                field_polys.append(coords)
        feat = _feature(coords, kind=kind, label=label, fid=f"{doc.canonical_name}:{addr}",
                        lcl_node=lcl_node if kind in ("plot", "cluster", "field", "structure") else "",
                        extra=extra or None)
        if feat:
            features.append(feat)

    if plot_count:
        plots_source = "migrated"
    elif not preview:
        plots_source = "none"
    else:
        plots_source = "live_preview"
    if not plot_count and preview:
        try:
            from shapely.geometry import Polygon

            from micyte.core.hops.square_pack import pack_squares

            idx = 0
            for coords in field_polys:
                if len(coords) < 3:
                    continue
                for square in pack_squares(Polygon(coords), edge_m=PREVIEW_PLOT_EDGE_M):
                    idx += 1
                    feat = _feature(
                        [(x, y) for x, y in list(square.exterior.coords)],
                        kind="plot", label=f"plot_{idx}",
                        fid=f"{doc.canonical_name}:preview:{idx}",
                    )
                    if feat:
                        features.append(feat)
            plot_count = idx
        except Exception:
            plots_source = "unavailable"

    return {
        "feature_collection": {"type": "FeatureCollection", "features": features},
        "feature_count": len(features),
        "plots_source": plots_source,
        "parcel_count": parcel_count,
        "field_count": field_count,
        "plot_count": plot_count,
        "cluster_count": cluster_count,
        "structure_count": structure_count,
    }


def _error(message: str) -> dict[str, Any]:
    return {
        "schema": _SCHEMA, "error": message,
        "feature_collection": {"type": "FeatureCollection", "features": []}, "feature_count": 0,
    }


def resolve_farm_profile(authority_db_file: Path | None, sandbox_id: str, document_id: str, *, tool: Any):
    """Shared farm_profile doc resolution (by archetype, not the auto-selected anchor)."""
    doc, _authority, err = resolve_farm_scene(authority_db_file, sandbox_id, document_id, tool=tool)
    return doc, err


def resolve_farm_scene(authority_db_file: Path | None, sandbox_id: str, document_id: str, *, tool: Any):
    """``(farm_profile doc, chronology authority | None, error | None)`` from ONE catalog read.

    The authority decodes the HOPS day tokens stamped on features, so an ``as_of`` caller needs it
    alongside the doc; resolving both here avoids a second full catalog read just for the anchor.
    """
    docs, err = read_sandbox_catalog(authority_db_file, tenant_id=_TENANT_DEFAULT)
    if err:
        return None, None, _error(err)
    sandbox = resolve_tool_sandbox(sandbox_id, docs=docs)
    if not sandbox:
        return None, None, _error("no sandbox specified")
    doc = resolve_tool_document(
        docs, tool=tool, sandbox=sandbox, document_id=document_id, canonical_name="farm_profile",
    )
    if doc is None:
        return None, None, _error("farm_profile document not found")
    return doc, chrono_authority(find_named_document(docs, sandbox=sandbox, name="anchor")), None


class GeospatialProjectionViewer:
    """The field/plots map (GeoJSON), the geospatial half of farm_profile."""

    tool_id = "geospatial_projection"
    label = "Geospatial Projection"
    summary = "Field and plot polygons projected from the farm_profile HOPS filament."
    route = WORKBENCH_UI_TOOL_ROUTE
    applies_to_archetype: tuple[str, ...] = ("hops_geospatial_filament",)
    applies_to_source_kind: tuple[str, ...] = ()

    def build_panel_payload(
        self, *, authority_db_file: Path | None, sandbox_id: str, document_id: str, datum_address: str,
    ) -> dict[str, Any]:
        doc, err = resolve_farm_profile(authority_db_file, sandbox_id, document_id, tool=self)
        if err:
            return err
        geo = build_geospatial_payload(doc)
        return {
            "schema": _SCHEMA,
            "sandbox_id": resolve_tool_sandbox(sandbox_id, doc=doc),
            "document_id": _as_text(doc.document_id),
            "selected_row_address": _as_text(datum_address),
            **geo,
        }


register(GeospatialProjectionViewer())
