from __future__ import annotations

import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from micyte.core.hops import assemble_polygon_groups


def _build(rows_with_links: dict[str, list[str]]):
    rows = {addr: {"links": links} for addr, links in rows_with_links.items()}
    return rows, lambda addr: rows.get(addr, {}).get("links", [])


class TestAssemblePolygonGroups(unittest.TestCase):
    def test_family_4_is_singleton(self) -> None:
        rows, links_of = _build({"4-0-1": []})
        self.assertEqual(
            assemble_polygon_groups("4-0-1", rows=rows, linked_addresses_of=links_of),
            [["4-0-1"]],
        )

    def test_family_5_collects_family_4_rings(self) -> None:
        rows, links_of = _build(
            {
                "4-0-1": [],
                "4-0-2": [],
                "5-0-1": ["4-0-1", "4-0-2"],
            }
        )
        self.assertEqual(
            assemble_polygon_groups("5-0-1", rows=rows, linked_addresses_of=links_of),
            [["4-0-1", "4-0-2"]],
        )

    def test_family_6_collects_family_5_polygons(self) -> None:
        rows, links_of = _build(
            {
                "4-0-1": [],
                "4-0-2": [],
                "4-0-3": [],
                "5-0-1": ["4-0-1", "4-0-2"],
                "5-0-2": ["4-0-3"],
                "6-0-1": ["5-0-1", "5-0-2"],
            }
        )
        self.assertEqual(
            assemble_polygon_groups("6-0-1", rows=rows, linked_addresses_of=links_of),
            [["4-0-1", "4-0-2"], ["4-0-3"]],
        )

    def test_family_6_with_direct_family_4_child(self) -> None:
        rows, links_of = _build(
            {
                "4-0-1": [],
                "4-0-2": [],
                "5-0-1": ["4-0-1"],
                "6-0-1": ["5-0-1", "4-0-2"],
            }
        )
        self.assertEqual(
            assemble_polygon_groups("6-0-1", rows=rows, linked_addresses_of=links_of),
            [["4-0-1"], ["4-0-2"]],
        )

    def test_family_7_recurses_through_nested_levels(self) -> None:
        rows, links_of = _build(
            {
                "4-0-1": [],
                "5-0-1": ["4-0-1"],
                "6-0-1": ["5-0-1"],
                "7-0-1": ["6-0-1"],
            }
        )
        self.assertEqual(
            assemble_polygon_groups("7-0-1", rows=rows, linked_addresses_of=links_of),
            [["4-0-1"]],
        )

    def test_unknown_address_returns_empty(self) -> None:
        rows, links_of = _build({"4-0-1": []})
        self.assertEqual(assemble_polygon_groups("9-9-9", rows=rows, linked_addresses_of=links_of), [])

    def test_unsupported_family_returns_empty(self) -> None:
        rows, links_of = _build({"1-0-1": []})
        self.assertEqual(assemble_polygon_groups("1-0-1", rows=rows, linked_addresses_of=links_of), [])


if __name__ == "__main__":
    unittest.main()
