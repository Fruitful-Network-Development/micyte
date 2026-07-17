from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from .mos_schema import MOS_SCHEMA_SQL

# --- Non-MOS ports co-resident in the same authority DB file ------------------
# These tables are NOT part of the MOS (datum-store) boundary defined in
# ``mos_schema.py``; they belong to the ``audit_log``, ``portal_authority`` and
# ``directive_context`` ports and share this file today only for operational
# convenience. Kept as separate fragments so the MOS schema stays cleanly
# separable from them.

_AUDIT_LOG_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS audit_records (
    record_id TEXT PRIMARY KEY,
    recorded_at_unix_ms INTEGER NOT NULL,
    record_json TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS audit_records_recorded_at_idx
ON audit_records(recorded_at_unix_ms DESC, record_id DESC);
"""

_PORTAL_AUTHORITY_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS portal_authority_snapshots (
    scope_id TEXT PRIMARY KEY,
    payload_json TEXT NOT NULL,
    updated_at_unix_ms INTEGER NOT NULL
);
"""

_DIRECTIVE_CONTEXT_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS directive_context_snapshots (
    context_id TEXT PRIMARY KEY,
    portal_instance_id TEXT NOT NULL,
    tool_id TEXT NOT NULL,
    hyphae_hash TEXT NOT NULL DEFAULT '',
    version_hash TEXT NOT NULL DEFAULT '',
    payload_json TEXT NOT NULL,
    updated_at_unix_ms INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS directive_context_events (
    event_id TEXT PRIMARY KEY,
    context_id TEXT NOT NULL,
    portal_instance_id TEXT NOT NULL,
    tool_id TEXT NOT NULL,
    event_kind TEXT NOT NULL,
    hyphae_hash TEXT NOT NULL DEFAULT '',
    version_hash TEXT NOT NULL DEFAULT '',
    payload_json TEXT NOT NULL,
    provenance_json TEXT NOT NULL,
    recorded_at_unix_ms INTEGER NOT NULL,
    FOREIGN KEY (context_id)
        REFERENCES directive_context_snapshots(context_id)
        ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS directive_context_snapshots_lookup_idx
ON directive_context_snapshots(portal_instance_id, tool_id, hyphae_hash, version_hash, updated_at_unix_ms DESC);

CREATE INDEX IF NOT EXISTS directive_context_events_lookup_idx
ON directive_context_events(portal_instance_id, tool_id, context_id, recorded_at_unix_ms DESC);
"""

# Full authority-DB schema = MOS (owned, see mos_schema.py) + the co-resident
# non-MOS ports above. Every statement is ``CREATE ... IF NOT EXISTS`` so
# composing the fragments is idempotent and order-insensitive.
SCHEMA_SQL = "\n".join(
    (
        MOS_SCHEMA_SQL,
        _AUDIT_LOG_SCHEMA_SQL,
        _PORTAL_AUTHORITY_SCHEMA_SQL,
        _DIRECTIVE_CONTEXT_SCHEMA_SQL,
    )
)


def _db_path(value: str | Path) -> Path:
    return Path(value)


def dumps_json(value: Any) -> str:
    return json.dumps(value, separators=(",", ":"), sort_keys=True)


def loads_json(value: str) -> Any:
    return json.loads(value)


def connect_sqlite(db_file: str | Path) -> sqlite3.Connection:
    path = _db_path(db_file)
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(str(path))
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    connection.execute("PRAGMA journal_mode = WAL")
    connection.executescript(SCHEMA_SQL)
    return connection


@contextmanager
def open_sqlite(db_file: str | Path):
    connection = connect_sqlite(db_file)
    try:
        yield connection
    finally:
        connection.close()
