"""map_ring — decoding HOPS coordinates by LOGICAL field, and one ring per row."""

from __future__ import annotations

from micyte.core.datum_ops import viewscope as vs
from micyte.tools import _viewscope as vsr

# Live tokens: a Wayne County boundary vertex (registrar) and a trapp parcel vertex (farm).
WAYNE = "3-76-27-72-18-72-66-27-94-23-44-33-44-33-44-33-44-33"
TRAPP = "3-76-27-72-35-90-37-86-32-54-41-65-4-26-79-17-92-31"


def slot(field="coordinate", primitive="map_ring"):
    return vs.Slot(field=field, primitive=primitive, group="geometry")


def test_a_hops_token_decodes_to_a_real_coordinate():
    ring = vsr._ring([WAYNE])
    assert len(ring) == 1
    lon, lat = ring[0]
    # Wayne County, Ohio.
    assert -83 < lon < -81, lon
    assert 40 < lat < 41.5, lat


def test_the_same_decoder_serves_BOTH_namespaces():
    """`datum_resolve.resolve_coordinate` matches `Markers.COORDINATE` — rf.3-1-3, the FARM
    marker — so it decodes the two farm profiles and none of the 469 registrar boundaries,
    whose coordinate is rf.3-1-1. This decodes the CELLS the fold already resolved, so the
    namespace never enters."""
    assert len(vsr._ring([WAYNE, TRAPP])) == 2


def test_an_undecodable_cell_is_counted_not_guessed():
    payload = vsr._slot_payload(slot(), {"coordinate": [WAYNE, "not-a-coordinate", TRAPP]})
    assert len(payload["rings"][0]) == 2
    assert payload["undecoded"] == 1


def test_one_ring_per_row_never_one_merged_ring():
    """A farm profile holds four parcels in four rows. A single polygon over all their
    coordinates draws edges across the gaps between them — a shape that exists nowhere."""
    per_row = [{"coordinate": [WAYNE, WAYNE]}, {"coordinate": [TRAPP, TRAPP, TRAPP]}]
    merged = {"coordinate": [WAYNE, WAYNE, TRAPP, TRAPP, TRAPP]}
    payload = vsr._slot_payload(slot(), merged, vsr.EMPTY_INDEX, per_row)
    assert [len(r) for r in payload["rings"]] == [2, 3]


def test_the_bounds_cover_every_ring():
    per_row = [{"coordinate": [WAYNE, WAYNE]}, {"coordinate": [TRAPP, TRAPP]}]
    payload = vsr._slot_payload(slot(), {"coordinate": []}, vsr.EMPTY_INDEX, per_row)
    min_x, min_y, max_x, max_y = payload["bounds"]
    for ring in payload["rings"]:
        for lon, lat in ring:
            assert min_x <= lon <= max_x and min_y <= lat <= max_y


def test_a_slot_with_no_decodable_geometry_carries_no_rings():
    payload = vsr._slot_payload(slot(), {"coordinate": ["junk"]})
    assert "rings" not in payload
    assert "bounds" not in payload


def test_only_a_map_ring_slot_gets_geometry():
    payload = vsr._slot_payload(slot(primitive="field_pair"), {"coordinate": [WAYNE]})
    assert "rings" not in payload
