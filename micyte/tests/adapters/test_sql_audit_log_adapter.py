from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

REPO_ROOT = Path(__file__).resolve().parents[3]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from micyte.adapters.sql import SqliteAuditLogAdapter
from micyte.ports.audit_log import AuditLogAppendRequest, AuditLogReadRequest


class SqlAuditLogAdapterTests(unittest.TestCase):
    def test_append_read_and_recent_window_round_trip(self) -> None:
        with TemporaryDirectory() as temp_dir:
            adapter = SqliteAuditLogAdapter(
                Path(temp_dir) / "authority.sqlite3",
                clock=lambda: 1770000000001,
                id_factory=lambda: "audit-0001",
            )
            receipt = adapter.append_audit_record(
                AuditLogAppendRequest(
                    record={
                        "event_type": "shell.transition.accepted",
                        "focus_subject": "anthology",
                        "shell_verb": "navigate",
                    }
                )
            )
            self.assertEqual(receipt.record_id, "audit-0001")
            self.assertTrue(adapter.read_audit_record(AuditLogReadRequest(record_id="audit-0001")).found)
            self.assertEqual(adapter.read_recent_audit_records({}).record_count, 1)

    def test_bootstrap_from_filesystem_imports_existing_records(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            storage_file = root / "audit.ndjson"
            storage_file.write_text(
                "\n".join(
                    [
                        json.dumps(
                            {
                                "record_id": "audit-0002",
                                "recorded_at_unix_ms": 1770000000002,
                                "record": {"event_type": "shell.transition.accepted"},
                            }
                        ),
                        json.dumps(
                            {
                                "record_id": "audit-0001",
                                "recorded_at_unix_ms": 1770000000001,
                                "record": {"event_type": "shell.transition.accepted"},
                            }
                        ),
                    ]
                )
                + "\n",
                encoding="utf-8",
            )
            adapter = SqliteAuditLogAdapter(root / "authority.sqlite3")
            adapter.bootstrap_from_filesystem(storage_file)
            recent = adapter.read_recent_audit_records({})
            self.assertEqual([record.record_id for record in recent.records], ["audit-0002", "audit-0001"])


if __name__ == "__main__":
    unittest.main()
