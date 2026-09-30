from __future__ import annotations

import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from micyte.state_machine.nimm.mediate_handlers import (
    build_characteristic_set_component_frame,
    build_chronology_matrix_component_frame,
    build_component_group_frame,
    build_geospatial_component_frame,
    build_listing_component_frame,
    build_profile_component_frame,
)


class TabIdRoundTripTests(unittest.TestCase):
    """tab_id is optional; when set, every builder must round-trip it onto the frame.

    Tab partitioning depends on this contract — frames without tab_id render in
    any tab; frames with a tab_id only render when that tab is active.
    """

    def test_profile_frame_carries_tab_id(self) -> None:
        frame = build_profile_component_frame(
            attention_node_id="3-2-3-17",
            label="Test",
            fields=[],
            tab_id="garland",
        )
        self.assertEqual(frame.get("tab_id"), "garland")

    def test_profile_frame_omits_tab_id_when_unset(self) -> None:
        frame = build_profile_component_frame(
            attention_node_id="3-2-3-17",
            label="Test",
            fields=[],
        )
        self.assertNotIn("tab_id", frame)

    def test_geospatial_frame_carries_tab_id(self) -> None:
        frame = build_geospatial_component_frame(
            attention_node_id="3-2-3-17",
            geospatial_projection={},
            tab_id="garland",
        )
        self.assertEqual(frame.get("tab_id"), "garland")

    def test_characteristic_set_frame_carries_tab_id(self) -> None:
        frame = build_characteristic_set_component_frame(
            frame_id="cset",
            label="Set",
            items=[],
            attention_node_id="3-2-3-17",
            tab_id="diktataograph",
        )
        self.assertEqual(frame.get("tab_id"), "diktataograph")

    def test_component_group_frame_carries_tab_id(self) -> None:
        frame = build_component_group_frame(
            frame_id="grp",
            label="Group",
            children=[],
            attention_node_id="3-2-3-17",
            tab_id="garland",
        )
        self.assertEqual(frame.get("tab_id"), "garland")

    def test_listing_frame_carries_tab_id(self) -> None:
        frame = build_listing_component_frame(
            frame_id="lst",
            label="List",
            columns=[],
            rows=[],
            attention_node_id="3-2-3-17",
            tab_id="garland",
        )
        self.assertEqual(frame.get("tab_id"), "garland")

    def test_chronology_matrix_frame_carries_tab_id(self) -> None:
        frame = build_chronology_matrix_component_frame(
            frame_id="chrono",
            label="History",
            row_headers=[],
            column_headers=[],
            events=[],
            attention_node_id="3-2-3-17",
            tab_id="garland",
        )
        self.assertEqual(frame.get("tab_id"), "garland")


if __name__ == "__main__":
    unittest.main()
