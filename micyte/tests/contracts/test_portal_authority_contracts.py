from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from micyte.ports.portal_authority import (
    PortalAuthorityRequest,
    PortalAuthorityResult,
    PortalAuthoritySource,
)


class PortalAuthorityContractTests(unittest.TestCase):
    def test_request_normalizes_scope_and_known_tool_ids(self) -> None:
        request = PortalAuthorityRequest.from_dict(
            {"portal_instance_id": "fnd", "known_tool_ids": ["cts_gis", "fnd_dcm", "cts_gis"]}
        )
        self.assertEqual(
            request.to_dict(),
            {"scope_id": "fnd", "known_tool_ids": ["cts_gis", "fnd_dcm"]},
        )

    def test_source_requires_authoritative_policy_dict(self) -> None:
        source = PortalAuthoritySource.from_dict(
            {
                "scope_id": "fnd",
                "capabilities": ["datum_recognition", "fnd_peripheral_routing"],
                "tool_exposure_policy": {"configured_tools": {"cts_gis": True}},
                "ownership_posture": "portal_instance",
            }
        )
        self.assertEqual(
            json.loads(json.dumps(source.to_dict(), sort_keys=True)),
            source.to_dict(),
        )

    def test_result_supports_found_and_missing_shapes(self) -> None:
        found = PortalAuthorityResult.from_dict(
            {
                "source": {
                    "scope_id": "fnd",
                    "capabilities": ["datum_recognition"],
                    "tool_exposure_policy": {"configured_tools": {"cts_gis": True}},
                },
                "resolution_status": {"portal_authority": "loaded"},
            }
        )
        missing = PortalAuthorityResult.from_dict(
            {
                "source": None,
                "resolution_status": {"portal_authority": "missing"},
                "warnings": ["sql_portal_authority_missing"],
            }
        )
        self.assertTrue(found.found)
        self.assertFalse(missing.found)
        self.assertEqual(missing.to_dict()["warnings"], ["sql_portal_authority_missing"])


if __name__ == "__main__":
    unittest.main()
