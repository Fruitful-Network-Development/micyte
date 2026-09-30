from __future__ import annotations

import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

REPO_ROOT = Path(__file__).resolve().parents[3]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from micyte.adapters.sql import SqliteDirectiveContextAdapter
from micyte.ports.directive_context import (
    DirectiveContextEventPort,
    DirectiveContextEventQuery,
    DirectiveContextPort,
    DirectiveContextRequest,
)


class SqlDirectiveContextAdapterTests(unittest.TestCase):
    def test_adapter_conforms_and_prefers_exact_subject_match(self) -> None:
        with TemporaryDirectory() as temp_dir:
            adapter = SqliteDirectiveContextAdapter(Path(temp_dir) / "authority.sqlite3")
            self.assertIsInstance(adapter, DirectiveContextPort)
            self.assertIsInstance(adapter, DirectiveContextEventPort)
            adapter.store_directive_context(
                {
                    "context_id": "ctx-version",
                    "portal_instance_id": "fnd",
                    "tool_id": "system_workspace",
                    "subject_version_hash": "sha256:doc",
                    "nimm_state": {"navigation": "document"},
                    "aitas_state": {"attention": "document"},
                    "scope": {"surface_id": "system.root"},
                    "provenance": {"policy_source": "version_only"},
                }
            )
            adapter.store_directive_context(
                {
                    "context_id": "ctx-exact",
                    "portal_instance_id": "fnd",
                    "tool_id": "system_workspace",
                    "subject_hyphae_hash": "sha256:row",
                    "subject_version_hash": "sha256:doc",
                    "nimm_state": {"navigation": "focused"},
                    "aitas_state": {"attention": "selected"},
                    "scope": {"surface_id": "system.root"},
                    "provenance": {"policy_source": "exact"},
                }
            )
            result = adapter.read_directive_context(
                DirectiveContextRequest(
                    portal_instance_id="fnd",
                    tool_id="system_workspace",
                    subject_hyphae_hash="sha256:row",
                    subject_version_hash="sha256:doc",
                )
            )
            self.assertTrue(result.found)
            self.assertEqual(result.source.context_id, "ctx-exact")
            self.assertEqual(result.resolution_status["match_kind"], "exact_hyphae_version")

    def test_adapter_reads_event_history(self) -> None:
        with TemporaryDirectory() as temp_dir:
            adapter = SqliteDirectiveContextAdapter(Path(temp_dir) / "authority.sqlite3")
            adapter.store_directive_context(
                {
                    "context_id": "ctx-1",
                    "portal_instance_id": "fnd",
                    "tool_id": "system_workspace",
                    "subject_version_hash": "sha256:doc",
                    "nimm_state": {"navigation": "focused"},
                    "aitas_state": {"attention": "selected"},
                    "scope": {"surface_id": "system.root"},
                    "provenance": {"policy_source": "test"},
                }
            )
            adapter.append_directive_context_event(
                {
                    "event_id": "evt-1",
                    "context_id": "ctx-1",
                    "portal_instance_id": "fnd",
                    "tool_id": "system_workspace",
                    "event_kind": "snapshot_replace",
                    "payload": {"nimm": "focused"},
                    "provenance": {"actor": "test"},
                    "subject_version_hash": "sha256:doc",
                    "recorded_at_unix_ms": 100,
                }
            )
            adapter.append_directive_context_event(
                {
                    "event_id": "evt-2",
                    "context_id": "ctx-1",
                    "portal_instance_id": "fnd",
                    "tool_id": "system_workspace",
                    "event_kind": "snapshot_replace",
                    "payload": {"nimm": "selected"},
                    "provenance": {"actor": "test"},
                    "subject_version_hash": "sha256:doc",
                    "recorded_at_unix_ms": 200,
                }
            )
            records = adapter.read_directive_context_events(
                DirectiveContextEventQuery(portal_instance_id="fnd", tool_id="system_workspace", context_id="ctx-1")
            )
            self.assertEqual([record.event_id for record in records], ["evt-2", "evt-1"])


if __name__ == "__main__":
    unittest.main()
