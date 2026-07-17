"""Batch consumption model — inventory *remaining* = total units minus planted capacity.

A supply batch (an ``invoices`` ``4-7-*`` row) has a total discrete-unit count derived from its
purchased amount and the product's ``propagule_density`` (units/g); a count-unit purchase
(``500 slips``) is already a count. A ``contracts`` ``4-6-*`` row *commits* that batch to a
referent plot (or cluster). The units a plot consumes from the batch is the operator's square-plot
planting capacity::

    n = ((int(a / (s ** 0.5)) + 1) ** 2) // 4

where ``a`` is the plot's side in cm (from its authoritative polygon) and ``s`` is the product's
spacing area per plant in cm² (the product-profile ``spacing`` cm field squared). Remaining =
total minus Sum(n) over the batch's contracts. When spacing (or the plot geometry) is unknown, the
contract's own free-text amount is used as the committed count instead (the pre-existing weight
draw-down behaviour), so nothing regresses for the ~1900 spacing-0 products.

Pure read model (no writes); shared by the Inventory Manager, the Inventory Synopsis and the
Contract Viewer so all three agree on received / consumed / remaining.
"""

from __future__ import annotations

import math
from datetime import date, timedelta
from typing import Any

from micyte.core.datum_ops.datum_resolve import cached_index, decode_label
from micyte.core.datum_ops.units import is_count_unit, parse_quantity, to_grams

from ._archetype import find_named_document
from ._hops_dates import chrono_authority, hops_token_to_date
from ._shared.utilities import as_text as _as_text
from ._shared.utilities import row_head as _row_head
from .geospatial_projection_viewer import build_geospatial_payload
from .product_document_view import build_product_rows

_RF_LCL = "rf.3-1-5"
_RF_UTC = "rf.3-1-6"
_RF_NOMINAL = "rf.3-1-7"
_INVOICES_PREFIX = "4-7-"
_CONTRACTS_PREFIX = "4-6-"
# metres per degree (equirectangular, good for a farm-scale local patch)
_M_PER_DEG_LAT = 110540.0
_M_PER_DEG_LON = 111320.0


def _ring_area_m2(ring: list[Any]) -> float:
    """Shoelace area (m²) of a [lon,lat] ring, locally projected to metres."""
    pts = ring[:-1] if ring and ring[0] == ring[-1] else ring
    if len(pts) < 3:
        return 0.0
    lat0 = sum(float(p[1]) for p in pts) / len(pts)
    mx = _M_PER_DEG_LON * math.cos(math.radians(lat0))
    xy = [(float(p[0]) * mx, float(p[1]) * _M_PER_DEG_LAT) for p in pts]
    acc = 0.0
    for i in range(len(xy)):
        x1, y1 = xy[i]
        x2, y2 = xy[(i + 1) % len(xy)]
        acc += x1 * y2 - x2 * y1
    return abs(acc) / 2.0


def _side_cm(ring: list[Any]) -> float:
    """Equivalent-square side (cm) of a plot ring (exact for the square plots pack_plots emits)."""
    area = _ring_area_m2(ring)
    return math.sqrt(area) * 100.0 if area > 0 else 0.0


def planting_capacity(side_cm: float, spacing_cm: float) -> int | None:
    """Units a square plot of side ``side_cm`` consumes at ``spacing_cm`` per-plant cell.

    ``n = ((int(a / (s ** 0.5)) + 1) ** 2) // 4`` with ``s = spacing_cm²`` (so ``s**0.5`` is the
    cell side). Returns ``None`` when either input is non-positive (caller falls back to the
    contract amount)."""
    if side_cm <= 0 or spacing_cm <= 0:
        return None
    return ((int(side_cm / spacing_cm) + 1) ** 2) // 4


def batch_total_units(amount_text: str, density_units_per_g: float) -> int | None:
    """Total discrete units in a batch: count-unit amount is the count; a mass amount is
    grams × propagule_density. ``None`` when it can't be derived (unknown unit / no density)."""
    qty, unit = parse_quantity(amount_text)
    if is_count_unit(unit):
        return int(qty)
    grams = to_grams(qty, unit)
    if grams is None or density_units_per_g <= 0:
        return None
    return int(grams * density_units_per_g + 1e-9)


# (product_profiles id, lcl id, txa id) -> product index. Memoised for the same reason as the
# geospatial projection: this walks every product profile (~2900 on trapp) and one PLAN render asks
# for it four times (the consumption model, the batch options, gestation, the calendar). A document
# id embeds its content hash, so the key self-invalidates on any write.
_PRODUCT_CACHE: dict[tuple[str, str, str], dict[str, dict[str, Any]]] = {}
_PRODUCT_CACHE_MAX = 8


def _doc_id(doc: Any) -> str:
    return _as_text(getattr(doc, "document_id", ""))


def _product_index(docs: list[Any], sandbox: str) -> dict[str, dict[str, Any]]:
    """product-leaf node -> {name, spacing_cm, density, unit_weight, shelf_days, gestation_days}.

    Memoised and SHARED — read-only, do not mutate the returned dict.
    """
    lcl_doc = find_named_document(docs, sandbox=sandbox, name="lcl")
    txa_doc = find_named_document(docs, sandbox=sandbox, name="txa")
    pp = find_named_document(docs, sandbox=sandbox, name="product_profiles")
    key = (_doc_id(pp), _doc_id(lcl_doc), _doc_id(txa_doc))
    # Only cache when the product doc's id carries its hash segment (lv.<msn>.<sandbox>.<name>.<hash>);
    # a hand-built fixture may reuse an id across different content.
    cacheable = len(key[0].split(".")) > 4
    if cacheable and key in _PRODUCT_CACHE:
        return _PRODUCT_CACHE[key]
    lcl = cached_index(lcl_doc)
    txa = cached_index(txa_doc)
    out: dict[str, dict[str, Any]] = {}
    for p in build_product_rows(pp, lcl_index=lcl, txa_index=txa):
        f = {x["field"]: x for x in p.get("fields", [])}
        node = _as_text(f.get("product_id", {}).get("magnitude"))
        if not node:
            continue
        spacing_val, _u = parse_quantity(_as_text(f.get("spacing", {}).get("resolved")))
        dens_val, _du = parse_quantity(_as_text(f.get("propagule_density", {}).get("resolved")))
        # shelf_life is a seconds scalar (unit_ref 2-1-1, like gestation) → days.
        shelf_secs, _su = parse_quantity(_as_text(f.get("shelf_life", {}).get("resolved")))
        # gestation is the SAME seconds encoding — how long a planting occupies its plot. Stored on
        # every product profile since ingest but read by nothing until now; it is what gives a
        # contract a duration rather than a single day.
        gest_secs, _gu = parse_quantity(_as_text(f.get("gestation", {}).get("resolved")))
        out[node] = {
            "name": _as_text(f.get("taxonomy_id", {}).get("resolved")) or _as_text(p.get("product_name")) or node,
            "spacing_cm": spacing_val,
            "density": dens_val,
            "unit_weight": _as_text(f.get("singular_unit_weight", {}).get("resolved")),
            "shelf_days": int(shelf_secs // 86400) if shelf_secs else 0,
            "gestation_days": int(gest_secs // 86400) if gest_secs else 0,
        }
    if cacheable:
        if len(_PRODUCT_CACHE) >= _PRODUCT_CACHE_MAX:
            _PRODUCT_CACHE.clear()
        _PRODUCT_CACHE[key] = out
    return out


def _plot_sides_cm(docs: list[Any], sandbox: str, *, as_of: date | None = None,
                   authority: Any = None) -> dict[str, float]:
    """plot lcl-node -> equivalent-square side (cm), from the farm_profile geometry.

    ``as_of`` restricts to the plots in force on that day. Callers want one of two things:
    ``as_of=None`` (every plot ever — the default, needed to resolve a contract written against a
    since-retired plot) or a specific day (what a cluster contract's referent actually covered).
    """
    fp = find_named_document(docs, sandbox=sandbox, name="farm_profile")
    if fp is None:
        return {}
    geo = build_geospatial_payload(fp, as_of=as_of, authority=authority)
    sides: dict[str, float] = {}
    for feat in geo.get("feature_collection", {}).get("features", []):
        props = feat.get("properties", {})
        node = _as_text(props.get("lcl_node"))
        if props.get("kind") != "plot" or not node:
            continue
        rings = feat.get("geometry", {}).get("coordinates") or [[]]
        sides[node] = _side_cm(rings[0])
    return sides


def _referent_capacity(node: str, spacing_cm: float, plot_sides: dict[str, float]) -> int | None:
    """Planting capacity of a contract referent: a single plot, or the Σ of a cluster's plots."""
    if node in plot_sides:
        return planting_capacity(plot_sides[node], spacing_cm)
    child_sides = [s for n, s in plot_sides.items() if n.startswith(node + "-")]
    if child_sides:
        total = 0
        any_valid = False
        for s in child_sides:
            cap = planting_capacity(s, spacing_cm)
            if cap is not None:
                total += cap
                any_valid = True
        return total if any_valid else None
    return None


def batch_consumption(docs: list[Any], sandbox: str) -> dict[str, dict[str, Any]]:
    """Per batch (invoice) node -> received / consumed / remaining unit figures.

    ``{batch_node: {product_node, product_name, total_units, consumed_units, remaining_units,
    contract_count, basis}}``. ``basis`` is 'capacity' when the square-plot formula drove the
    consumption or 'amount' when it fell back to the contract free-text amounts.

    Each contract is valued against the plots in force on **its own date**, not against today's
    geometry. That matters for a CLUSTER referent, whose capacity is the Σ of its plots: with
    effective-dated geometry a cluster accumulates retired plots alongside its live ones, and
    summing them all would inflate consumed_units (driving remaining negative) purely because the
    cluster was once reshaped. A contract consumed what its referent covered when it was written.
    """
    products = _product_index(docs, sandbox)
    authority = chrono_authority(find_named_document(docs, sandbox=sandbox, name="anchor"))
    # Memoised per contract date — a farm has a handful of distinct contract days, and each miss
    # re-projects the whole farm_profile.
    sides_cache: dict[Any, dict[str, float]] = {}

    def sides_on(day: date | None) -> dict[str, float]:
        if day not in sides_cache:
            sides_cache[day] = _plot_sides_cm(docs, sandbox, as_of=day, authority=authority)
        return sides_cache[day]

    invoices = find_named_document(docs, sandbox=sandbox, name="invoices")
    batch_meta: dict[str, dict[str, Any]] = {}
    for row in getattr(invoices, "rows", ()) or ():
        if not _as_text(row.datum_address).startswith(_INVOICES_PREFIX):
            continue
        head = _row_head(row)
        lcl_refs = [_as_text(head[i + 1]) for i in range(1, len(head) - 1, 2) if _as_text(head[i]) == _RF_LCL]
        noms = [decode_label(head[i + 1]) for i in range(1, len(head) - 1, 2) if _as_text(head[i]) == _RF_NOMINAL]
        batch_node = lcl_refs[0] if lcl_refs else ""
        product_node = lcl_refs[1] if len(lcl_refs) > 1 else ""
        if not batch_node:
            continue
        prod = products.get(product_node, {})
        amount = noms[0] if noms else ""
        total = batch_total_units(amount, prod.get("density", 0.0))
        batch_meta[batch_node] = {
            "product_node": product_node,
            "product_name": prod.get("name", product_node),
            "spacing_cm": prod.get("spacing_cm", 0.0),
            "shelf_days": prod.get("shelf_days", 0),
            "amount_text": amount,
            "total_units": total,
            "consumed_units": 0,
            "contract_count": 0,
            "basis": "capacity",
        }

    contracts = find_named_document(docs, sandbox=sandbox, name="contracts")
    for row in getattr(contracts, "rows", ()) or ():
        if not _as_text(row.datum_address).startswith(_CONTRACTS_PREFIX):
            continue
        head = _row_head(row)
        lcl_refs = [_as_text(head[i + 1]) for i in range(1, len(head) - 1, 2) if _as_text(head[i]) == _RF_LCL]
        noms = [decode_label(head[i + 1]) for i in range(1, len(head) - 1, 2) if _as_text(head[i]) == _RF_NOMINAL]
        dates = [_as_text(head[i + 1]) for i in range(1, len(head) - 1, 2) if _as_text(head[i]) == _RF_UTC]
        batch_node = lcl_refs[0] if lcl_refs else ""      # first lcl ref = the committed batch
        referent = lcl_refs[1] if len(lcl_refs) > 1 else ""  # second = plot/cluster referent
        meta = batch_meta.get(batch_node)
        if meta is None:
            continue
        # Value it against the geometry that existed on the contract's own day (None -> all plots
        # ever, the safe fallback when the date is missing or undecodable).
        on = hops_token_to_date(authority, dates[0]) if dates else None
        cap = _referent_capacity(referent, meta["spacing_cm"], sides_on(on))
        if cap is None:  # unknown spacing/geometry — fall back to the contract's free-text amount
            amt_qty, _u = parse_quantity(noms[0] if noms else "")
            cap = int(amt_qty)
            meta["basis"] = "amount"
        meta["consumed_units"] += cap
        meta["contract_count"] += 1

    for meta in batch_meta.values():
        total = meta["total_units"]
        meta["remaining_units"] = (total - meta["consumed_units"]) if total is not None else None
    return batch_meta


def contract_spans(docs: list[Any], sandbox: str) -> list[dict[str, Any]]:
    """Every contract as a dated OCCUPANCY of its referent: when is this plot busy, with what.

    ``[{datum_address, referent_node, batch_node, product_node, product_name, gestation_days,
    start: date, end: date, amount, label}]`` — ``start`` is the contract's own day and ``end`` is
    ``start + gestation_days`` (the product's seconds-encoded gestation, i.e. how long the planting
    occupies the plot). A product with no gestation on file yields a single-day span rather than a
    zero-width one, so it still draws.

    The single source of truth for plot occupancy: the Planting calendar's bars, the map's
    "mid-planting" shading, and the effective-day suggestion all read it. Contracts whose date
    cannot be decoded are skipped (they cannot be placed on a calendar).
    """
    products = _product_index(docs, sandbox)
    authority = chrono_authority(find_named_document(docs, sandbox=sandbox, name="anchor"))
    lcl = cached_index(find_named_document(docs, sandbox=sandbox, name="lcl"))

    # batch node -> product node, from the invoices; a contract names its batch, not its product.
    product_of_batch: dict[str, str] = {}
    invoices = find_named_document(docs, sandbox=sandbox, name="invoices")
    for row in getattr(invoices, "rows", ()) or ():
        if not _as_text(row.datum_address).startswith(_INVOICES_PREFIX):
            continue
        head = _row_head(row)
        refs = [_as_text(head[i + 1]) for i in range(1, len(head) - 1, 2) if _as_text(head[i]) == _RF_LCL]
        if refs:
            product_of_batch[refs[0]] = refs[1] if len(refs) > 1 else ""

    out: list[dict[str, Any]] = []
    contracts = find_named_document(docs, sandbox=sandbox, name="contracts")
    for row in getattr(contracts, "rows", ()) or ():
        if not _as_text(row.datum_address).startswith(_CONTRACTS_PREFIX):
            continue
        head = _row_head(row)
        refs = [_as_text(head[i + 1]) for i in range(1, len(head) - 1, 2) if _as_text(head[i]) == _RF_LCL]
        noms = [decode_label(head[i + 1]) for i in range(1, len(head) - 1, 2) if _as_text(head[i]) == _RF_NOMINAL]
        dates = [_as_text(head[i + 1]) for i in range(1, len(head) - 1, 2) if _as_text(head[i]) == _RF_UTC]
        start = hops_token_to_date(authority, dates[0]) if dates else None
        if start is None:
            continue
        batch = refs[0] if refs else ""
        referent = refs[1] if len(refs) > 1 else ""
        product = product_of_batch.get(batch, "")
        prod = products.get(product, {})
        gest = int(prod.get("gestation_days") or 0)
        out.append({
            "datum_address": _as_text(row.datum_address),
            "referent_node": referent,
            "referent": lcl.resolve(referent) or referent,
            "batch_node": batch,
            "batch": lcl.resolve(batch) or batch,
            "product_node": product,
            "product_name": prod.get("name", product) or product,
            "gestation_days": gest,
            "start": start,
            "end": start + timedelta(days=gest or 1),
            "amount": noms[0] if noms else "",
        })
    out.sort(key=lambda s: (s["start"], s["referent_node"]))
    return out


def available_batches(docs: list[Any], sandbox: str) -> list[dict[str, Any]]:
    """Batches with units left to plant, OLDEST FIRST — the contract form's product options.

    ``[{batch_node, batch, product_node, product_name, remaining_units, total_units, received,
    ordinal, oldest_for_product}]``. Ordered by the ``4-7-N`` ordinal ascending, which tracks
    receival order (save_invoice keeps the rows sorted by it and preserves the original date on
    edit). ``oldest_for_product`` flags the first batch of each product, so the form can default to
    consuming the oldest stock rather than whatever happens to be listed first.

    Nothing orders oldest-first today — the Inventory Manager is strictly newest-first — so this is
    a new ordering, not a reuse. A batch whose total can't be derived (unknown unit / no density)
    is kept: it is genuinely available, its remaining is just unknown.
    """
    meta = batch_consumption(docs, sandbox)
    lcl = cached_index(find_named_document(docs, sandbox=sandbox, name="lcl"))
    invoices = find_named_document(docs, sandbox=sandbox, name="invoices")
    authority = chrono_authority(find_named_document(docs, sandbox=sandbox, name="anchor"))
    # Hoisted: _product_index walks every product profile (~2900 on trapp), so this must not be
    # rebuilt per row.
    gestation = products_gestation(docs, sandbox)

    rows: list[dict[str, Any]] = []
    for row in getattr(invoices, "rows", ()) or ():
        addr = _as_text(row.datum_address)
        if not addr.startswith(_INVOICES_PREFIX):
            continue
        head = _row_head(row)
        refs = [_as_text(head[i + 1]) for i in range(1, len(head) - 1, 2) if _as_text(head[i]) == _RF_LCL]
        noms = [decode_label(head[i + 1]) for i in range(1, len(head) - 1, 2) if _as_text(head[i]) == _RF_NOMINAL]
        dates = [_as_text(head[i + 1]) for i in range(1, len(head) - 1, 2) if _as_text(head[i]) == _RF_UTC]
        batch = refs[0] if refs else ""
        m = meta.get(batch)
        if not batch or m is None:
            continue
        if any(t.strip().lower() == "retired" for t in noms):
            continue  # retired: its remainder is waste, not stock
        remaining = m.get("remaining_units")
        if remaining is not None and remaining <= 0:
            continue
        received = hops_token_to_date(authority, dates[0]) if dates else None
        try:
            ordinal = int(addr.rsplit("-", 1)[1])
        except (ValueError, IndexError):
            ordinal = 0
        rows.append({
            "datum_address": addr,
            "ordinal": ordinal,
            "batch_node": batch,
            "batch": lcl.resolve(batch) or batch,
            "product_node": m.get("product_node", ""),
            "product_name": m.get("product_name", ""),
            "total_units": m.get("total_units"),
            "remaining_units": remaining,
            "gestation_days": gestation.get(m.get("product_node", ""), 0),
            "received": received.isoformat() if received else "",
        })
    rows.sort(key=lambda r: r["ordinal"])   # oldest first
    seen: set[str] = set()
    for r in rows:
        r["oldest_for_product"] = r["product_node"] not in seen
        seen.add(r["product_node"])
    return rows


def products_gestation(docs: list[Any], sandbox: str) -> dict[str, int]:
    """product node -> gestation days (memo-free; small and called once per build)."""
    return {node: int(p.get("gestation_days") or 0) for node, p in _product_index(docs, sandbox).items()}


def plots_of_referent(referent: str, plot_nodes: set[str]) -> set[str]:
    """The plots a contract referent covers: itself if it is a plot, else its cluster's children."""
    if referent in plot_nodes:
        return {referent}
    return {n for n in plot_nodes if n.startswith(referent + "-")}


def occupancy_on(spans: list[dict[str, Any]], day: date, plot_nodes: set[str]) -> dict[str, dict[str, Any]]:
    """plot lcl-node -> the span occupying it on ``day`` (start <= day < end).

    A contract on a CLUSTER occupies every plot under it, which is what lets the map shade a plot
    that is mid-planting even though no contract names it directly.
    """
    out: dict[str, dict[str, Any]] = {}
    for s in spans:
        if not (s["start"] <= day < s["end"]):
            continue
        for node in plots_of_referent(s["referent_node"], plot_nodes):
            out.setdefault(node, s)
    return out
