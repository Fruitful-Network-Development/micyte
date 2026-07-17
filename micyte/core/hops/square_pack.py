"""Plot-packing geometry for farm field / cluster plots.

Pure geometry: given a region polygon (lon/lat), return a maximal set of equal,
real-world-sized rectangular plots whose entire area lies inside the region (none
crossing the boundary). Two entry points:

- ``pack_plots`` — the general packer: fixed real-world ``cell_w_m`` x ``cell_h_m``
  cells, an optional grid rotation ``angle_deg`` in [0, 90), and per-side gutter
  ``spacing_m`` = (top, bottom, left, right) metres. This drives the cluster
  authoring flow (draw a region -> auto-generate plots at an angle/size/spacing).
- ``pack_squares`` — the historical equal-axis-aligned-square packer (TASK-004/005/
  006), now a thin wrapper over ``pack_plots`` (angle 0, no spacing, cell_w==cell_h).

Correctness note: rotation and spacing are metric operations, so packing happens in
a *local tangent (equirectangular) metric frame* centred on the region — degrees are
mapped to metres via ``meters_to_degrees`` at the region's mid-latitude, the packing
runs in metres, and the kept cells are mapped back to lon/lat. This keeps a rotated
cell a true real-world rectangle rather than a degree-space box (whose east-west span
is compressed by cos(lat)). See plans/Farm-Authoring-Program-2026-07-10.plan.md and
plans/TASK-003-farm-plot-model.md.

shapely is the only third-party dependency (2.1.2 in the fnd_portal venv). No
randomness — the grid-origin sweep is a deterministic scan so output is stable.
"""

from __future__ import annotations

import math

from shapely.affinity import affine_transform
from shapely.affinity import rotate as _rotate
from shapely.geometry import Polygon, box

# WGS84 metres-per-degree of latitude (near-constant); longitude scales by cos(lat).
_M_PER_DEG_LAT = 111_320.0


def meters_to_degrees(edge_m: float, latitude: float) -> tuple[float, float]:
    """Convert a real-world edge length (metres) to (d_lon, d_lat) degrees at a
    given latitude, so the resulting cell is a real-world square (axis-aligned)."""
    d_lat = edge_m / _M_PER_DEG_LAT
    cos_lat = math.cos(math.radians(latitude))
    d_lon = edge_m / (_M_PER_DEG_LAT * cos_lat) if cos_lat else d_lat
    return d_lon, d_lat


def pack_plots(
    region: Polygon,
    *,
    cell_w_m: float,
    cell_h_m: float,
    angle_deg: float = 0.0,
    spacing_m: tuple[float, float, float, float] = (0.0, 0.0, 0.0, 0.0),
    origin_steps: int = 5,
) -> list[Polygon]:
    """Return a maximal set of equal ``cell_w_m`` x ``cell_h_m`` plots inside ``region``.

    ``angle_deg`` (in [0, 90)) rotates the plot GRID — it sets the orientation of the
    generated plots, not the region polygon. ``spacing_m`` = (top, bottom, left, right)
    are per-side gutters in metres: the grid pitch is ``cell_h_m + top + bottom`` (rows)
    and ``cell_w_m + left + right`` (columns), and each cell is inset from the
    bottom-left of its pitch box by (left, bottom) so the named margins are honoured
    (symmetric spacing therefore centres the cell). The grid origin is swept over an
    ``origin_steps`` x ``origin_steps`` sub-pitch offset grid and the densest packing is
    kept — deterministic, so the same inputs always yield the same plots. A cell is kept
    only when ``region`` covers it entirely (edges may touch the boundary, none cross).
    Output is ordered row-major in the grid frame for stable downstream addressing.

    Returns [] for a missing/empty region, non-positive cell size, an out-of-range
    angle, negative spacing, or a near-polar region (where cos(lat)->0 degenerates the
    metric frame).
    """
    if region is None or region.is_empty:
        return []
    if cell_w_m <= 0 or cell_h_m <= 0:
        return []
    if not (0.0 <= float(angle_deg) < 90.0):
        return []
    sp_top, sp_bottom, sp_left, sp_right = (float(s) for s in spacing_m)
    if min(sp_top, sp_bottom, sp_left, sp_right) < 0:
        return []

    min_x, min_y, max_x, max_y = region.bounds
    lat_mid = (min_y + max_y) / 2.0
    lon_mid = (min_x + max_x) / 2.0
    # Near the poles cos(lat)->0, so a metre maps to an unbounded span of longitude
    # and the local metric frame degenerates. Refuse rather than emit distorted cells.
    if abs(lat_mid) >= 89.9:
        return []
    d_lon_per_m, d_lat_per_m = meters_to_degrees(1.0, lat_mid)  # degrees per metre
    if d_lon_per_m <= 0 or d_lat_per_m <= 0:
        return []
    mx = 1.0 / d_lon_per_m  # metres per degree of longitude at lat_mid
    my = 1.0 / d_lat_per_m  # metres per degree of latitude

    # Affine maps between lon/lat and the local metric frame (origin at the region's
    # bounds-centre). affine_transform matrix is [a, b, d, e, xoff, yoff].
    to_metres = [mx, 0.0, 0.0, my, -mx * lon_mid, -my * lat_mid]
    to_degrees = [d_lon_per_m, 0.0, 0.0, d_lat_per_m, lon_mid, lat_mid]

    region_m = affine_transform(region, to_metres)
    # Rotate the region by -angle into the grid frame (about the metric origin, which is
    # the region centre). Packing axis-aligned there == packing at +angle in the world.
    region_g = _rotate(region_m, -float(angle_deg), origin=(0.0, 0.0)) if angle_deg else region_m

    pitch_x = cell_w_m + sp_left + sp_right
    pitch_y = cell_h_m + sp_top + sp_bottom
    if pitch_x <= 0 or pitch_y <= 0:
        return []

    g_min_x, g_min_y, g_max_x, g_max_y = region_g.bounds
    steps = max(1, int(origin_steps))
    best: list[tuple[int, int, Polygon]] = []
    for ox in range(steps):
        for oy in range(steps):
            start_x = g_min_x - pitch_x * (ox / steps)
            start_y = g_min_y - pitch_y * (oy / steps)
            n_cols = math.ceil((g_max_x - start_x) / pitch_x) + 1
            n_rows = math.ceil((g_max_y - start_y) / pitch_y) + 1
            cells: list[tuple[int, int, Polygon]] = []
            for r in range(n_rows):
                cy0 = start_y + r * pitch_y + sp_bottom
                for c in range(n_cols):
                    cx0 = start_x + c * pitch_x + sp_left
                    cell = box(cx0, cy0, cx0 + cell_w_m, cy0 + cell_h_m)
                    if region_g.covers(cell):
                        cells.append((r, c, cell))
            if len(cells) > len(best):
                best = cells

    best.sort(key=lambda rc: (rc[0], rc[1]))  # row-major in the grid frame
    out: list[Polygon] = []
    for _, _, cell in best:
        world = _rotate(cell, float(angle_deg), origin=(0.0, 0.0)) if angle_deg else cell
        out.append(affine_transform(world, to_degrees))
    return out


def pack_squares(field: Polygon, edge_m: float, *, origin_steps: int = 5) -> list[Polygon]:
    """Return the maximal set of equal axis-aligned squares fully inside ``field``.

    Historical entry point (TASK-004/005/006): a thin wrapper over :func:`pack_plots`
    with a square ``edge_m`` cell, no rotation, and no spacing. Kept for the plot
    migration + viewer that call it. A square is kept only when ``field.covers`` it;
    output is sorted by (row, col) for stable addressing.
    """
    return pack_plots(
        field,
        cell_w_m=edge_m,
        cell_h_m=edge_m,
        angle_deg=0.0,
        spacing_m=(0.0, 0.0, 0.0, 0.0),
        origin_steps=origin_steps,
    )


def field_polygon_from_hops_tokens(tokens: list[str]) -> Polygon:
    """Decode a ring of HOPS coordinate tokens (rf.3-1-3 values) to a shapely
    Polygon in lon/lat. Raises ValueError if fewer than 3 vertices decode."""
    from micyte.core.structures.hops import decode_hops_coordinate_token

    points: list[tuple[float, float]] = []
    for token in tokens:
        decoded = decode_hops_coordinate_token(token)
        if not decoded:
            continue
        points.append((decoded["longitude"]["value"], decoded["latitude"]["value"]))
    if len(points) < 3:
        raise ValueError("hops ring needs at least 3 decodable vertices")
    return Polygon(points)


def square_to_hops_tokens(square: Polygon) -> list[str]:
    """Encode a plot's 4 corners (open ring) to HOPS coordinate tokens for persistence
    as a family-4 ring inside farm_profile (TASK-006). Works for rotated plots too —
    the corners are written as-is."""
    from micyte.core.hops.geojson import encode_hops_coordinate

    corners = list(square.exterior.coords)[:4]  # exterior repeats the first point; drop it
    return [encode_hops_coordinate(float(lon), float(lat)) for lon, lat in corners]
