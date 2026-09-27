"""The same rows a table draws, drawn as the places they are in.

A record table's rows already know where they are: `_place.place_of` reads a county and a
municipality off the one msn each row stores, and those prefixes are not merely *related*
to the registrar's outlines — **they are the outline documents' names**. A boundary
document minted for `3-2-3-17-77` is called `3-2-3-17-77`, which is exactly the
`county_msn` a job in Summit carries. So the join between a book of work and a map of Ohio
is a string equality, and this module is mostly the honesty around it.

## What this does NOT do

**It invents no coordinates.** A job row holds an address node, not a point:
`JOB_ROW_KEYS` and `CONTACT_ROW_KEYS` carry msn prefixes and titles and nothing else, the
registrar's `msn_contact_card` has no coordinate field, and `address_nodes` is a name
table. The only rows in the corpus with a real `rf.3-1-1` are ag profiles. A pin per job
would therefore have to be a centroid or a jitter — a position the corpus does not hold,
drawn at a precision that says otherwise. So the map is REGIONAL: the county (or the
municipality) a row is in, shaded by how many rows are in it. That is the resolution the
data actually has.

**It reads only the outlines the rows name.** There are 539 boundary documents. Decoding
all of them costs 2,796 ring decodes and 427,584 HOPS coordinate tokens per request, which
measured ~17 s against a 15 s client timeout — the reason `network_map_viewer` memoises at
all. A table's rows name a handful of counties, so this asks for those by name and reads
nothing else.

## What it says out loud

A map is a claim of completeness in a way a table is not: an operator looking at four
shaded counties reads "these are my jobs", and if eleven rows had no county they are simply
absent from the picture with nothing to notice. So the payload carries `unplaced` (rows
whose msn does not reach the level) and `unoutlined` (regions the rows name that the
registrar has no polygon for), and the renderer states both.
"""

from __future__ import annotations

from typing import Any

from micyte.core.datum_ops.datum_resolve import as_text
from micyte.domains.registry import levels as lv

#: The sandbox that publishes administrative outlines. FND's registrar is the only holder
#: of the name, so `scoped_to_instance` lets every instance see it — which is the same
#: route `_node_names.SHARED_NAME_SANDBOXES` already takes to resolve the titles these
#: rows display.
BOUNDARY_SANDBOX = "registrar"

#: level id -> (the row column holding its msn, the row column holding its title,
#:              the address level, what to call it)
LEVELS: dict[str, tuple[str, str, int, str]] = {
    "county": ("county_msn", "county", lv.COUNTY, "County"),
    "municipality": ("city_msn", "city", lv.MUNICIPALITY, "Municipality"),
}


def _document_ids_named(store: Any, *, tenant_id: str, sandbox: str,
                        names: list[str]) -> dict[str, str]:
    """``name -> document_id`` for the names asked for, in ONE query.

    Asked for by name rather than swept: the whole point is not to touch the other five
    hundred boundary documents.
    """
    wanted = [n for n in dict.fromkeys(names) if n]
    if not wanted:
        return {}
    out: dict[str, str] = {}
    chunk = 400  # SQLite's default parameter ceiling is 999; stay well under it
    with store._connect() as connection:
        for start in range(0, len(wanted), chunk):
            batch = wanted[start:start + chunk]
            placeholders = ",".join("?" for _ in batch)
            rows = connection.execute(
                "SELECT name, document_id FROM documents "
                f"WHERE tenant_id=? AND sandbox=? AND name IN ({placeholders})",
                (tenant_id, sandbox, *batch),
            ).fetchall()
            for row in rows:
                out[row["name"]] = row["document_id"]
    return out


def region_map(
    rows: list[dict[str, Any]],
    *,
    store: Any,
    tenant_id: str,
    level: str = "county",
    facet_param: str = "",
    active: str = "",
) -> dict[str, Any]:
    """The regional map of ``rows`` — one shaded polygon per place they are in.

    ``facet_param`` is the table's own facet parameter for this level, carried so a click
    on a region sets the SAME filter the dropdown does. That is what makes the map a facet
    rather than a picture: narrowing happens server-side, in `narrow`, once, and the table
    and the map can never disagree about which rows are showing.
    """
    spec = LEVELS.get(as_text(level))
    if spec is None:
        return {}
    msn_column, title_column, _depth, level_label = spec

    counts: dict[str, int] = {}
    titles: dict[str, str] = {}
    unplaced = 0
    for row in rows:
        node = as_text((row or {}).get(msn_column)).strip()
        if not node:
            unplaced += 1
            continue
        counts[node] = counts.get(node, 0) + 1
        shown = as_text((row or {}).get(title_column)).strip()
        if shown:
            titles.setdefault(node, shown)

    ids = _document_ids_named(store, tenant_id=tenant_id, sandbox=BOUNDARY_SANDBOX,
                              names=sorted(counts))

    from ._viewscope import read_document
    from .network_map_viewer import _boundary_rings

    features: list[dict[str, Any]] = []
    regions: list[dict[str, Any]] = []
    unoutlined: list[str] = []
    highest = max(counts.values()) if counts else 0
    for node in sorted(counts, key=lambda n: (-counts[n], titles.get(n, n))):
        label = titles.get(node) or node
        count = counts[node]
        document_id = ids.get(node)
        rings = []
        if document_id:
            document = read_document(store, tenant_id=tenant_id, document_id=document_id)
            if document is not None:
                rings = _boundary_rings(document)
        if not rings:
            unoutlined.append(label)
        regions.append({"node": node, "label": label, "count": count,
                        "has_outline": bool(rings)})
        for index, ring in enumerate(rings):
            clean = [[c[0], c[1]] for c in ring
                     if isinstance(c, (list, tuple)) and len(c) >= 2]
            if len(clean) < 3:
                continue
            if clean[0] != clean[-1]:
                clean.append(clean[0])
            features.append({
                "type": "Feature",
                "id": f"{node}:{index}",
                "geometry": {"type": "Polygon", "coordinates": [clean]},
                "properties": {
                    "kind": "region", "level": as_text(level), "node": node,
                    "label": label, "count": count,
                    # 0..1, for shading. Relative to the busiest region rather than to an
                    # absolute scale: the question a map of one operator's book answers is
                    # "where is most of my work", and an absolute scale would paint every
                    # county the same pale tint the day they are all under ten.
                    "weight": (count / highest) if highest else 0.0,
                    "active": node == as_text(active),
                },
            })

    return {
        "level": as_text(level),
        "level_label": level_label,
        "facet_param": as_text(facet_param),
        "active": as_text(active),
        "feature_collection": {"type": "FeatureCollection", "features": features},
        "feature_count": len(features),
        "regions": regions,
        "placed": sum(counts.values()),
        "unplaced": unplaced,
        "region_count": len(counts),
        # Named, not silently absent: a region with rows and no polygon is a hole in the
        # picture that the picture cannot show.
        "unoutlined": unoutlined,
    }


__all__ = ["BOUNDARY_SANDBOX", "LEVELS", "region_map"]
