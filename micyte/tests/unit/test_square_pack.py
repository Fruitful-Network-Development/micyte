from __future__ import annotations

import math
import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from shapely.geometry import Polygon

from micyte.core.hops.square_pack import (
    meters_to_degrees,
    pack_plots,
    pack_squares,
    square_to_hops_tokens,
)
from micyte.core.structures.hops import decode_hops_coordinate_token

# The live agro_erp farm_profile parcel_1 outer ring (4-29-1), decoded to lon/lat
# (read-back 2026-06-02). ~800 m across in Summit County, Ohio.
PARCEL_1 = [
    (-81.519243306, 41.2358431405), (-81.5192077635, 41.240386448),
    (-81.5208272952, 41.2403471539), (-81.5223023446, 41.240311345),
    (-81.524273366, 41.238523911), (-81.526692561, 41.2385314602),
    (-81.5274180211, 41.2385337141), (-81.5274897614, 41.2355360559),
    (-81.527457952, 41.2355309117), (-81.5272304527, 41.2354988015),
    (-81.5270025189, 41.2354684999), (-81.5266417169, 41.2354905685),
    (-81.5262771222, 41.2353705249), (-81.5260239954, 41.2353363349),
    (-81.5259168111, 41.2353148451), (-81.5258118638, 41.2352877835),
    (-81.5257096622, 41.2352552805), (-81.5256107015, 41.2352174942),
    (-81.5248421215, 41.2349538988), (-81.5231359133, 41.2343476921),
    (-81.5224764738, 41.2341463354), (-81.5223210192, 41.2341638069),
    (-81.5221793987, 41.2340169621), (-81.5218324434, 41.2338878367),
    (-81.5213051917, 41.233707396), (-81.5204469233, 41.2334746289),
    (-81.5200574226, 41.2333636127), (-81.5193065203, 41.2331752544),
    (-81.5193059638, 41.2331987626),
]


class TestMetersToDegrees(unittest.TestCase):
    def test_latitude_constant(self) -> None:
        d_lon, d_lat = meters_to_degrees(111_320.0, 0.0)
        self.assertAlmostEqual(d_lat, 1.0, places=6)
        self.assertAlmostEqual(d_lon, 1.0, places=6)  # cos(0) == 1

    def test_longitude_widens_with_latitude(self) -> None:
        _, d_lat = meters_to_degrees(30.0, 41.0)
        d_lon, _ = meters_to_degrees(30.0, 41.0)
        self.assertGreater(d_lon, d_lat)  # cos(41°) < 1 -> more degrees per metre east-west


class TestPackSquares(unittest.TestCase):
    def setUp(self) -> None:
        self.field = Polygon(PARCEL_1)

    def test_all_squares_fully_inside(self) -> None:
        squares = pack_squares(self.field, edge_m=30.0)
        self.assertGreater(len(squares), 0, "expected at least one 30 m plot in the field")
        for sq in squares:
            self.assertTrue(self.field.covers(sq), "every square must lie fully inside the field")

    def test_no_overlap_between_squares(self) -> None:
        squares = pack_squares(self.field, edge_m=30.0)
        for i in range(len(squares)):
            for j in range(i + 1, len(squares)):
                inter = squares[i].intersection(squares[j]).area
                self.assertLess(inter, 1e-12, "grid squares must not overlap")

    def test_deterministic(self) -> None:
        a = pack_squares(self.field, edge_m=30.0)
        b = pack_squares(self.field, edge_m=30.0)
        self.assertEqual(len(a), len(b))
        self.assertEqual(
            [s.bounds for s in a],
            [s.bounds for s in b],
            "packing must be deterministic (same field+edge -> identical squares)",
        )

    def test_larger_edge_yields_fewer_squares(self) -> None:
        small = pack_squares(self.field, edge_m=30.0)
        large = pack_squares(self.field, edge_m=80.0)
        self.assertGreaterEqual(len(small), len(large))

    def test_squares_are_equal_size(self) -> None:
        squares = pack_squares(self.field, edge_m=30.0)
        areas = {round(s.area, 14) for s in squares}
        self.assertEqual(len(areas), 1, "all plots must be equal-sized squares")

    def test_empty_for_nonpositive_edge(self) -> None:
        self.assertEqual(pack_squares(self.field, edge_m=0.0), [])
        self.assertEqual(pack_squares(self.field, edge_m=-5.0), [])

    def test_empty_near_the_pole(self) -> None:
        # Near the poles cos(lat)->0 and axis-aligned squares degenerate; pack refuses
        # rather than emitting wildly distorted cells.
        polar = Polygon([(0.0, 89.95), (0.001, 89.95), (0.001, 89.96), (0.0, 89.96)])
        self.assertEqual(pack_squares(polar, edge_m=30.0), [])

    def test_hops_roundtrip_of_a_plot_square(self) -> None:
        squares = pack_squares(self.field, edge_m=30.0)
        sq = squares[0]
        tokens = square_to_hops_tokens(sq)
        self.assertEqual(len(tokens), 4)
        corners = list(sq.exterior.coords)[:4]
        for token, (lon, lat) in zip(tokens, corners, strict=True):
            decoded = decode_hops_coordinate_token(token)
            self.assertIsNotNone(decoded)
            # HOPS is a 16-segment mixed-radix grid -> sub-metre cell; expect ~5 dp.
            self.assertAlmostEqual(decoded["longitude"]["value"], lon, places=4)
            self.assertAlmostEqual(decoded["latitude"]["value"], lat, places=4)


class TestPackPlots(unittest.TestCase):
    """pack_plots: rotation [0,90) + per-side spacing + rectangular cells."""

    def setUp(self) -> None:
        self.field = Polygon(PARCEL_1)
        self.lat0 = 41.0
        self.lon0 = -81.5
        self.mx = 1.0 / meters_to_degrees(1.0, self.lat0)[0]  # metres per degree lon
        self.my = 1.0 / meters_to_degrees(1.0, self.lat0)[1]  # metres per degree lat

    def _rect_field(self, width_m: float, height_m: float) -> Polygon:
        dlon = meters_to_degrees(width_m, self.lat0)[0]
        dlat = meters_to_degrees(height_m, self.lat0)[1]
        hx, hy = dlon / 2.0, dlat / 2.0
        return Polygon([
            (self.lon0 - hx, self.lat0 - hy), (self.lon0 + hx, self.lat0 - hy),
            (self.lon0 + hx, self.lat0 + hy), (self.lon0 - hx, self.lat0 + hy),
        ])

    def _disk_field(self, radius_m: float, n: int = 96) -> Polygon:
        pts = []
        for k in range(n):
            th = 2.0 * math.pi * k / n
            pts.append((
                self.lon0 + (radius_m * math.cos(th)) / self.mx,
                self.lat0 + (radius_m * math.sin(th)) / self.my,
            ))
        return Polygon(pts)

    def _metric_area(self, plot: Polygon) -> float:
        return plot.area * self.mx * self.my

    def test_containment_at_various_angles(self) -> None:
        for angle in (0.0, 30.0, 60.0, 89.999):
            plots = pack_plots(self.field, cell_w_m=30.0, cell_h_m=30.0, angle_deg=angle)
            self.assertGreater(len(plots), 0, f"expected plots at angle {angle}")
            for p in plots:
                self.assertTrue(self.field.covers(p), f"plot escaped the field at angle {angle}")

    def test_wrapper_equivalence_pack_squares(self) -> None:
        a = pack_squares(self.field, edge_m=30.0)
        b = pack_plots(self.field, cell_w_m=30.0, cell_h_m=30.0, angle_deg=0.0,
                       spacing_m=(0.0, 0.0, 0.0, 0.0))
        self.assertEqual(len(a), len(b))
        self.assertEqual([p.bounds for p in a], [p.bounds for p in b],
                         "pack_squares must equal pack_plots(square, angle 0, no spacing)")

    def test_spacing_pitch_is_cell_plus_side_gutters(self) -> None:
        # 30 cm cells, 0 top/bottom + 30 cm left/right -> row pitch 0.30 m, column pitch 0.90 m.
        field = self._rect_field(6.0, 6.0)
        plots = pack_plots(field, cell_w_m=0.30, cell_h_m=0.30, spacing_m=(0.0, 0.0, 0.30, 0.30))
        self.assertGreater(len(plots), 4)
        xs = sorted({round((p.centroid.x - self.lon0) * self.mx, 4) for p in plots})
        ys = sorted({round((p.centroid.y - self.lat0) * self.my, 4) for p in plots})
        self.assertGreaterEqual(len(xs), 3)
        self.assertGreaterEqual(len(ys), 3)
        dx = min(xs[i + 1] - xs[i] for i in range(len(xs) - 1))
        dy = min(ys[i + 1] - ys[i] for i in range(len(ys) - 1))
        self.assertAlmostEqual(dx, 0.90, places=2)  # nearest-column centre pitch
        self.assertAlmostEqual(dy, 0.30, places=2)  # nearest-row centre pitch

    def test_plot_metric_area_matches_cell_size(self) -> None:
        field = self._rect_field(5.0, 5.0)
        for w, h, ang in [(0.30, 0.30, 0.0), (0.50, 0.20, 0.0), (0.30, 0.30, 30.0)]:
            plots = pack_plots(field, cell_w_m=w, cell_h_m=h, angle_deg=ang)
            self.assertGreater(len(plots), 0, f"expected plots for {w}x{h}@{ang}")
            for p in plots:
                self.assertAlmostEqual(self._metric_area(p), w * h, places=3)

    def test_rectangle_cells_are_rectangular(self) -> None:
        field = self._rect_field(5.0, 5.0)
        plots = pack_plots(field, cell_w_m=0.50, cell_h_m=0.20, angle_deg=0.0)
        self.assertGreater(len(plots), 0)
        for p in plots:
            minx, miny, maxx, maxy = p.bounds
            self.assertAlmostEqual((maxx - minx) * self.mx, 0.50, places=2)
            self.assertAlmostEqual((maxy - miny) * self.my, 0.20, places=2)

    def test_rotated_plots_are_not_axis_aligned(self) -> None:
        plots = pack_plots(self.field, cell_w_m=30.0, cell_h_m=30.0, angle_deg=30.0)
        self.assertGreater(len(plots), 0)
        for p in plots:
            # a tilted rectangle fills less than its axis-aligned bounding box
            self.assertLess(p.area, p.envelope.area * 0.99)

    def test_rotation_count_stable_on_disk(self) -> None:
        disk = self._disk_field(2.5)
        counts = [len(pack_plots(disk, cell_w_m=0.30, cell_h_m=0.30, angle_deg=a))
                  for a in (0.0, 30.0, 60.0)]
        self.assertTrue(all(c > 0 for c in counts), f"expected plots at every angle: {counts}")
        # a disk is rotation-symmetric, so grid angle should barely change the count
        self.assertLessEqual(max(counts) - min(counts), 0.15 * max(counts) + 3, f"counts={counts}")

    def test_deterministic(self) -> None:
        kw = dict(cell_w_m=25.0, cell_h_m=25.0, angle_deg=20.0, spacing_m=(0.0, 0.0, 5.0, 5.0))
        a = pack_plots(self.field, **kw)
        b = pack_plots(self.field, **kw)
        self.assertEqual(len(a), len(b))
        self.assertEqual([p.bounds for p in a], [p.bounds for p in b])

    def test_rejects_bad_inputs(self) -> None:
        f = self.field
        self.assertEqual(pack_plots(f, cell_w_m=30.0, cell_h_m=30.0, angle_deg=90.0), [])
        self.assertEqual(pack_plots(f, cell_w_m=30.0, cell_h_m=30.0, angle_deg=-1.0), [])
        self.assertEqual(pack_plots(f, cell_w_m=0.0, cell_h_m=30.0), [])
        self.assertEqual(pack_plots(f, cell_w_m=30.0, cell_h_m=-1.0), [])
        self.assertEqual(pack_plots(f, cell_w_m=30.0, cell_h_m=30.0, spacing_m=(-1.0, 0.0, 0.0, 0.0)), [])


if __name__ == "__main__":
    unittest.main()
