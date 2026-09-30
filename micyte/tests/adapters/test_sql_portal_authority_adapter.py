from __future__ import annotations

import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

REPO_ROOT = Path(__file__).resolve().parents[3]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from micyte.adapters.sql import SqlitePortalAuthorityAdapter
from micyte.ports.portal_authority import PortalAuthorityPort, PortalAuthorityRequest


class SqlPortalAuthorityAdapterTests(unittest.TestCase):
    def test_adapter_conforms_and_returns_seeded_scope(self) -> None:
        with TemporaryDirectory() as temp_dir:
            adapter = SqlitePortalAuthorityAdapter(Path(temp_dir) / "authority.sqlite3")
            self.assertIsInstance(adapter, PortalAuthorityPort)
            adapter.bootstrap_from_defaults(
                scope_id="fnd",
                capabilities=("datum_recognition", "fnd_peripheral_routing"),
                tool_exposure_policy={
                    "configured_tools": {"cts_gis": True},
                    "enabled_tools": {"cts_gis": True},
                    "policy_source": "test_seed",
                },
            )
            result = adapter.read_portal_authority(
                PortalAuthorityRequest(scope_id="fnd", known_tool_ids=("cts_gis",))
            )
            self.assertTrue(result.found)
            self.assertEqual(result.source.capabilities, ("datum_recognition", "fnd_peripheral_routing"))
            self.assertEqual(result.source.tool_exposure_policy["policy_source"], "test_seed")


if __name__ == "__main__":
    unittest.main()
