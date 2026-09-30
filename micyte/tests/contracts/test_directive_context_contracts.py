from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from micyte.ports.directive_context import (
    DirectiveContextEventQuery,
    DirectiveContextEventRecord,
    DirectiveContextRequest,
    DirectiveContextResult,
    DirectiveContextSource,
)


class DirectiveContextContractTests(unittest.TestCase):
    def test_request_requires_semantic_subject(self) -> None:
        request = DirectiveContextRequest.from_dict(
            {
                "portal_instance_id": "fnd",
                "tool_id": "system_workspace",
                "subject_version_hash": "sha256:abc",
            }
        )
        self.assertEqual(
            request.to_dict(),
            {
                "portal_instance_id": "fnd",
                "tool_id": "system_workspace",
                "subject_hyphae_hash": "",
                "subject_version_hash": "sha256:abc",
            },
        )

    def test_source_normalizes_overlay_payloads(self) -> None:
        source = DirectiveContextSource.from_dict(
            {
                "context_id": "ctx-1",
                "portal_instance_id": "fnd",
                "tool_id": "system_workspace",
                "subject_hyphae_hash": "sha256:row",
                "subject_version_hash": "sha256:doc",
                "nimm_state": {"navigation": "focused"},
                "aitas_state": {"attention": "selected"},
                "scope": {"surface_id": "system.root"},
                "provenance": {"policy_source": "test"},
            }
        )
        self.assertEqual(json.loads(json.dumps(source.to_dict(), sort_keys=True)), source.to_dict())

    def test_result_and_event_shapes_round_trip(self) -> None:
        found = DirectiveContextResult.from_dict(
            {
                "source": {
                    "context_id": "ctx-1",
                    "portal_instance_id": "fnd",
                    "tool_id": "system_workspace",
                    "subject_hyphae_hash": "sha256:row",
                    "subject_version_hash": "sha256:doc",
                    "nimm_state": {"navigation": "focused"},
                    "aitas_state": {"attention": "selected"},
                    "scope": {"surface_id": "system.root"},
                    "provenance": {"policy_source": "test"},
                },
                "resolution_status": {"directive_context": "loaded"},
            }
        )
        missing = DirectiveContextResult.from_dict(
            {
                "source": None,
                "resolution_status": {"directive_context": "missing"},
                "warnings": ["sql_directive_context_missing"],
            }
        )
        event = DirectiveContextEventRecord.from_dict(
            {
                "event_id": "evt-1",
                "context_id": "ctx-1",
                "portal_instance_id": "fnd",
                "tool_id": "system_workspace",
                "event_kind": "snapshot_replace",
                "payload": {"changed": True},
                "provenance": {"actor": "test"},
                "subject_hyphae_hash": "sha256:row",
                "subject_version_hash": "sha256:doc",
                "recorded_at_unix_ms": 42,
            }
        )
        query = DirectiveContextEventQuery.from_dict(
            {"portal_instance_id": "fnd", "tool_id": "system_workspace", "limit": 10}
        )
        self.assertTrue(found.found)
        self.assertFalse(missing.found)
        self.assertEqual(missing.to_dict()["warnings"], ["sql_directive_context_missing"])
        self.assertEqual(event.to_dict()["event_kind"], "snapshot_replace")
        self.assertEqual(query.to_dict()["limit"], 10)


if __name__ == "__main__":
    unittest.main()
