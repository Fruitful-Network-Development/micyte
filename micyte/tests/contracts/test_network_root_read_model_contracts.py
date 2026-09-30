from __future__ import annotations

import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from micyte.ports.network_root_read_model import (
    NetworkRootReadModelRequest,
    NetworkRootReadModelResult,
    NetworkRootReadModelSource,
    normalize_network_surface_query,
)


class NetworkRootReadModelContractTests(unittest.TestCase):
    def test_request_normalizes_portal_tenant_and_domain(self) -> None:
        request = NetworkRootReadModelRequest(
            portal_tenant_id="FND",
            portal_domain="FruitfulNetworkDevelopment.com",
        )

        self.assertEqual(
            request.to_dict(),
            {
                "portal_tenant_id": "fnd",
                "portal_domain": "fruitfulnetworkdevelopment.com",
            },
        )

    def test_request_rejects_invalid_domain(self) -> None:
        with self.assertRaisesRegex(ValueError, "portal_domain"):
            NetworkRootReadModelRequest(
                portal_tenant_id="fnd",
                portal_domain="../fruitfulnetworkdevelopment.com",
            )

    def test_request_normalizes_surface_query(self) -> None:
        request = NetworkRootReadModelRequest(
            portal_tenant_id="FND",
            portal_domain="FruitfulNetworkDevelopment.com",
            surface_query={" view ": " system_logs ", "contract": " contract-1 ", "record": 7},
        )

        self.assertEqual(
            request.to_dict(),
            {
                "portal_tenant_id": "fnd",
                "portal_domain": "fruitfulnetworkdevelopment.com",
                "surface_query": {
                    "view": "system_logs",
                    "contract": "contract-1",
                    "record": "7",
                },
            },
        )

    def test_request_rejects_non_mapping_surface_query_when_field_is_present(self) -> None:
        with self.assertRaisesRegex(ValueError, "surface_query must be a dict"):
            NetworkRootReadModelRequest.from_dict(
                {
                    "portal_tenant_id": "fnd",
                    "portal_domain": "fruitfulnetworkdevelopment.com",
                    "surface_query": "contract=abc",
                }
            )

    def test_helper_normalizes_network_surface_query_and_surfaces_unknown_keys(self) -> None:
        query, warnings = normalize_network_surface_query(
            {
                " view ": " hosted ",
                "contract": " contract-1 ",
                "type": " type-1 ",
                "record": 7,
                "unused": "ignored",
            }
        )

        # RE-PINNED 2026-08-17. The claim under test is the one in the name — keys are
        # trimmed and coerced, and an unsupported key is REPORTED rather than dropped in
        # silence. The default view moved from `system_logs` to `map` when the operator
        # made the Network page the map; `system_logs` is not kept as an alias, because
        # a canonical query naming a view the payload is not is its own defect.
        self.assertEqual(
            query,
            {
                "view": "map",
                "contract": "contract-1",
                "type": "type-1",
                "record": "7",
            },
        )
        self.assertEqual(
            warnings,
            ("Ignored unsupported NETWORK surface_query key(s): unused",),
        )

    def test_source_payload_must_be_non_empty_json(self) -> None:
        source = NetworkRootReadModelSource(
            payload={
                "portal_instance": {
                    "portal_instance_id": "fnd",
                    "domain": "fruitfulnetworkdevelopment.com",
                }
            }
        )
        result = NetworkRootReadModelResult(source=source)

        self.assertTrue(result.found)
        self.assertEqual(result.to_dict()["source"]["payload"]["portal_instance"]["portal_instance_id"], "fnd")

        with self.assertRaisesRegex(ValueError, "non-empty dict"):
            NetworkRootReadModelSource(payload={})


if __name__ == "__main__":
    unittest.main()
